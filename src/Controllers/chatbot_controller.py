"""
Chatbot Controller

Business logic for chatbot operations including chat processing,
human-in-the-loop approval handling, and session management.
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.graph.graph import CompiledGraph

from src.Chatbot.Agent.Graph.chatbot_graph import ChatbotGraph
from src.Chatbot.Agent.State.agent_state import ChatbotState
from src.Chatbot.ChatSessions.chat_sessions import ChatSessionManager
from src.Stores.LLM.Providers.openai_provider import OpenAIProvider
from src.Chatbot.MCP.Servers.lesson_retrieval_server import LessonRetrievalServer
from src.Api.Schemes.chatbot_schemes import (
    ChatRequest, 
    ChatResponse, 
    ApprovalRequest, 
    ApprovalResponse,
    SessionRefreshResponse
)
import aioredis

logger = logging.getLogger(__name__)


class ChatbotController:
    """
    Controller for handling chatbot operations.
    
    Manages the integration between the chatbot graph, session management,
    and human-in-the-loop approval workflows.
    """
    
    def __init__(self, 
                 session: AsyncSession,
                 llm_provider: OpenAIProvider,
                 redis_client: aioredis.Redis,
                 mcp_server: LessonRetrievalServer):
        """
        Initialize the chatbot controller.
        
        Args:
            session: Database session
            llm_provider: OpenAI provider for LLM operations
            redis_client: Redis client for session management
            mcp_server: MCP server for lesson retrieval
        """
        self.session = session
        self.llm_provider = llm_provider
        self.redis_client = redis_client
        self.mcp_server = mcp_server
        
        # Initialize chatbot graph
        self.chatbot_graph = ChatbotGraph(
            llm_provider=llm_provider,
            session=session,
            redis_client=redis_client,
            mcp_server=mcp_server
        )
        
        # Compile the graph
        self.compiled_graph = self.chatbot_graph.build_graph()
        
        # Initialize session manager
        self.session_manager = ChatSessionManager(redis_client)
        
        logger.info("ChatbotController initialized successfully")
    
    async def process_chat_message(self, 
                                   chat_request: ChatRequest, 
                                   student_unique_id: str) -> ChatResponse:
        """
        Process a chat message from a student.
        
        Args:
            chat_request: Chat request with message and optional session_id
            student_unique_id: Unique ID of the student sending the message (e.g., "22009")
            
        Returns:
            ChatResponse: Response from the chatbot
        """
        try:
            # Generate or use existing session ID
            session_id = chat_request.session_id or str(uuid.uuid4())
            
            # Create session if it doesn't exist
            if not await self.session_manager.session_exists(session_id):
                await self.session_manager.create_session(session_id, student_unique_id)
            
            # Prepare initial state
            initial_state = {
                "user_message": chat_request.message,
                "session_id": session_id,
                "student_id": student_unique_id,  # Use unique_id instead of UUID
                "timestamp": datetime.now().isoformat(),
                "final_response": "",
                "request_type": "lesson_question",  # Default value
                "confidence_score": 0.0,
                "lesson_context": None,
                "lesson_response": None,
                "roadmap_approved": None,
                "roadmap_content": None,
                "needs_enhancement": False,
                "enhancement_feedback": None,
                "revision_count": 0
            }
            
            # Create thread configuration for LangGraph
            thread_config = {
                "configurable": {
                    "thread_id": session_id
                }
            }
            
            # Execute the graph
            result = None
            needs_approval = False
            
            try:
                # Run the graph and get the final result
                async for output in self.compiled_graph.astream(
                    initial_state,
                    config=thread_config
                ):
                    # The output is a dict with node_name -> state mapping
                    if output:
                        # Get the last output (final state)
                        result = list(output.values())[-1]
                
                # Check if we hit an interrupt (human approval needed)
                # We can detect this by checking if roadmap_approved is None and request_type is roadmap
                if result and result.get("request_type") == "roadmap" and result.get("roadmap_approved") is None:
                    needs_approval = True
                    response_message = "Your roadmap request requires approval. Please wait for human review."
                else:
                    response_message = result.get("final_response", "I'm sorry, I couldn't process your request.")
                
            except Exception as graph_error:
                logger.error(f"Graph execution error: {graph_error}", exc_info=True)
                response_message = f"Graph execution failed: {str(graph_error)}"
                needs_approval = False
                result = {}
            
            # Save conversation to session
            await self._save_conversation_entry(
                session_id=session_id,
                user_message=chat_request.message,
                bot_response=response_message,
                request_type=result.get("request_type", "unknown")
            )
            
            # Prepare metadata
            metadata = {
                "confidence_score": result.get("confidence_score"),
                "processing_time": result.get("processing_time"),
                "revision_count": result.get("revision_count", 0)
            }
            
            return ChatResponse(
                message=response_message,
                session_id=session_id,
                request_type=result.get("request_type", "unknown"),
                needs_approval=needs_approval,
                metadata=metadata,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error processing chat message: {e}")
            # Return error response
            return ChatResponse(
                message="I'm sorry, I encountered an error while processing your message. Please try again.",
                session_id=session_id,
                request_type="error",
                needs_approval=False,
                metadata={"error": str(e)},
                timestamp=datetime.now()
            )
    
    async def handle_approval_decision(self, 
                                       approval_request: ApprovalRequest) -> ApprovalResponse:
        """
        Handle human approval decision for roadmap generation.
        
        Args:
            approval_request: Approval decision from human reviewer
            
        Returns:
            ApprovalResponse: Response indicating approval processing status
        """
        try:
            session_id = approval_request.session_id
            
            # Prepare thread configuration
            thread_config = {
                "configurable": {
                    "thread_id": session_id
                }
            }
            
            # Create approval response state
            approval_state = {
                "roadmap_approved": approval_request.approved,
                "approval_feedback": approval_request.feedback or "",
                "approval_timestamp": datetime.now().isoformat()
            }
            
            # Resume the graph execution with approval decision
            result = None
            try:
                async for output in self.compiled_graph.astream(
                    approval_state,
                    config=thread_config
                ):
                    if output:
                        result = list(output.values())[-1]
                
                if approval_request.approved:
                    message = result.get("final_response", "Roadmap has been generated successfully.")
                    status = "approved"
                else:
                    message = "Your request has been reviewed and cannot be processed at this time."
                    status = "denied"
                
                # Save the final response to session
                await self._save_conversation_entry(
                    session_id=session_id,
                    user_message=f"[APPROVAL: {'Approved' if approval_request.approved else 'Denied'}]",
                    bot_response=message,
                    request_type="approval_response"
                )
                
            except Exception as graph_error:
                logger.error(f"Graph resume error: {graph_error}")
                message = "Error processing approval decision. Please try again."
                status = "error"
            
            return ApprovalResponse(
                session_id=session_id,
                status=status,
                message=message,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error handling approval decision: {e}")
            return ApprovalResponse(
                session_id=approval_request.session_id,
                status="error",
                message="Failed to process approval decision",
                timestamp=datetime.now()
            )
    
    async def refresh_session(self, 
                              session_id: Optional[str], 
                              student_id: UUID) -> SessionRefreshResponse:
        """
        Refresh or create a new chat session for the student.
        
        Args:
            session_id: Optional existing session ID to refresh
            student_id: ID of the student
            
        Returns:
            SessionRefreshResponse: Information about the refreshed session
        """
        try:
            # Generate new session ID if not provided
            new_session_id = session_id or str(uuid.uuid4())
            
            # Create or recreate the session
            await self.session_manager.create_session(new_session_id, str(student_id))
            
            # Clear any existing checkpoints for this session
            thread_config = {
                "configurable": {
                    "thread_id": new_session_id
                }
            }
            
            # Note: LangGraph MemorySaver doesn't have a direct clear method
            # The checkpoints will be overwritten on next execution
            
            logger.info(f"Session refreshed: {new_session_id} for student: {student_id}")
            
            return SessionRefreshResponse(
                session_id=new_session_id,
                status="refreshed",
                message="Chat session has been refreshed successfully.",
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error refreshing session: {e}")
            return SessionRefreshResponse(
                session_id=session_id or "unknown",
                status="error",
                message="Failed to refresh chat session",
                timestamp=datetime.now()
            )
    
    async def _save_conversation_entry(self, 
                                       session_id: str, 
                                       user_message: str, 
                                       bot_response: str, 
                                       request_type: str) -> bool:
        """
        Save a conversation entry to the session.
        
        Args:
            session_id: Session ID
            user_message: User's message
            bot_response: Bot's response
            request_type: Type of request processed
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            conversation_entry = {
                "user_message": user_message,
                "bot_response": bot_response,
                "request_type": request_type,
                "timestamp": datetime.now().isoformat()
            }
            
            return await self.session_manager.add_message(session_id, conversation_entry)
            
        except Exception as e:
            logger.error(f"Error saving conversation entry: {e}")
            return False
