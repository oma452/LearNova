import logging
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any
from uuid import UUID

# Add project root to path for standalone execution
if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

try:
    from typing_extensions import TypedDict
except ImportError:
    from typing import TypedDict

from mcp.server.fastmcp import FastMCP
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.Stores.VectorDB.vectordb_factory import VectorDBProviderFactory
from src.Stores.LLM.llm_facatory import LLMProviderFactory
from src.Helpers.config import get_settings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChunkResult(TypedDict):
    """Type definition for lesson chunk search results."""
    lesson_id: str
    chunk_id: str
    content: str
    similarity_score: float
    metadata: Dict[str, Any]


class LessonRetrievalServer:
    """
    MCP Server for lesson content retrieval with enhanced error handling and logging.
    """
    
    def __init__(self, llm_client=None, vectordb_client=None, session_factory=None):
        self.mcp = FastMCP("lesson_retrieval")
        self.llm_client = llm_client
        self.vectordb_client = vectordb_client
        self.session_factory = session_factory
        self._setup_tools()
        logger.info("LessonRetrievalServer initialized")
    
    async def _initialize_services(self):
        """Initialize the embedding service and database connections."""
        if self.llm_client is not None and self.vectordb_client is not None:
            return  # Already initialized via dependency injection or previous call
        
        try:
            # Get settings
            settings = get_settings()
            
            # Only create resources if not provided via dependency injection
            if self.session_factory is None:
                # Create database engine and session factory
                postgres_conn = f"postgresql+asyncpg://{settings.POSTGRES_USERNAME}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_MAIN_DATABASE}"
                engine = create_async_engine(postgres_conn)
                self.session_factory = sessionmaker(
                    bind=engine, class_=AsyncSession, expire_on_commit=False
                )
            
            if self.llm_client is None or self.vectordb_client is None:
                # Create factories only if needed
                vectordb_factory = VectorDBProviderFactory(config=settings, db_client=self.session_factory)
                llm_factory = LLMProviderFactory(config=settings)
                
                if self.llm_client is None:
                    # Create LLM client
                    self.llm_client = llm_factory.create(provider=settings.EMBEDDING_BACKEND)
                    self.llm_client.set_embedding_model(
                        model_id=settings.EMBEDDING_MODEL_ID,
                        embedding_size=settings.EMBEDDING_MODEL_SIZE
                    )
                
                if self.vectordb_client is None:
                    # Create VectorDB client
                    self.vectordb_client = vectordb_factory.create(provider=settings.VECTOR_DB_BACKEND)
                    await self.vectordb_client.connect()
            
            logger.info("Services initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize services: {e}")
            raise
    
    def _setup_tools(self):
        """Register MCP tools with the server."""
        
        @self.mcp.tool()
        async def search_lesson_chunks(
            query_text: str,
            limit: int = 10,
            lesson_ids: Optional[List[str]] = None
        ) -> List[ChunkResult]:
            """
            Search for relevant lesson content chunks based on semantic similarity.
            
            Args:
                query_text: Text query to search for
                limit: Maximum number of results to return (default: 10)
                lesson_ids: Optional list of lesson IDs to filter by
                
            Returns:
                List of relevant lesson chunks with metadata
            """
            try:
                # Input validation
                if not query_text or not isinstance(query_text, str) or not query_text.strip():
                    logger.warning("Empty or invalid query_text provided")
                    return []
                
                if not isinstance(limit, int) or limit <= 0:
                    logger.warning(f"Invalid limit provided: {limit}, using default of 10")
                    limit = 10
                
                if limit > 100:
                    logger.warning(f"Limit too high: {limit}, capping at 100")
                    limit = 100
                
                # Convert lesson_ids to UUID objects if provided
                lesson_uuid_ids = None
                if lesson_ids:
                    try:
                        lesson_uuid_ids = [UUID(lesson_id) for lesson_id in lesson_ids]
                    except ValueError as e:
                        logger.error(f"Invalid lesson ID format: {e}")
                        return []
                
                logger.info(f"Searching for chunks with query: '{query_text[:50]}...', limit: {limit}")
                
                # Initialize services if needed
                await self._initialize_services()
                
                # Generate embedding for the query using the LLM client directly
                query_embedding = self.llm_client.embed_text(query_text.strip())
                if not query_embedding or len(query_embedding) == 0:
                    logger.error("Failed to generate query embedding")
                    return []
                
                # Use the first embedding from the result
                embedding_vector = query_embedding[0]
                
                # Perform vector search using vectordb client directly
                collection_name = "lesson_vectors"
                
                # Check if collection exists
                collection_exists = await self.vectordb_client.is_collection_existed(collection_name)
                if not collection_exists:
                    logger.warning(f"Collection '{collection_name}' does not exist")
                    return []
                
                # Search with lesson_ids filter if provided
                if lesson_uuid_ids and len(lesson_uuid_ids) > 0:
                    # Convert UUIDs to strings for the vectordb client
                    lesson_ids_str = [str(lesson_id) for lesson_id in lesson_uuid_ids]
                    lesson_filter = lesson_ids_str[0] if len(lesson_ids_str) == 1 else lesson_ids_str
                    search_results = await self.vectordb_client.search_by_vector(
                        collection_name=collection_name,
                        vector=embedding_vector,
                        limit=limit,
                        lesson_id=lesson_filter
                    )
                else:
                    # Search without lesson filter
                    search_results = await self.vectordb_client.search_by_vector(
                        collection_name=collection_name,
                        vector=embedding_vector,
                        limit=limit
                    )
                
                # Convert results to the expected format
                formatted_results = []
                for i, result in enumerate(search_results):
                    formatted_result = {
                        "lesson_id": "unknown",  # Will be resolved from chunk_id
                        "chunk_id": getattr(result, 'chunk_id', f"chunk_{i}"),
                        "content": result.text,
                        "similarity_score": float(result.score),
                        "metadata": getattr(result, 'metadata', {})
                    }
                    formatted_results.append(formatted_result)
                
                logger.info(f"Found {len(formatted_results)} relevant chunks")
                return formatted_results
                
            except Exception as e:
                logger.error(f"Error searching lesson chunks: {e}")
                return []
    
    async def search_lesson_content(self, query: str, lesson_ids: list = None, limit: int = 5):
        """
        Public method to search lesson content directly without MCP.
        This provides direct access to bypass FastMCP internal structure issues.
        """
        try:
            logger.info(f"Direct search for lesson content: {query}")
            
            # Use the same logic as the MCP tool but return directly
            results = await self.search_lesson_chunks(query, lesson_ids, limit)
            
            logger.info(f"Direct search found {len(results)} chunks")
            return results
            
        except Exception as e:
            logger.error(f"Error in direct lesson content search: {e}")
            return []
    
    def run(self):
        """Start the MCP server."""
        try:
            logger.info("Starting lesson retrieval MCP server...")
            self.mcp.run()
        except Exception as e:
            logger.error(f"Failed to start MCP server: {e}")
            raise


async def create_shared_resources():
    """Create shared resources following main.py pattern to avoid duplication."""
    settings = get_settings()
    
    # Create database engine and session factory
    postgres_conn = f"postgresql+asyncpg://{settings.POSTGRES_USERNAME}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_MAIN_DATABASE}"
    engine = create_async_engine(postgres_conn)
    session_factory = sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    
    # Create factories
    vectordb_factory = VectorDBProviderFactory(config=settings, db_client=session_factory)
    llm_factory = LLMProviderFactory(config=settings)
    
    # Create embedding client
    embedding_client = llm_factory.create(provider=settings.EMBEDDING_BACKEND)
    embedding_client.set_embedding_model(
        model_id=settings.EMBEDDING_MODEL_ID,
        embedding_size=settings.EMBEDDING_MODEL_SIZE
    )
    
    # Create vectordb client
    vectordb_client = vectordb_factory.create(provider=settings.VECTOR_DB_BACKEND)
    await vectordb_client.connect()
    
    return embedding_client, vectordb_client, session_factory


# Create server instance with shared resources to avoid duplication
async def create_server_with_shared_resources():
    """Create server with shared resources to follow main.py patterns."""
    embedding_client, vectordb_client, session_factory = await create_shared_resources()
    return LessonRetrievalServer(
        llm_client=embedding_client,
        vectordb_client=vectordb_client, 
        session_factory=session_factory
    )


# For backwards compatibility, keep the simple instantiation for standalone use
server = LessonRetrievalServer()

if __name__ == "__main__":
    import asyncio
    
    async def main():
        try:
            logger.info("lesson_retrieval MCP Server is running and waiting for requests...")
            # Use shared resources for proper resource management
            server_with_shared_resources = await create_server_with_shared_resources()
            server_with_shared_resources.run()
        except KeyboardInterrupt:
            logger.info("Shutting down server.")
        except Exception as e:
            logger.error(f"Server error: {e}")
            raise
    
    # Run the server with proper async context
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise