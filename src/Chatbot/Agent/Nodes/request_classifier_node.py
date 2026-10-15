"""
Request Classifier Node - Analyzes and categorizes user requests.
"""

import json
import logging
from typing import Dict, Any, Optional
from src.Chatbot.Agent.Nodes.base_node import BaseNode
from src.Chatbot.Agent.State.agent_state import ChatbotState
from src.Chatbot.Agent.Prompts.classification_prompts import REQUEST_CLASSIFICATION_PROMPT
from src.Stores.LLM.Providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


class RequestClassifierNode(BaseNode):
    """
    Node to analyze incoming user requests and categorize their intent.
    
    This node classifies user messages into educational request types and
    provides confidence scores for the classification.
    
    Input: user_message, student_id
    Output: request_type, confidence_score
    """
    
    def __init__(self, llm_client: OpenAIProvider):
        """
        Initialize the classifier node.
        
        Args:
            llm_client: OpenAI provider instance for text generation
        """
        self.llm_client = llm_client
        self.logger = logger
        
    async def execute(self, state: ChatbotState) -> ChatbotState:
        """
        Execute the request classification logic.
        
        Args:
            state: Current chatbot state containing user_message and student_id
            
        Returns:
            Updated state with request_type and confidence_score
        """
        try:
            self.logger.info(f"Classifying request for student {state.get('student_id', 'unknown')}")
            
            # Get user message from state
            user_message = state.get("user_message", "").strip()
            if not user_message:
                self.logger.warning("Empty user message provided for classification")
                state["request_type"] = "irrelevant"
                state["confidence_score"] = 1.0
                return state
            
            # Format the classification prompt
            classification_prompt = REQUEST_CLASSIFICATION_PROMPT.format(
                user_message=user_message
            )
            
            # Generate classification using LLM
            response = self.llm_client.generate_text(
                prompt=classification_prompt,
                chat_history=[],
                max_output_tokens=200,
                temperature=0.1  # Low temperature for consistent classification
            )
            
            if not response:
                self.logger.error("Failed to get classification response from LLM")
                # Fallback classification
                state["request_type"] = "lesson_question"  # Safe default
                state["confidence_score"] = 0.5
                return state
            
            # Parse the JSON response
            classification_result = self._parse_classification_response(response)
            
            # Update state with classification results
            state["request_type"] = classification_result["request_type"]
            state["confidence_score"] = classification_result["confidence_score"]
            
            self.logger.info(
                f"Classified request as '{classification_result['request_type']}' "
                f"with confidence {classification_result['confidence_score']:.2f}"
            )
            
            return state
            
        except Exception as e:
            self.logger.error(f"Error in request classification: {e}")
            # Fallback to safe default
            state["request_type"] = "lesson_question"
            state["confidence_score"] = 0.5
            return state
    
    def _parse_classification_response(self, response: str) -> Dict[str, Any]:
        """
        Parse the LLM classification response.
        
        Args:
            response: Raw response from LLM
            
        Returns:
            Dictionary with request_type and confidence_score
        """
        try:
            # Try to extract JSON from response
            response_clean = response.strip()
            
            # Handle cases where response might contain extra text
            if "{" in response_clean:
                json_start = response_clean.find("{")
                json_end = response_clean.rfind("}") + 1
                json_str = response_clean[json_start:json_end]
            else:
                json_str = response_clean
            
            # Parse JSON
            result = json.loads(json_str)
            
            # Validate request_type
            valid_types = ["roadmap", "lesson_question", "irrelevant"]
            request_type = result.get("request_type", "lesson_question")
            if request_type not in valid_types:
                self.logger.warning(f"Invalid request_type: {request_type}, defaulting to lesson_question")
                request_type = "lesson_question"
            
            # Validate confidence_score
            confidence_score = float(result.get("confidence_score", 0.5))
            confidence_score = max(0.0, min(1.0, confidence_score))  # Clamp to [0, 1]
            
            return {
                "request_type": request_type,
                "confidence_score": confidence_score
            }
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.warning(f"Failed to parse classification response: {e}")
            self.logger.debug(f"Raw response: {response}")
            
            # Fallback parsing - try to extract key information
            response_lower = response.lower()
            
            if "roadmap" in response_lower:
                return {"request_type": "roadmap", "confidence_score": 0.7}
            elif "irrelevant" in response_lower:
                return {"request_type": "irrelevant", "confidence_score": 0.7}
            else:
                return {"request_type": "lesson_question", "confidence_score": 0.6}