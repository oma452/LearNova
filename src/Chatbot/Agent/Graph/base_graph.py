from abc import ABC, abstractmethod
from langgraph.graph import StateGraph
from src.Helpers.config import get_settings

class BaseGraph(ABC):
    """Base class for ChatBot graphs"""
    
    def __init__(self):
        self.graph: StateGraph = None
        self.settings = get_settings()
    
    @abstractmethod
    def build_graph(self) -> StateGraph:
        """Build the graph structure"""
        pass
    
    def get_graph(self) -> StateGraph:
        """Get the compiled graph"""
        if self.graph is None:
            self.graph = self.build_graph()
        return self.graph