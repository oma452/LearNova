"""
Quality Reflection Node - Evaluates response quality and suggests improvements.
"""

import json
import logging
from typing import Dict, Any, Optional
from src.Chatbot.Agent.Nodes.base_node import BaseNode
from src.Chatbot.Agent.State.agent_state import ChatbotState
from src.Chatbot.Agent.Prompts.quality_prompts import QUALITY_REFLECTION_PROMPT
from src.Stores.LLM.Providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


class QualityReflectionNode(BaseNode):
    """
    Node to evaluate response quality and suggest improvements.
    
    This node analyzes either lesson_response or roadmap_content and determines:
    1. Whether the response needs enhancement
    2. Specific feedback for improvement
    3. Quality assessment metrics
    
    Input: lesson_response OR roadmap_content
    Output: needs_enhancement, enhancement_feedback
    """
    
    def __init__(self, llm_client: OpenAIProvider):
        """
        Initialize the quality reflection node.
        
        Args:
            llm_client: OpenAI provider instance for text generation
        """
        self.llm_client = llm_client
        self.logger = logger
        
        # Quality thresholds
        self.quality_threshold = 0.8  # Minimum quality score to pass
        self.max_revisions = 2  # Maximum number of enhancement attempts
        
    async def execute(self, state: ChatbotState) -> ChatbotState:
        """
        Execute the quality reflection logic.
        
        Args:
            state: Current chatbot state
            
        Returns:
            Updated state with needs_enhancement and enhancement_feedback
        """
        try:
            self.logger.info("Executing quality reflection node")
            
            # Get the response content to evaluate
            response_content, response_type = self._get_response_content(state)
            
            if not response_content:
                self.logger.warning("No response content found for quality reflection")
                state["needs_enhancement"] = False
                state["enhancement_feedback"] = None
                return state
            
            # Get original question for context
            original_question = state.get("user_message", "")
            
            # Check revision count to avoid infinite loops
            revision_count = state.get("revision_count", 0)
            if revision_count >= self.max_revisions:
                self.logger.info(f"Maximum revisions ({self.max_revisions}) reached, approving response")
                state["needs_enhancement"] = False
                state["enhancement_feedback"] = None
                return state
            
            # Perform quality assessment
            quality_assessment = await self._assess_quality(
                response_content, 
                original_question, 
                response_type
            )
            
            # Update state with assessment results
            state["needs_enhancement"] = quality_assessment["needs_enhancement"]
            state["enhancement_feedback"] = quality_assessment["enhancement_feedback"]
            
            # Update revision count if enhancement is needed
            if quality_assessment["needs_enhancement"]:
                state["revision_count"] = revision_count + 1
                self.logger.info(
                    f"Quality assessment suggests enhancement (revision {revision_count + 1})"
                )
            else:
                self.logger.info("Quality assessment passed, no enhancement needed")
            
            return state
            
        except Exception as e:
            self.logger.error(f"Error in quality reflection: {e}")
            # Default to no enhancement on error to avoid blocking the flow
            state["needs_enhancement"] = False
            state["enhancement_feedback"] = None
            return state
    
    def _get_response_content(self, state: ChatbotState) -> tuple[Optional[str], str]:
        """
        Extract the response content to be evaluated.
        
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
    
    async def _assess_quality(self, response_content: str, original_question: str, response_type: str) -> Dict[str, Any]:
        """
        Assess the quality of the response content.
        
        Args:
            response_content: The response to evaluate
            original_question: Original user question for context
            response_type: Type of response (lesson_response or roadmap_content)
            
        Returns:
            Quality assessment results
        """
        try:
            # Format the quality reflection prompt
            reflection_prompt = QUALITY_REFLECTION_PROMPT.format(
                response_content=response_content,
                original_question=original_question
            )
            
            # Generate quality assessment using LLM
            assessment_response = self.llm_client.generate_text(
                prompt=reflection_prompt,
                chat_history=[],
                max_output_tokens=400,
                temperature=0.2  # Low temperature for consistent evaluation
            )
            
            if not assessment_response:
                self.logger.error("Failed to get quality assessment from LLM")
                return self._default_quality_assessment()
            
            # Parse the assessment response
            assessment_result = self._parse_quality_assessment(assessment_response)
            
            # Validate and enhance the assessment
            return self._validate_assessment(assessment_result, response_content, response_type)
            
        except Exception as e:
            self.logger.error(f"Error assessing quality: {e}")
            return self._default_quality_assessment()
    
    def _parse_quality_assessment(self, assessment_response: str) -> Dict[str, Any]:
        """
        Parse the LLM quality assessment response.
        
        Args:
            assessment_response: Raw response from LLM
            
        Returns:
            Parsed assessment data
        """
        try:
            # Try to extract JSON from response
            response_clean = assessment_response.strip()
            
            # Handle cases where response might contain extra text
            if "{" in response_clean:
                json_start = response_clean.find("{")
                json_end = response_clean.rfind("}") + 1
                json_str = response_clean[json_start:json_end]
            else:
                json_str = response_clean
            
            # Parse JSON
            result = json.loads(json_str)
            
            return {
                "needs_enhancement": result.get("needs_enhancement", False),
                "enhancement_feedback": result.get("enhancement_feedback"),
                "quality_score": float(result.get("quality_score", 0.7)),
                "strengths": result.get("strengths", []),
                "weaknesses": result.get("weaknesses", [])
            }
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.warning(f"Failed to parse quality assessment: {e}")
            self.logger.debug(f"Raw response: {assessment_response}")
            
            # Fallback parsing
            response_lower = assessment_response.lower()
            
            needs_enhancement = any(keyword in response_lower for keyword in [
                "needs enhancement", "needs improvement", "should be enhanced", 
                "could be better", "requires improvement"
            ])
            
            return {
                "needs_enhancement": needs_enhancement,
                "enhancement_feedback": assessment_response if needs_enhancement else None,
                "quality_score": 0.6 if needs_enhancement else 0.8,
                "strengths": [],
                "weaknesses": []
            }
    
    def _validate_assessment(self, assessment: Dict[str, Any], response_content: str, response_type: str) -> Dict[str, Any]:
        """
        Validate and enhance the quality assessment.
        
        Args:
            assessment: Initial assessment from LLM
            response_content: Original response content
            response_type: Type of response
            
        Returns:
            Validated and enhanced assessment
        """
        # Validate quality score
        quality_score = assessment.get("quality_score", 0.7)
        quality_score = max(0.0, min(1.0, quality_score))  # Clamp to [0, 1]
        
        # Apply quality threshold
        if quality_score < self.quality_threshold and not assessment.get("needs_enhancement"):
            assessment["needs_enhancement"] = True
            if not assessment.get("enhancement_feedback"):
                assessment["enhancement_feedback"] = (
                    f"The response quality score ({quality_score:.2f}) is below the threshold "
                    f"({self.quality_threshold}). Please improve clarity, completeness, and helpfulness."
                )
        
        # Validate enhancement feedback
        if assessment.get("needs_enhancement") and not assessment.get("enhancement_feedback"):
            assessment["enhancement_feedback"] = (
                "The response could be improved for better clarity and educational value."
            )
        
        # Add response-type specific validation
        if response_type == "roadmap_content":
            assessment = self._validate_roadmap_quality(assessment, response_content)
        elif response_type == "lesson_response":
            assessment = self._validate_lesson_quality(assessment, response_content)
        
        return assessment
    
    def _validate_roadmap_quality(self, assessment: Dict[str, Any], roadmap_content: str) -> Dict[str, Any]:
        """
        Add roadmap-specific quality validation.
        
        Args:
            assessment: Current assessment
            roadmap_content: Roadmap content to validate
            
        Returns:
            Enhanced assessment with roadmap-specific feedback
        """
        # Check for roadmap structure elements
        required_elements = ["goal", "phase", "timeline", "resource"]
        missing_elements = []
        
        content_lower = roadmap_content.lower()
        for element in required_elements:
            if element not in content_lower:
                missing_elements.append(element)
        
        if missing_elements and not assessment.get("needs_enhancement"):
            assessment["needs_enhancement"] = True
            existing_feedback = assessment.get("enhancement_feedback", "")
            roadmap_feedback = f"The roadmap should include: {', '.join(missing_elements)}."
            assessment["enhancement_feedback"] = f"{existing_feedback} {roadmap_feedback}".strip()
        
        return assessment
    
    def _validate_lesson_quality(self, assessment: Dict[str, Any], lesson_response: str) -> Dict[str, Any]:
        """
        Add lesson-specific quality validation.
        
        Args:
            assessment: Current assessment
            lesson_response: Lesson response to validate
            
        Returns:
            Enhanced assessment with lesson-specific feedback
        """
        # Check response length (too short might not be helpful)
        if len(lesson_response) < 100:
            if not assessment.get("needs_enhancement"):
                assessment["needs_enhancement"] = True
                assessment["enhancement_feedback"] = (
                    "The response seems too brief. Please provide more detailed explanation "
                    "and examples to help the student understand better."
                )
        
        return assessment
    
    def _default_quality_assessment(self) -> Dict[str, Any]:
        """
        Return default quality assessment when LLM fails.
        
        Returns:
            Default assessment data
        """
        return {
            "needs_enhancement": False,  # Safe default to avoid blocking
            "enhancement_feedback": None,
            "quality_score": 0.7,
            "strengths": [],
            "weaknesses": []
        }