from .base_graph import BaseGraph
from ..Nodes.enhancement_node import EnhancementNode
from ..Nodes.human_approval_gate_node import HumanApprovalGateNode
from ..Nodes.irrelevant_handler_node import IrrelevantHandlerNode
from ..Nodes.lesson_qa_node import LessonQANode
from ..Nodes.request_classifier_node import RequestClassifierNode
from ..Nodes.roadmap_generator_node import RoadmapGeneratorNode
from ..Nodes.quality_reflection_node import QualityReflectionNode
from ..Nodes.output_formatter_node import OutputFormatterNode
from ..State.agent_state import ChatbotState
from src.Stores.LLM.Providers.openai_provider import OpenAIProvider
from src.Chatbot.MCP.Servers.lesson_retrieval_server import LessonRetrievalServer
from src.Chatbot.ChatSessions.chat_sessions import ChatSessionManager
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from .graph_enums import GraphNodeType
import aioredis
import logging

logger = logging.getLogger(__name__)


class ChatbotGraph(BaseGraph):
    """
    Main chatbot graph that orchestrates the conversation flow.
    
    This graph handles the complete workflow from request classification
    to final response formatting, including human-in-the-loop approval
    for roadmap generation and quality reflection for response enhancement.
    """
    
    def __init__(self, llm_provider: OpenAIProvider, session: AsyncSession, 
                 redis_client: aioredis.Redis = None, mcp_server: LessonRetrievalServer = None):
        """
        Initialize the chatbot graph.
        
        Args:
            llm_provider: OpenAI provider for LLM operations
            session: Database session for data operations
            redis_client: Redis client for session management
            mcp_server: MCP server for lesson content retrieval
        """
        super().__init__()
        self.llm_provider = llm_provider
        self.session = session
        self.redis_client = redis_client
        self.mcp_server = mcp_server
        
        # Initialize session manager if Redis is available
        self.session_manager = None
        if redis_client:
            self.session_manager = ChatSessionManager(redis_client)
        
        # Initialize MCP tool for lesson retrieval
        self.mcp_tool = None
        if mcp_server:
            # Extract the search_lesson_chunks tool from MCP server
            self.mcp_tool = self._get_mcp_search_tool()
        
        # Initialize all nodes
        self.nodes = {
            GraphNodeType.REQUEST_CLASSIFIER_NODE.value: RequestClassifierNode(llm_client=self.llm_provider),
            GraphNodeType.IRRELEVANT_HANDLER_NODE.value: IrrelevantHandlerNode(llm_client=self.llm_provider),
            GraphNodeType.HUMAN_APPROVAL_GATE_NODE.value: HumanApprovalGateNode(),
            GraphNodeType.LESSON_QA_NODE.value: LessonQANode(
                llm_client=self.llm_provider, 
                session=self.session, 
                mcp_tool=self.mcp_tool
            ),
            GraphNodeType.ROADMAP_GENERATOR_NODE.value: RoadmapGeneratorNode(
                llm_client=self.llm_provider, 
                session=self.session
            ),
            GraphNodeType.QUALITY_REFLECTION_NODE.value: QualityReflectionNode(llm_client=self.llm_provider),
            GraphNodeType.ENHANCEMENT_NODE.value: EnhancementNode(llm_client=self.llm_provider),
            GraphNodeType.OUTPUT_FORMATTER_NODE.value: OutputFormatterNode(),
        }
    
    def _get_mcp_search_tool(self):
        """
        Extract the search function from MCP server using direct access method.
        
        Returns:
            Callable MCP search function
        """
        if not self.mcp_server:
            return None
        
        # Use the new direct access method to bypass FastMCP internal structure issues
        try:
            # Check if the MCP server has the direct search method
            if hasattr(self.mcp_server, 'search_lesson_content'):
                # Create a wrapper function to match expected signature
                async def search_tool(query_text: str, limit: int = 10, lesson_ids: list = None):
                    return await self.mcp_server.search_lesson_content(query_text, lesson_ids, limit)
                logger.info("Using direct MCP search method")
                return search_tool
            else:
                logger.warning("search_lesson_content method not found in MCP server")
                return None
        except Exception as e:
            logger.error(f"Error extracting MCP tool: {e}")
            return None
    
    def build_graph(self) -> StateGraph:
        """
        Build the complete chatbot workflow graph.
        
        Returns:
            Compiled StateGraph ready for execution
        """
        # Create the graph with ChatbotState
        graph = StateGraph(ChatbotState)
        
        # Add all nodes to the graph
        for node_name, node_instance in self.nodes.items():
            graph.add_node(node_name, node_instance.execute)
        
        # Define the workflow edges
        self._add_graph_edges(graph)
        
        # Set entry point
        graph.add_edge(START, GraphNodeType.REQUEST_CLASSIFIER_NODE.value)
        
        # Add memory saver for checkpoints (human-in-the-loop)
        memory = MemorySaver()
        
        # Compile the graph
        compiled_graph = graph.compile(checkpointer=memory)
        
        logger.info("Chatbot graph compiled successfully")
        return compiled_graph
    
    def _add_graph_edges(self, graph: StateGraph) -> None:
        """
        Add conditional edges and routing logic to the graph.
        
        Args:
            graph: StateGraph instance to add edges to
        """
        # From REQUEST_CLASSIFIER: Route based on request type
        graph.add_conditional_edges(
            GraphNodeType.REQUEST_CLASSIFIER_NODE.value,
            self._route_after_classification,
            {
                "lesson_question": GraphNodeType.LESSON_QA_NODE.value,
                "roadmap": GraphNodeType.HUMAN_APPROVAL_GATE_NODE.value,
                "irrelevant": GraphNodeType.IRRELEVANT_HANDLER_NODE.value,
            }
        )
        
        # From LESSON_QA: Go to quality reflection
        graph.add_edge(
            GraphNodeType.LESSON_QA_NODE.value,
            GraphNodeType.QUALITY_REFLECTION_NODE.value
        )
        
        # From HUMAN_APPROVAL_GATE: Route based on approval
        graph.add_conditional_edges(
            GraphNodeType.HUMAN_APPROVAL_GATE_NODE.value,
            self._route_after_approval,
            {
                "approved": GraphNodeType.ROADMAP_GENERATOR_NODE.value,
                "denied": GraphNodeType.IRRELEVANT_HANDLER_NODE.value,
            }
        )
        
        # From ROADMAP_GENERATOR: Go to quality reflection
        graph.add_edge(
            GraphNodeType.ROADMAP_GENERATOR_NODE.value,
            GraphNodeType.QUALITY_REFLECTION_NODE.value
        )
        
        # From QUALITY_REFLECTION: Route based on enhancement need
        graph.add_conditional_edges(
            GraphNodeType.QUALITY_REFLECTION_NODE.value,
            self._route_after_quality_check,
            {
                "enhance": GraphNodeType.ENHANCEMENT_NODE.value,
                "format": GraphNodeType.OUTPUT_FORMATTER_NODE.value,
            }
        )
        
        # From ENHANCEMENT: Go back to quality reflection or to formatter
        graph.add_conditional_edges(
            GraphNodeType.ENHANCEMENT_NODE.value,
            self._route_after_enhancement,
            {
                "recheck": GraphNodeType.QUALITY_REFLECTION_NODE.value,
                "format": GraphNodeType.OUTPUT_FORMATTER_NODE.value,
            }
        )
        
        # From IRRELEVANT_HANDLER: Go to output formatter
        graph.add_edge(
            GraphNodeType.IRRELEVANT_HANDLER_NODE.value,
            GraphNodeType.OUTPUT_FORMATTER_NODE.value
        )
        
        # From OUTPUT_FORMATTER: End the conversation
        graph.add_edge(GraphNodeType.OUTPUT_FORMATTER_NODE.value, END)
    
    def _route_after_classification(self, state: ChatbotState) -> str:
        """
        Route after request classification based on request type.
        
        Args:
            state: Current chatbot state
            
        Returns:
            Next node to execute
        """
        request_type = state.get("request_type", "irrelevant")
        logger.info(f"Routing after classification: {request_type}")
        
        if request_type == "lesson_question":
            return "lesson_question"
        elif request_type == "roadmap":
            return "roadmap"
        else:
            return "irrelevant"
    
    def _route_after_approval(self, state: ChatbotState) -> str:
        """
        Route after human approval based on approval decision.
        
        Args:
            state: Current chatbot state
            
        Returns:
            Next node to execute
        """
        roadmap_approved = state.get("roadmap_approved", False)
        logger.info(f"Routing after approval: {roadmap_approved}")
        
        if roadmap_approved:
            return "approved"
        else:
            return "denied"
    
    def _route_after_quality_check(self, state: ChatbotState) -> str:
        """
        Route after quality reflection based on enhancement need.
        
        Args:
            state: Current chatbot state
            
        Returns:
            Next node to execute
        """
        needs_enhancement = state.get("needs_enhancement", False)
        revision_count = state.get("revision_count", 0)
        max_revisions = 2  # Prevent infinite loops
        
        logger.info(f"Routing after quality check: needs_enhancement={needs_enhancement}, revision_count={revision_count}")
        
        if needs_enhancement and revision_count < max_revisions:
            return "enhance"
        else:
            return "format"
    
    def _route_after_enhancement(self, state: ChatbotState) -> str:
        """
        Route after enhancement based on revision count.
        
        Args:
            state: Current chatbot state
            
        Returns:
            Next node to execute
        """
        revision_count = state.get("revision_count", 0)
        max_revisions = 2
        
        logger.info(f"Routing after enhancement: revision_count={revision_count}")
        
        if revision_count < max_revisions:
            return "recheck"
        else:
            return "format"
    
    async def save_conversation_to_session(self, state: ChatbotState) -> bool:
        """
        Save conversation to Redis session if session manager is available.
        
        Args:
            state: Current chatbot state
            
        Returns:
            True if saved successfully, False otherwise
        """
        if not self.session_manager:
            return False
        
        try:
            session_id = state.get("session_id")
            student_id = state.get("student_id")
            
            if not session_id or not student_id:
                logger.warning("Missing session_id or student_id for conversation save")
                return False
            
            # Create session if it doesn't exist
            if not await self.session_manager.session_exists(session_id):
                await self.session_manager.create_session(session_id, student_id)
            
            # Save user message and final response
            conversation_entry = {
                "user_message": state.get("user_message", ""),
                "final_response": state.get("final_response", ""),
                "request_type": state.get("request_type", ""),
                "timestamp": state.get("timestamp", "")
            }
            
            return await self.session_manager.add_message(session_id, conversation_entry)
            
        except Exception as e:
            logger.error(f"Error saving conversation to session: {e}")
            return False
