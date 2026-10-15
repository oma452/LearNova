"""
Chatbot API Routes

FastAPI routes for chatbot-related operations including:
- Chat interaction
- Human-in-the-loop approval
- Session management
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.Api.dependencies import get_current_user, get_db_session, RoleChecker
from src.Controllers.chatbot_controller import ChatbotController
from src.Chatbot.MCP.Servers.lesson_retrieval_server import LessonRetrievalServer
from src.Api.Schemes.chatbot_schemes import (
    ChatRequest,
    ChatResponse,
    ApprovalRequest,
    ApprovalResponse,
    SessionRefreshRequest,
    SessionRefreshResponse
)
from src.Enums.user_type_enums import UserTypeEnum


# Create router with prefix and tags
router = APIRouter(
    prefix="/api/v1/students/chatbot",
    tags=["Chatbot"],
    responses={
        401: {"description": "Unauthorized - Invalid or missing authentication"},
        403: {"description": "Forbidden - Insufficient permissions"},
        500: {"description": "Internal Server Error"}
    }
)

student_admin_checker = RoleChecker(allowed_roles=[UserTypeEnum.STUDENT.value, UserTypeEnum.ADMIN.value])


@router.post("/chat", response_model=ChatResponse)
async def chat_with_bot(
    request: ChatRequest,
    current_user = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
    request_obj: Request = None
) -> ChatResponse:
    """
    Main chat endpoint for student-bot interaction.
    
    Handles lesson questions, roadmap requests, and general queries.
    Supports human-in-the-loop approval for complex responses.
    """
    try:
        print(f"Chat endpoint hit by user: {current_user}")
        print(f"Request: {request}")
        
        # Initialize shared resources for MCP server
        lesson_retrieval_server = LessonRetrievalServer(
            llm_client=request_obj.app.embedding_client,
            vectordb_client=request_obj.app.vectordb_client,
            session_factory=request_obj.app.state.db_session_factory
        )
        
        # Initialize chatbot controller
        controller = ChatbotController(
            session=db_session,
            llm_provider=request_obj.app.generation_client,
            redis_client=request_obj.app.state.redis,
            mcp_server=lesson_retrieval_server
        )
        
        # Process the chat message  
        result = await controller.process_chat_message(
            chat_request=request,
            student_unique_id=current_user["unique_id"]  # Pass unique_id as string
        )
        
        print(f"Controller result: {result}")
        
        return result
        
    except Exception as e:
        print(f"Chat endpoint error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process chat message: {str(e)}"
        )


@router.post("/approve", response_model=ApprovalResponse)
async def handle_approval(
    approval_request: ApprovalRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(student_admin_checker),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Handle human-in-the-loop approval decisions for roadmap generation.
    
    This endpoint is used to approve or deny roadmap generation requests
    that require human review. It resumes the interrupted chatbot workflow
    with the approval decision.
    
    Args:
        approval_request: Approval decision with session ID and feedback
        
    Returns:
        ApprovalResponse: Status of approval processing
    """
    try:
        # Create MCP server with shared resources from app state
        mcp_server = LessonRetrievalServer(
            llm_client=request.app.embedding_client,
            vectordb_client=request.app.vectordb_client,
            session_factory=request.app.state.db_session_factory
        )
        
        # Create chatbot controller from request state
        controller = ChatbotController(
            session=db_session,
            llm_provider=request.app.generation_client,
            redis_client=request.app.state.redis,
            mcp_server=mcp_server
        )
        
        # Process the approval decision
        response = await controller.handle_approval_decision(
            approval_request=approval_request
        )
        
        return response
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process approval decision"
        )


@router.post("/session/refresh", response_model=SessionRefreshResponse)
async def refresh_chat_session(
    refresh_request: SessionRefreshRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(student_admin_checker),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Refresh or reset a chat session.
    
    This endpoint allows users to:
    - Start a new chat session
    - Reset an existing session to clear conversation history
    - Clear any pending approvals or interrupts
    
    Args:
        refresh_request: Optional session ID to refresh
        
    Returns:
        SessionRefreshResponse: Information about the refreshed session
    """
    try:
        student_id = UUID(current_user["id"])
        
        # Create MCP server with shared resources from app state
        mcp_server = LessonRetrievalServer(
            llm_client=request.app.embedding_client,
            vectordb_client=request.app.vectordb_client,
            session_factory=request.app.state.db_session_factory
        )
        
        # Create chatbot controller from request state
        controller = ChatbotController(
            session=db_session,
            llm_provider=request.app.generation_client,
            redis_client=request.app.state.redis,
            mcp_server=mcp_server
        )
        
        # Refresh the session
        response = await controller.refresh_session(
            session_id=refresh_request.session_id,
            student_id=student_id
        )
        
        return response
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh chat session"
        )
