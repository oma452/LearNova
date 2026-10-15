"""
Enhancement Node - Improves responses based on quality reflection feedback.
"""

import logging
from typing import Dict, Any, Optional
from src.Chatbot.Agent.Nodes.base_node import BaseNode
from src.Chatbot.Agent.State.agent_state import ChatbotState
from src.Chatbot.Agent.Prompts.generation_prompts import (
    ENHANCEMENT_PROMPT, 
    LESSON_ENHANCEMENT_PROMPT,
    ROADMAP_ENHANCEMENT_PROMPT
)
from src.Stores.LLM.Providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


class EnhancementNode(BaseNode):
    """
    Node to enhance responses based on quality reflection feedback.
    
    This node takes the enhancement_feedback and improves either lesson_response 
    or roadmap_content accordingly using LLM-based enhancement.
    
    Input: enhancement_feedback, lesson_response OR roadmap_content
    Output: Enhanced lesson_response OR roadmap_content
    """
    
    def __init__(self, llm_client: OpenAIProvider):
        """
        Initialize the enhancement node.
        
        Args:
            llm_client: OpenAI provider instance for text generation
        """
        self.llm_client = llm_client
        self.logger = logger
        
    async def execute(self, state: ChatbotState) -> ChatbotState:
        """
        Execute the enhancement logic.
        
        Args:
            state: Current chatbot state
            
        Returns:
            Updated state with enhanced response content
        """
        try:
            self.logger.info("Executing enhancement node")
            
            # Get enhancement feedback
            enhancement_feedback = state.get("enhancement_feedback")
            if not enhancement_feedback:
                self.logger.warning("No enhancement feedback provided, skipping enhancement")
                return state
            
            # Get original user message for context
            original_question = state.get("user_message", "")
            
            # Determine what content to enhance
            response_content, response_type = self._get_response_content(state)
            
            if not response_content:
                self.logger.warning("No response content found for enhancement")
                return state
            
            # Perform enhancement
            enhanced_content = await self._enhance_content(
                response_content,
                enhancement_feedback,
                original_question,
                response_type
            )
            
            if enhanced_content:
                # Update the appropriate field in state
                if response_type == "lesson_response":
                    state["lesson_response"] = enhanced_content
                    self.logger.info("Enhanced lesson response")
                elif response_type == "roadmap_content":
                    state["roadmap_content"] = enhanced_content
                    self.logger.info("Enhanced roadmap content")
                
                # Clear enhancement feedback to indicate completion
                state["enhancement_feedback"] = None
                state["needs_enhancement"] = False
            else:
                self.logger.error("Failed to enhance content")
            
            return state
            
        except Exception as e:
            self.logger.error(f"Error in enhancement: {e}")
            # Clear enhancement flags to prevent infinite loops
            state["enhancement_feedback"] = None
            state["needs_enhancement"] = False
            return state
    
    def _get_response_content(self, state: ChatbotState) -> tuple[Optional[str], str]:
        """
        Extract the response content to be enhanced.
        
        Args:
            state: Current chatbot state
            
        Returns:
            Tuple of (response_content, response_type)
        """
        # Check for lesson response first
        lesson_response = state.get("lesson_response")
        if lesson_response and lesson_response.strip():
            return lesson_response.strip(), "lesson_response"
        
        # Check for roadmap content
        roadmap_content = state.get("roadmap_content")
        if roadmap_content and roadmap_content.strip():
            return roadmap_content.strip(), "roadmap_content"
        
        # No content found
        return None, "unknown"
    
    async def _enhance_content(
        self, 
        original_content: str, 
        enhancement_feedback: str, 
        original_question: str,
        response_type: str
    ) -> Optional[str]:
        """
        Enhance the content based on feedback.
        
        Args:
            original_content: Original response content
            enhancement_feedback: Specific feedback for improvement
            original_question: Original user question
            response_type: Type of content being enhanced
            
        Returns:
            Enhanced content or None if enhancement fails
        """
        try:
            # Choose appropriate enhancement prompt
            enhancement_prompt = self._get_enhancement_prompt(
                response_type,
                original_content,
                enhancement_feedback,
                original_question
            )
            
            # Generate enhanced content
            enhanced_response = self.llm_client.generate_text(
                prompt=enhancement_prompt,
                chat_history=[],
                max_output_tokens=800,  # Increased for enhanced content
                temperature=0.3  # Slightly creative but controlled
            )
            
            if not enhanced_response:
                self.logger.error("Failed to get enhanced content from LLM")
                return None
            
            # Validate enhanced content
            if self._validate_enhanced_content(enhanced_response, original_content):
                return enhanced_response.strip()
            else:
                self.logger.warning("Enhanced content validation failed")
                return None
                
        except Exception as e:
            self.logger.error(f"Error enhancing content: {e}")
            return None
    
    def _get_enhancement_prompt(
        self,
        response_type: str,
        original_content: str,
        enhancement_feedback: str,
        original_question: str
    ) -> str:
        """
        Get the appropriate enhancement prompt based on response type.
        
        Args:
            response_type: Type of content being enhanced
            original_content: Original response content
            enhancement_feedback: Feedback for improvement
            original_question: Original user question
            
        Returns:
            Formatted enhancement prompt
        """
        if response_type == "lesson_response":
            return LESSON_ENHANCEMENT_PROMPT.format(
                original_question=original_question,
                original_response=original_content,
                enhancement_feedback=enhancement_feedback
            )
        elif response_type == "roadmap_content":
            return ROADMAP_ENHANCEMENT_PROMPT.format(
                original_question=original_question,
                original_roadmap=original_content,
                enhancement_feedback=enhancement_feedback
            )
        else:
            # Generic enhancement prompt
            return ENHANCEMENT_PROMPT.format(
                original_question=original_question,
                original_content=original_content,
                enhancement_feedback=enhancement_feedback
            )
    
    def _validate_enhanced_content(self, enhanced_content: str, original_content: str) -> bool:
        """
        Validate that enhanced content is actually improved.
        
        Args:
            enhanced_content: The enhanced content
            original_content: The original content
            
        Returns:
            True if content appears to be enhanced, False otherwise
        """
        try:
            # Basic validation checks
            if not enhanced_content or not enhanced_content.strip():
                return False
            
            # Enhanced content should be different from original
            if enhanced_content.strip() == original_content.strip():
                self.logger.warning("Enhanced content is identical to original")
                return False
            
            # Enhanced content should be reasonably substantial
            if len(enhanced_content.strip()) < 50:
                self.logger.warning("Enhanced content is too short")
                return False
            
            # Enhanced content should be longer or at least similar length
            # (allowing for cases where content is made more concise but better)
            if len(enhanced_content) < len(original_content) * 0.7:
                self.logger.warning("Enhanced content is significantly shorter")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error validating enhanced content: {e}")
            return False
    
    def _get_fallback_enhancement(self, original_content: str, enhancement_feedback: str) -> str:
        """
        Provide a fallback enhancement when LLM fails.
        
        Args:
            original_content: Original content
            enhancement_feedback: Enhancement feedback
            
        Returns:
            Fallback enhanced content
        """
        return f"""**Enhanced Response:**

{original_content}

**Additional Notes:**
Based on the feedback provided, please consider the following improvements: {enhancement_feedback}

This response has been enhanced to better address your question. If you need further clarification or have additional questions, please feel free to ask.
"""