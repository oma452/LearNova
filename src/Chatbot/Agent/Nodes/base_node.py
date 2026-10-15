"""
Base node class for all chatbot agent nodes.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from src.Chatbot.Agent.State.agent_state import ChatbotState


class BaseNode(ABC):
    """
    Base class for all chatbot agent nodes.
    
    All nodes must inherit from this class and implement the execute method.
    """
    
    @abstractmethod
    async def execute(self, state: ChatbotState) -> ChatbotState:
        """
        Execute the node logic.
        
        Args:
            state: Current chatbot state
            
        Returns:
            Updated chatbot state
        """
        pass
    
    def __call__(self, state: ChatbotState) -> ChatbotState:
        """
        Make the node callable.
        
        Args:
            state: Current chatbot state
            
        Returns:
            Result of execute method
        """
        return self.execute(state)