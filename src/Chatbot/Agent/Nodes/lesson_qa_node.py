"""
Lesson Q&A Node - Answers lesson-related questions using MCP retrieval.
"""

import logging
from typing import List, Dict, Any, Optional, Callable
from uuid import UUID
from src.Chatbot.Agent.Nodes.base_node import BaseNode
from src.Chatbot.Agent.State.agent_state import ChatbotState
from src.Chatbot.Agent.Prompts.lesson_prompts import LESSON_QA_PROMPT, LESSON_CONTEXT_SUMMARY_PROMPT
from src.Stores.LLM.Providers.openai_provider import OpenAIProvider
from src.Models.services.classroom_service import ClassRoomService
from src.Models.services.lesson_service import LessonService
from src.Models.repositories.lesson_repository import LessonRepository
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class LessonQANode(BaseNode):
    """
    Node to answer lesson-related questions using MCP retrieval.
    
    This node:
    1. Retrieves student-specific lessons based on classroom enrollment
    2. Uses MCP tool to find relevant content
    3. Generates educational responses based on lesson context
    
    Input: user_message, student_id
    Output: lesson_context, lesson_response
    """

    def __init__(self, llm_client: OpenAIProvider, session: AsyncSession, mcp_tool: Optional[Any] = None):
        """
        Initialize the lesson Q&A node.
        
        Args:
            llm_client: OpenAI provider instance for text generation
            session: Database session for student/lesson queries
            mcp_tool: MCP tool function for lesson content retrieval
        """
        self.llm_client = llm_client
        self.session = session
        self.mcp_tool = mcp_tool
        self.logger = logger
        self.classroom_service = ClassRoomService(session)
        self.lesson_service = LessonService(session)
        self.lesson_repo = LessonRepository(session)
        
    async def execute(self, state: ChatbotState) -> ChatbotState:
        """
        Execute the lesson Q&A logic.
        
        Args:
            state: Current chatbot state containing user_message and student_id
            
        Returns:
            Updated state with lesson_context and lesson_response
        """
        try:
            self.logger.info("Executing lesson Q&A node")
            
            # Get user message and student ID from state
            user_message = state.get("user_message", "").strip()
            student_id = state.get("student_id", "")
            
            if not user_message:
                self.logger.warning("Empty user message provided for lesson Q&A")
                state["lesson_response"] = "Please provide a specific question about your lessons."
                state["lesson_context"] = []
                return state
            
            if not student_id:
                self.logger.warning("No student ID provided for lesson Q&A")
                # Provide general response without student-specific filtering
                return await self._handle_general_lesson_qa(state, user_message)
            
            # Get student's enrolled lessons
            student_lesson_ids = await self._get_student_lesson_ids(student_id)
            
            if not student_lesson_ids:
                self.logger.info(f"No lessons found for student {student_id}")
                state["lesson_response"] = (
                    "I don't see any lessons associated with your account yet. "
                    "Please contact your teacher or check your enrollment status."
                )
                state["lesson_context"] = []
                return state
            
            # Use MCP tool to retrieve relevant lesson content
            lesson_context = await self._retrieve_lesson_content(
                user_message, 
                student_lesson_ids
            )
            
            if not lesson_context:
                self.logger.info("No relevant lesson content found")
                state["lesson_response"] = (
                    "I couldn't find specific information about that topic in your current lessons. "
                    "Could you try rephrasing your question or ask about a different topic from your coursework?"
                )
                state["lesson_context"] = []
                return state
            
            # Generate response based on lesson context
            self.logger.info(f"About to generate lesson response with {len(lesson_context)} context chunks")
            lesson_response = await self._generate_lesson_response(
                user_message, 
                lesson_context
            )
            self.logger.info(f"Generated lesson response: {lesson_response[:100]}..." if lesson_response else "No response generated")
            
            # Update state with results
            state["lesson_context"] = lesson_context
            state["lesson_response"] = lesson_response
            
            self.logger.info(f"Successfully generated lesson response with {len(lesson_context)} context chunks")
            return state
            
        except Exception as e:
            self.logger.error(f"Error in lesson Q&A node: {e}")
            # Fallback response
            state["lesson_response"] = (
                "I'm having trouble accessing your lesson content right now. "
                "Please try again later or contact support if the issue persists."
            )
            state["lesson_context"] = []
            return state
    
    async def _get_student_lesson_ids(self, student_id: str) -> List[str]:
        """
        Get list of lesson IDs that the student has access to based on classroom enrollment.
        
        Args:
            student_id: Student's unique identifier
            
        Returns:
            List of lesson IDs the student can access
        """
        try:
            # Get student's classroom assignments
            classrooms = await self.classroom_service.get_student_classrooms(student_id)
            
            lesson_ids = []
            for classroom in classrooms:
                # Get lessons for this classroom's teacher and subject
                try:
                    teacher_id = UUID(classroom.get('teacher_id'))
                    subject_id = UUID(classroom.get('subject_id'))
                    
                    classroom_lessons = await self.lesson_repo.get_by_teacher_and_subject(
                        teacher_id=teacher_id,
                        subject_id=subject_id
                    )
                    
                    lesson_ids.extend([str(lesson.lesson_id) for lesson in classroom_lessons])
                except (ValueError, TypeError) as e:
                    self.logger.warning(f"Invalid UUID in classroom data: {e}")
                    continue
            
            # Remove duplicates and convert to strings
            unique_lesson_ids = list(set(str(lesson_id) for lesson_id in lesson_ids if lesson_id))
            
            self.logger.info(f"Found {len(unique_lesson_ids)} lessons for student {student_id}")
            return unique_lesson_ids
            
        except Exception as e:
            self.logger.error(f"Error getting student lesson IDs: {e}")
            return []
    
    async def _retrieve_lesson_content(self, user_message: str, lesson_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Use MCP tool to retrieve relevant lesson content.
        
        Args:
            user_message: Student's question
            lesson_ids: List of lesson IDs to search within
            
        Returns:
            List of relevant lesson chunks with metadata
        """
        try:
            if not self.mcp_tool:
                self.logger.warning("MCP tool not available, using fallback method")
                return []
            
            # Use MCP tool to search for relevant content
            # The MCP tool should filter by lesson_ids to only return student's accessible content
            relevant_chunks = await self.mcp_tool(
                query_text=user_message,
                limit=5,  # Get top 5 most relevant chunks
                lesson_ids=lesson_ids
            )
            
            self.logger.info(f"MCP tool returned {len(relevant_chunks)} relevant chunks")
            return relevant_chunks
            
        except Exception as e:
            self.logger.error(f"Error retrieving lesson content via MCP: {e}")
            return []
    
    async def _generate_lesson_response(self, user_message: str, lesson_context: List[Dict[str, Any]]) -> str:
        """
        Generate educational response based on lesson context.
        
        Args:
            user_message: Student's question
            lesson_context: Retrieved lesson chunks
            
        Returns:
            Generated educational response
        """
        try:
            # Format lesson context for the prompt
            context_text = self._format_lesson_context(lesson_context)
            self.logger.info(f"Formatted context: {context_text[:200]}...")
            
            # Generate response using LLM
            response_prompt = LESSON_QA_PROMPT.format(
                user_message=user_message,
                lesson_context=context_text
            )
            self.logger.info(f"Prompt length: {len(response_prompt)}")
            
            response = self.llm_client.generate_text(
                prompt=response_prompt,
                chat_history=[],
                max_output_tokens=500,
                temperature=0.3  # Balanced creativity for educational content
            )
            
            self.logger.info(f"LLM response: {response}")
            
            if not response or not response.strip():
                self.logger.warning("LLM failed to generate lesson response")
                return (
                    "I found some relevant information in your lessons, but I'm having trouble "
                    "formulating a clear response. Please try rephrasing your question."
                )

            return response.strip()
            
        except Exception as e:
            self.logger.error(f"Error generating lesson response: {e}")
            return (
                "I found relevant content in your lessons, but encountered an error "
                "while preparing the response. Please try again."
            )
    
    def _format_lesson_context(self, lesson_context: List[Dict[str, Any]]) -> str:
        """
        Format lesson chunks into readable context for the LLM prompt.
        
        Args:
            lesson_context: List of lesson chunks with metadata
            
        Returns:
            Formatted context string
        """
        if not lesson_context:
            return "No specific lesson content available."
        
        formatted_chunks = []
        for i, chunk in enumerate(lesson_context, 1):
            content = chunk.get('content', '').strip()
            similarity_score = chunk.get('similarity_score', 0)
            
            if content:
                formatted_chunks.append(
                    f"Lesson Content {i} (Relevance: {similarity_score:.2f}):\n{content}"
                )
        
        return "\n\n".join(formatted_chunks)
    
    async def _handle_general_lesson_qa(self, state: ChatbotState, user_message: str) -> ChatbotState:
        """
        Handle lesson Q&A without student-specific filtering.
        
        Args:
            state: Current chatbot state
            user_message: Student's question
            
        Returns:
            Updated state with general educational response
        """
        try:
            # Use MCP tool without lesson filtering for general educational content
            if self.mcp_tool:
                general_content = await self.mcp_tool(
                    query_text=user_message,
                    limit=3,
                    lesson_ids=None  # No filtering
                )
                
                if general_content:
                    response = await self._generate_lesson_response(user_message, general_content)
                    state["lesson_context"] = general_content
                    state["lesson_response"] = response
                    return state
            
            # Fallback to general educational response
            state["lesson_response"] = (
                "I'd be happy to help with your educational question. "
                "For more personalized assistance with your specific lessons, "
                "please make sure you're logged in to your student account."
            )
            state["lesson_context"] = []
            return state
            
        except Exception as e:
            self.logger.error(f"Error in general lesson Q&A: {e}")
            state["lesson_response"] = (
                "I'm having trouble accessing educational content right now. "
                "Please try again later."
            )
            state["lesson_context"] = []
            return state