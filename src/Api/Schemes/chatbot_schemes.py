"""
Chatbot API Schemas

Pydantic models for chatbot-related API requests and responses.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, validator


class ChatRequest(BaseModel):
    """Request model for chatbot interaction"""
    message: str
    session_id: Optional[str] = None

    @validator('message')
    def validate_message(cls, v):
        if not v or len(v.strip()) < 1:
            raise ValueError('Message cannot be empty')
        if len(v.strip()) > 2000:
            raise ValueError('Message too long (max 2000 characters)')
        return v.strip()


class ChatResponse(BaseModel):
    """Response model for chatbot interaction"""
    message: str
    session_id: str
    request_type: str
    needs_approval: bool
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime

    class Config:
        from_attributes = True


class ApprovalRequest(BaseModel):
    """Request model for human approval decisions"""
    session_id: str
    approved: bool
    feedback: Optional[str] = None

    @validator('feedback')
    def validate_feedback(cls, v):
        if v and len(v.strip()) > 500:
            raise ValueError('Feedback too long (max 500 characters)')
        return v.strip() if v else v


class ApprovalResponse(BaseModel):
    """Response model for approval decisions"""
    session_id: str
    status: str  # "approved", "denied", "processed"
    message: str
    timestamp: datetime

    class Config:
        from_attributes = True


class SessionRefreshRequest(BaseModel):
    """Request model for session refresh"""
    session_id: Optional[str] = None


class SessionRefreshResponse(BaseModel):
    """Response model for session refresh"""
    session_id: str
    status: str
    message: str
    timestamp: datetime

    class Config:
        from_attributes = True


class ChatSessionInfo(BaseModel):
    """Information about a chat session"""
    session_id: str
    student_id: UUID
    created_at: datetime
    last_activity: datetime
    message_count: int
    status: str  # "active", "waiting_approval", "completed"

    class Config:
        from_attributes = True
