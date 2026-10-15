"""
Output Formatter Node - Formats final responses for delivery to users.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from src.Chatbot.Agent.Nodes.base_node import BaseNode
from src.Chatbot.Agent.State.agent_state import ChatbotState

logger = logging.getLogger(__name__)


class OutputFormatterNode(BaseNode):
    """
    Node to format final responses for delivery to users.
    
    This node takes the final content (lesson_response, roadmap_content, or 
    irrelevant_response) and formats it appropriately for the user interface, 
    adding structure, metadata, and educational suggestions.
    
    Input: lesson_response OR roadmap_content OR irrelevant_response
    Output: final_response (formatted for delivery)
    """
    
    def __init__(self):
        """
        Initialize the output formatter node.
        """
        self.logger = logger
        
    async def execute(self, state: ChatbotState) -> ChatbotState:
        """
        Execute the output formatting logic.
        
        Args:
            state: Current chatbot state
            
        Returns:
            Updated state with formatted final_response
        """
        try:
            self.logger.info("Executing output formatter node")
            
            # Determine response type and content
            response_content, response_type = self._get_response_content(state)
            
            if not response_content:
                self.logger.warning("No response content found for formatting")
                state["final_response"] = self._generate_error_response()
                return state
            
            # Format the response based on type
            if response_type == "lesson_response":
                formatted_response = self._format_lesson_response(response_content, state)
            elif response_type == "roadmap_content":
                formatted_response = self._format_roadmap_response(response_content, state)
            else:
                formatted_response = self._format_generic_response(response_content, state)
            
            # Add metadata and finalization
            formatted_response = self._add_response_metadata(formatted_response, state)
            
            # Set final response
            state["final_response"] = formatted_response
            
            self.logger.info(f"Formatted {response_type} for final delivery")
            return state
            
        except Exception as e:
            self.logger.error(f"Error in output formatting: {e}")
            state["final_response"] = self._generate_error_response()
            return state
    
    def _get_response_content(self, state: ChatbotState) -> tuple[Optional[str], str]:
        """
        Extract the response content to be formatted.
        
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
        
        # Check for irrelevant response
        irrelevant_response = state.get("irrelevant_response")
        if irrelevant_response and irrelevant_response.strip():
            return irrelevant_response.strip(), "irrelevant_response"
        
        # No content found
        return None, "unknown"
    
    def _format_lesson_response(self, lesson_content: str, state: ChatbotState) -> str:
        """
        Format lesson-specific responses.
        
        Args:
            lesson_content: The lesson response content
            state: Current chatbot state
            
        Returns:
            Formatted lesson response
        """
        # Get lesson context if available
        lesson_context = state.get("lesson_context", [])
        
        # Extract lesson title from the first context chunk if available
        lesson_title = "Lesson Content"
        if lesson_context and len(lesson_context) > 0:
            # lesson_context is a list of dictionaries, get title from first chunk
            first_chunk = lesson_context[0]
            if isinstance(first_chunk, dict):
                lesson_title = first_chunk.get("lesson_title", "Lesson Content")
        
        # Create formatted response
        formatted_response = f"""## 📚 {lesson_title}

{lesson_content}

---
*This response is based on your enrolled lesson content. If you have follow-up questions, feel free to ask!*
"""
        
        return formatted_response
    
    def _format_roadmap_response(self, roadmap_content: str, state: ChatbotState) -> str:
        """
        Format roadmap-specific responses.
        
        Args:
            roadmap_content: The roadmap content
            state: Current chatbot state
            
        Returns:
            Formatted roadmap response
        """
        # Check if roadmap was approved by human
        roadmap_approved = state.get("roadmap_approved", False)
        approval_status = "✅ **Approved**" if roadmap_approved else "⏳ **Pending Approval**"
        
        # Create formatted response
        formatted_response = f"""## 🗺️ Your Personalized Learning Roadmap

{approval_status}

{roadmap_content}

---
*This roadmap has been personalized based on your academic background and goals. You can ask for modifications or clarifications at any time.*
"""
        
        return formatted_response
    
    def _format_generic_response(self, content: str, state: ChatbotState) -> str:
        """
        Format generic responses.
        
        Args:
            content: The response content
            state: Current chatbot state
            
        Returns:
            Formatted generic response
        """
        # Determine if this is an irrelevant response
        request_type = state.get("request_type")
        
        if request_type == "irrelevant":
            return f"""## 💡 Educational Focus

{content}

---
*I'm here to help with your learning journey. Ask me about any academic topic, homework help, or study guidance!*
"""
        
        # Standard educational response
        return f"""## 📖 Educational Response

{content}

---
*Hope this helps with your learning! Feel free to ask follow-up questions or explore related topics.*
"""
    
    def _add_response_metadata(self, formatted_response: str, state: ChatbotState) -> str:
        """
        Add metadata and finalization to the response.
        
        Args:
            formatted_response: The formatted response content
            state: Current chatbot state
            
        Returns:
            Response with metadata
        """
        # Add timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Add session information if available
        session_info = []
        
        # Add enhancement information if response was enhanced
        revision_count = state.get("revision_count", 0)
        if revision_count > 0:
            session_info.append(f"Enhanced response (revision {revision_count})")
        
        # Add confidence information if available
        confidence_score = state.get("confidence_score")
        if confidence_score is not None:
            confidence_percentage = int(confidence_score * 100)
            session_info.append(f"Confidence: {confidence_percentage}%")
        
        # Build metadata footer
        metadata_parts = [f"Generated: {timestamp}"]
        if session_info:
            metadata_parts.extend(session_info)
        
        metadata_footer = f"\n\n<details><summary>Response Info</summary>\n\n{' | '.join(metadata_parts)}\n\n</details>"
        
        return formatted_response + metadata_footer
    
    def _generate_error_response(self) -> str:
        """
        Generate a fallback error response.
        
        Returns:
            Error response string
        """
        return """## ⚠️ Response Error

I apologize, but I encountered an issue while preparing your response. Please try asking your question again, or rephrase it if the problem persists.

If you continue to experience issues, please contact support for assistance.

---
*Error generated at: {timestamp}*
""".format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"))
    
    def _clean_content(self, content: str) -> str:
        """
        Clean and prepare content for formatting.
        
        Args:
            content: Raw content to clean
            
        Returns:
            Cleaned content
        """
        if not content:
            return ""
        
        # Remove excessive whitespace
        content = content.strip()
        
        # Normalize line endings
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        
        # Remove excessive blank lines (more than 2 consecutive)
        import re
        content = re.sub(r"\n{3,}", "\n\n", content)
        
        return content
    
    def _add_educational_suggestions(self, formatted_response: str, state: ChatbotState) -> str:
        """
        Add educational suggestions and next steps to the response.
        
        Args:
            formatted_response: Current formatted response
            state: Current chatbot state
            
        Returns:
            Response with educational suggestions
        """
        request_type = state.get("request_type")
        
        if request_type == "lesson_question":
            suggestions = """
### 💡 Next Steps
- Try practicing with similar problems
- Review related concepts in your lesson
- Ask for clarification on specific points
"""
        elif request_type == "roadmap_request":
            suggestions = """
### 💡 Getting Started
- Start with Phase 1 fundamentals
- Set up a study schedule
- Track your progress regularly
- Don't hesitate to ask for help along the way
"""
        else:
            suggestions = """
### 💡 Continue Learning
- Explore related topics
- Ask follow-up questions
- Practice what you've learned
"""
        
        return formatted_response + suggestions