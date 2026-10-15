"""
Irrelevant Handler Node - Handles non-educational requests with polite rejection.
"""

import logging
from src.Chatbot.Agent.Nodes.base_node import BaseNode
from src.Chatbot.Agent.State.agent_state import ChatbotState
from src.Chatbot.Agent.Prompts.generation_prompts import IRRELEVANT_RESPONSE_PROMPT
from src.Stores.LLM.Providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


class IrrelevantHandlerNode(BaseNode):
    """
    Node to handle non-educational requests with polite, helpful responses.
    
    Input: user_message
    Output: final_response
    """
    
    def __init__(self, llm_client: OpenAIProvider):
        """
        Initialize the irrelevant handler node with an LLM client.
        
        Args:
            llm_client: OpenAI provider instance for text generation
        """
        self.llm_client = llm_client
        self.logger = logger
        
    async def execute(self, state: ChatbotState) -> ChatbotState:
        """
        Execute the irrelevant request handling logic.
        
        Args:
            state: Current chatbot state containing user_message
            
        Returns:
            Updated state with final_response
        """
        try:
            self.logger.info("Handling irrelevant request")
            
            # Get user message from state
            user_message = state.get("user_message", "").strip()
            
            if not user_message:
                # Fallback response for empty messages
                state["final_response"] = (
                    "I'm here to help with your educational questions and learning needs. "
                    "Please feel free to ask me about any subject you're studying!"
                )
                return state
            
            # Generate personalized polite response using LLM
            response_prompt = IRRELEVANT_RESPONSE_PROMPT.format(
                user_message=user_message
            )
            
            response = self.llm_client.generate_text(
                prompt=response_prompt,
                chat_history=[],
                max_output_tokens=150,
                temperature=0.3  # Slightly creative but consistent
            )
            
            if response and response.strip():
                state["final_response"] = response.strip()
            else:
                # Fallback response if LLM fails
                self.logger.warning("LLM failed to generate irrelevant response, using fallback")
                state["final_response"] = (
                    "I'm designed to help with educational questions and learning topics. "
                    "Feel free to ask me about any subject you're studying or homework you need help with!"
                )
            
            self.logger.info("Successfully handled irrelevant request")
            return state
            
        except Exception as e:
            self.logger.error(f"Error in irrelevant handler: {e}")
            # Fallback response for any errors
            state["final_response"] = (
                "I can only assist with educational matters. "
                "Is there anything related to your studies that I can help you with?"
            )
            return state