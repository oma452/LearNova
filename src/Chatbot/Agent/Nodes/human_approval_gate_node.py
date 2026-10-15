"""
Human Approval Gate Node - Implements human-in-the-loop checkpoint for roadmap generation.
"""

import logging
from typing import Any, Dict, Optional
from langgraph.errors import NodeInterrupt
from src.Chatbot.Agent.Nodes.base_node import BaseNode
from src.Chatbot.Agent.State.agent_state import ChatbotState

logger = logging.getLogger(__name__)


class HumanApprovalGateNode(BaseNode):
    """
    Node that acts as a checkpoint before roadmap generation.
    
    This node interrupts the flow and waits for human confirmation
    before proceeding with roadmap generation using LangGraph's interrupt mechanism.
    
    Input: request_type, user_message
    Output: roadmap_approved
    """
    
    def __init__(self, timeout_seconds: int = 300):
        """
        Initialize the human approval gate node.
        
        Args:
            timeout_seconds: Maximum time to wait for approval (default: 5 minutes)
        """
        self.logger = logger
        self.timeout_seconds = timeout_seconds
        
    async def execute(self, state: ChatbotState) -> ChatbotState:
        """
        Execute the human approval gate logic with LangGraph interrupt.
        
        This node creates an interrupt point for human approval using
        LangGraph's NodeInterrupt mechanism.
        
        Args:
            state: Current chatbot state containing request_type and user_message
            
        Returns:
            Updated state with roadmap_approved flag
            
        Raises:
            NodeInterrupt: When human approval is required
        """
        try:
            self.logger.info("Executing human approval gate for roadmap generation")
            
            # Get request details from state
            request_type = state.get("request_type", "")
            user_message = state.get("user_message", "").strip()
            student_id = state.get("student_id", "unknown")
            confidence_score = state.get("confidence_score", 0.0)
            
            # Validate that this is indeed a roadmap request
            if request_type != "roadmap":
                self.logger.warning(f"Human approval gate called for non-roadmap request: {request_type}")
                state["roadmap_approved"] = False
                return state
            
            # Check if approval was already provided (resuming from interrupt)
            if "roadmap_approved" in state and state["roadmap_approved"] is not None:
                approval_status = state["roadmap_approved"]
                self.logger.info(f"Resuming with approval status: {approval_status}")
                return state
            
            # Prepare approval request data
            approval_request = self._prepare_approval_request(state)
            
            # Log the approval request details
            self.logger.info(
                f"Requesting human approval for roadmap generation:\n"
                f"Student ID: {student_id}\n"
                f"Request: {user_message[:100]}{'...' if len(user_message) > 100 else ''}\n"
                f"Confidence: {confidence_score:.2f}"
            )
            
            # Trigger LangGraph interrupt - execution will pause here until human input
            raise NodeInterrupt(approval_request)
            
        except NodeInterrupt:
            # Re-raise NodeInterrupt to maintain LangGraph flow
            raise
        except Exception as e:
            self.logger.error(f"Error in human approval gate: {e}")
            # Default to not approved on error to maintain safety
            state["roadmap_approved"] = False
            return state
    
    def _prepare_approval_request(self, state: ChatbotState) -> Dict[str, Any]:
        """
        Prepare the approval request data for the interrupt.
        
        Args:
            state: Current chatbot state
            
        Returns:
            Approval request data for human review
        """
        user_message = state.get("user_message", "")
        student_id = state.get("student_id", "unknown")
        confidence_score = state.get("confidence_score", 0.0)
        
        # Create a comprehensive approval request
        approval_request = {
            "type": "roadmap_approval_request",
            "student_id": student_id,
            "user_message": user_message,
            "confidence_score": confidence_score,
            "timestamp": self._get_current_timestamp(),
            "timeout_seconds": self.timeout_seconds,
            "metadata": {
                "request_type": state.get("request_type"),
                "session_id": state.get("session_id"),
                "user_context": self._extract_user_context(state)
            },
            "approval_options": {
                "approve": "Generate personalized roadmap for this student",
                "deny": "Reject roadmap generation request",
                "modify": "Request modifications to the request before proceeding"
            },
            "instructions": (
                "This student is requesting a personalized learning roadmap. "
                "Please review the request and student context to determine if "
                "roadmap generation should proceed."
            )
        }
        
        return approval_request
    
    def _extract_user_context(self, state: ChatbotState) -> Dict[str, Any]:
        """
        Extract relevant user context for approval decision.
        
        Args:
            state: Current chatbot state
            
        Returns:
            User context information
        """
        return {
            "request_complexity": "high" if len(state.get("user_message", "")) > 200 else "normal",
            "student_id": state.get("student_id", "unknown"),
            "confidence_score": state.get("confidence_score", 0.0)
        }
    
    def _get_current_timestamp(self) -> str:
        """
        Get current timestamp for approval request.
        
        Returns:
            ISO format timestamp string
        """
        from datetime import datetime
        return datetime.utcnow().isoformat()
    
    def process_approval_response(self, state: ChatbotState, approval_data: Dict[str, Any]) -> ChatbotState:
        """
        Process the human approval response and update state.
        
        This method is called by the LangGraph framework when resuming
        execution after receiving human input.
        
        Args:
            state: Current chatbot state
            approval_data: Human approval response data
            
        Returns:
            Updated state with approval decision
        """
        try:
            approval_decision = approval_data.get("decision", "deny")
            approval_reason = approval_data.get("reason", "")
            
            # Process different approval decisions
            if approval_decision == "approve":
                state["roadmap_approved"] = True
                self.logger.info("Human approval granted for roadmap generation")
            elif approval_decision == "deny":
                state["roadmap_approved"] = False
                self.logger.info(f"Human approval denied: {approval_reason}")
            elif approval_decision == "modify":
                state["roadmap_approved"] = False
                self.logger.info(f"Modification requested: {approval_reason}")
            else:
                # Default to deny for unknown decisions
                state["roadmap_approved"] = False
                self.logger.warning(f"Unknown approval decision: {approval_decision}")
            
            return state
            
        except Exception as e:
            self.logger.error(f"Error processing approval response: {e}")
            # Default to denial on error
            state["roadmap_approved"] = False
            return state
    
    def handle_timeout(self, state: ChatbotState) -> ChatbotState:
        """
        Handle approval timeout scenario.
        
        This method is called when no human response is received
        within the timeout period.
        
        Args:
            state: Current chatbot state
            
        Returns:
            Updated state with timeout handling
        """
        self.logger.warning(f"Human approval timeout after {self.timeout_seconds} seconds")
        
        # Default to denial on timeout for safety
        state["roadmap_approved"] = False
        
        return state