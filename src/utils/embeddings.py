"""
Embeddings generation and vector storage utilities for lesson chunks.
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from src.Models.DBSchemes.Schemes.lesson import LessonChunk
from src.Stores.VectorDB.vectordb_enums import PgVectorTableSchemeEnums


class EmbeddingGenerator:
    """Handles embeddings generation using injected LLM client."""
    
    MAX_CHUNK_SIZE = 8000  # Max tokens for embedding model
    BATCH_SIZE = 10  # Process embeddings in batches
    
    def __init__(self, llm_client):
        """
        Initialize with an LLM client (from the app's factory).
        
        Args:
            llm_client: LLM client from the app's llm_factory (e.g., app.embedding_client)
        """
        self.llm_client = llm_client
    
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
            
        Raises:
            ValueError: If embedding generation fails
        """
        try:
            # Truncate text if too long
            if len(text) > self.MAX_CHUNK_SIZE:
                text = text[:self.MAX_CHUNK_SIZE]
            
            # Use the injected LLM client's embedding method
            embeddings = self.llm_client.embed_text(text)
            
            if not embeddings or len(embeddings) == 0:
                raise ValueError("No embedding data received")
            
            return embeddings[0]  # Return first (and only) embedding
            
        except Exception as e:
            raise ValueError(f"Failed to generate embedding: {str(e)}")
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
            
        Raises:
            ValueError: If batch embedding generation fails
        """
        if not texts:
            return []
        
        try:
            all_embeddings = []
            
            # Process in batches to avoid rate limits
            for i in range(0, len(texts), self.BATCH_SIZE):
                batch_texts = texts[i:i + self.BATCH_SIZE]
                
                # Truncate long texts
                processed_texts = [
                    text[:self.MAX_CHUNK_SIZE] if len(text) > self.MAX_CHUNK_SIZE else text
                    for text in batch_texts
                ]
                
                # Use the injected LLM client's embedding method
                batch_embeddings = self.llm_client.embed_text(processed_texts)
                
                if not batch_embeddings:
                    raise ValueError(f"No embedding data received for batch {i // self.BATCH_SIZE + 1}")
                
                all_embeddings.extend(batch_embeddings)
                
                # Small delay between batches to respect rate limits
                if i + self.BATCH_SIZE < len(texts):
                    await asyncio.sleep(0.1)
            
            return all_embeddings
            
        except Exception as e:
            raise ValueError(f"Failed to generate batch embeddings: {str(e)}")
    
    def get_embedding_dimensions(self) -> int:
        """Get the dimension count for the embedding model."""
        # Get from the LLM client's configuration
        if hasattr(self.llm_client, 'embedding_size') and self.llm_client.embedding_size:
            return self.llm_client.embedding_size
        else:
            return 1536  # Default for text-embedding-3-small


class VectorStorage:
    """Handles vector storage operations using injected VectorDB client."""
    
    def __init__(self, vectordb_client):
        """
        Initialize with a VectorDB client from the app's factory.
        
        Args:
            vectordb_client: VectorDB client from app.vectordb_client
        """
        self.vectordb_client = vectordb_client
    
    async def store_chunk_embedding(
        self,
        lesson_id: UUID,
        chunk_number: int,
        chunk_text: str,
        embedding: List[float],
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Store a lesson chunk with its embedding vector using the vectordb client.
        
        Args:
            lesson_id: ID of the parent lesson
            chunk_number: Sequential number of the chunk
            chunk_text: Text content of the chunk
            embedding: Embedding vector
            metadata: Additional metadata
            
        Returns:
            True if stored successfully
            
        Raises:
            ValueError: If storage fails
        """
        try:
            # Use the vectordb client to store the embedding
            collection_name = "lesson_vectors"  # Use a separate table for vector storage
            record_id = str(lesson_id)  # Use lesson_id as record_id for individual chunks
            
            # Ensure collection exists
            collection_exists = await self.vectordb_client.is_collection_existed(collection_name)
            if not collection_exists:
                await self.vectordb_client.create_collection(
                    collection_name=collection_name,
                    embedding_size=len(embedding)
                )
            
            # Store the chunk with embedding
            success = await self.vectordb_client.insert_one(
                collection_name=collection_name,
                text=chunk_text,
                vector=embedding,
                metadata=metadata or {},
                record_id=record_id
            )
            
            return success
            
        except Exception as e:
            raise ValueError(f"Failed to store chunk embedding: {str(e)}")
    
    async def store_lesson_chunks_batch(
        self,
        lesson_id: UUID,
        chunk_data_list: List[Dict[str, Any]],
        embeddings: List[List[float]]
    ) -> bool:
        """
        Store multiple lesson chunks with embeddings in a batch using vectordb client.
        
        Args:
            lesson_id: ID of the parent lesson
            chunk_data_list: List of chunk data dictionaries
            embeddings: List of embedding vectors
            
        Returns:
            True if batch storage successful
            
        Raises:
            ValueError: If batch storage fails
        """
        if len(chunk_data_list) != len(embeddings):
            raise ValueError("Chunk data and embeddings lists must have the same length")
        
        try:
            collection_name = "lesson_vectors"  # Use a separate table for vector storage
            
            # Ensure collection exists
            collection_exists = await self.vectordb_client.is_collection_existed(collection_name)
            if not collection_exists and embeddings:
                await self.vectordb_client.create_collection(
                    collection_name=collection_name,
                    embedding_size=len(embeddings[0])
                )
            
            # Prepare batch data
            texts = []
            vectors = []
            metadata_list = []
            record_ids = []
            
            for i, (chunk_data, embedding) in enumerate(zip(chunk_data_list, embeddings)):
                texts.append(chunk_data['chunk_text'])
                vectors.append(embedding)
                metadata_list.append(chunk_data.get('chunk_metadata', {}))
                # Use the actual chunk_id from the database
                record_ids.append(str(chunk_data['chunk_id']))
            
            # Store batch
            success = await self.vectordb_client.insert_many(
                collection_name=collection_name,
                texts=texts,
                vectors=vectors,
                metadata=metadata_list,
                record_ids=record_ids
            )
            
            return success
            
        except Exception as e:
            raise ValueError(f"Failed to store lesson chunks batch: {str(e)}")
    
    async def search_similar_chunks(
        self,
        query_embedding: List[float],
        limit: int = 10,
        lesson_ids: Optional[List[UUID]] = None
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Search for similar chunks using vector similarity via vectordb client.
        
        Args:
            query_embedding: Query embedding vector
            limit: Maximum number of results
            lesson_ids: Optional list of lesson IDs to filter by
            
        Returns:
            List of tuples (chunk_data, similarity_score)
        """
        try:
            collection_name = "lesson_vectors"  # Use a separate table for vector storage
            
            # Check if collection exists
            collection_exists = await self.vectordb_client.is_collection_existed(collection_name)
            if not collection_exists:
                return []
            
            # If lesson_ids filter is provided, use it for filtering
            if lesson_ids and len(lesson_ids) > 0:
                # Convert UUIDs to strings for the vectordb client
                lesson_ids_str = [str(lesson_id) for lesson_id in lesson_ids]
                
                # Pass lesson_ids to vectordb client (supports both single and multiple)
                lesson_filter = lesson_ids_str[0] if len(lesson_ids_str) == 1 else lesson_ids_str
                results = await self.vectordb_client.search_by_vector(
                    collection_name=collection_name,
                    vector=query_embedding,
                    limit=limit,
                    lesson_id=lesson_filter
                )
            else:
                # Search using vectordb client without lesson_id filter (original behavior)
                results = await self.vectordb_client.search_by_vector(
                    collection_name=collection_name,
                    vector=query_embedding,
                    limit=limit
                )
            
            # Convert to expected format
            formatted_results = []
            for i, result in enumerate(results):
                chunk_data = {
                    'record_id': f"search_result_{i}",  # Placeholder since we don't have actual record_id
                    'content': result.text,
                    'metadata': {}  # No metadata available in current implementation
                }
                formatted_results.append((chunk_data, result.score))
            
            return formatted_results
            
        except Exception as e:
            raise ValueError(f"Similarity search failed: {str(e)}")


class LessonEmbeddingService:
    """High-level service for managing lesson embeddings and vector storage."""
    
    def __init__(self, llm_client, vectordb_client, db_session: AsyncSession):
        """
        Initialize with injected clients from the app's factories.
        
        Args:
            llm_client: LLM client from app.embedding_client
            vectordb_client: VectorDB client from app.vectordb_client
            db_session: Database session
        """
        self.embedding_generator = EmbeddingGenerator(llm_client)
        self.vector_storage = VectorStorage(vectordb_client)
        self.db_session = db_session
    
    async def process_and_store_lesson(
        self,
        lesson_id: UUID,
        chunk_data_list: List[Dict[str, Any]]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Process lesson chunks and store them with embeddings.
        
        Args:
            lesson_id: ID of the lesson
            chunk_data_list: List of chunk data from PDF processing
            
        Returns:
            Tuple of (success, processing_stats)
            
        Raises:
            ValueError: If processing fails
        """
        try:
            # Extract chunk texts for embedding generation
            chunk_texts = [chunk_data['chunk_text'] for chunk_data in chunk_data_list]
            
            # Generate embeddings for all chunks
            embeddings = await self.embedding_generator.generate_embeddings_batch(chunk_texts)
            
            # Store chunks with embeddings using vectordb client
            success = await self.vector_storage.store_lesson_chunks_batch(
                lesson_id=lesson_id,
                chunk_data_list=chunk_data_list,
                embeddings=embeddings
            )
            
            if not success:
                raise ValueError("Failed to store embeddings in vector database")
            
            # Generate processing statistics
            processing_stats = {
                'total_chunks': len(chunk_data_list),
                'total_embeddings': len(embeddings),
                'embedding_dimensions': self.embedding_generator.get_embedding_dimensions(),
                'processing_status': 'success'
            }
            
            return success, processing_stats
            
        except Exception as e:
            raise ValueError(f"Lesson embedding processing failed: {str(e)}")
    
    async def search_lesson_content(
        self,
        query_text: str,
        limit: int = 10,
        lesson_ids: Optional[List[UUID]] = None
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Search for relevant lesson content using semantic similarity.
        
        Args:
            query_text: Search query text
            limit: Maximum number of results
            lesson_ids: Optional lesson IDs to filter by
            
        Returns:
            List of tuples (chunk_data, similarity_score)
        """
        try:
            # Generate embedding for the query
            query_embedding = await self.embedding_generator.generate_embedding(query_text)
            
            # Search for similar chunks
            return await self.vector_storage.search_similar_chunks(
                query_embedding=query_embedding,
                limit=limit,
                lesson_ids=lesson_ids
            )
            
        except Exception as e:
            raise ValueError(f"Content search failed: {str(e)}")
    
    async def update_lesson_embeddings(self, lesson_id: UUID, chunk_data_list: List[Dict[str, Any]]) -> bool:
        """
        Update embeddings for an existing lesson.
        
        Args:
            lesson_id: ID of the lesson
            chunk_data_list: New chunk data
            
        Returns:
            True if update successful
        """
        try:
            # Note: With vectordb client, we would need to delete old entries first
            # This is a simplified implementation - in practice you might want to
            # delete by collection + record_id pattern for the lesson
            
            # Process and store new chunks
            success, _ = await self.process_and_store_lesson(lesson_id, chunk_data_list)
            
            return success
            
        except Exception as e:
            raise ValueError(f"Failed to update lesson embeddings: {str(e)}")
