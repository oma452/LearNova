from typing import TypedDict, Literal, Optional, List, Dict, Any


class ChatbotState(TypedDict):
    # Input/Output
    user_message: str
    final_response: str
    
    # Classification
    request_type: Literal["roadmap", "lesson_question", "irrelevant"]
    confidence_score: float
    
    # Lesson Q&A
    lesson_context: Optional[List[Dict[str, Any]]]
    lesson_response: Optional[str]
    
    # Roadmap Generation
    roadmap_approved: Optional[bool]
    roadmap_content: Optional[str]
    
    # Reflection & Quality Control
    needs_enhancement: bool
    enhancement_feedback: Optional[str]
    revision_count: int
    
    # Metadata
    student_id: str
    session_id: str
    timestamp: str