"""
Student Routes Module

This module exports all student-related API routes.
"""

from fastapi import APIRouter
from .student_response_router import router as student_response_router
from .student_routes import router as student_routes_router
from .ChatBotRoutes.chatbot_routes import router as chatbot_routes_router

# Create main student router
router = APIRouter()

# Include all student sub-routers
router.include_router(student_response_router)
router.include_router(student_routes_router)
router.include_router(chatbot_routes_router)

__all__ = ["router"]
