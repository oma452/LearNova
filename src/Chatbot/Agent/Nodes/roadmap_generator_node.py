"""
Roadmap Generator Node - Generates personalized career/learning roadmaps.
"""

import logging
from typing import Dict, Any, Optional
from src.Chatbot.Agent.Nodes.base_node import BaseNode
from src.Chatbot.Agent.State.agent_state import ChatbotState
from src.Chatbot.Agent.Prompts.generation_prompts import ROADMAP_GENERATION_PROMPT
from src.Stores.LLM.Providers.openai_provider import OpenAIProvider
from src.Models.services.classroom_service import ClassRoomService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class RoadmapGeneratorNode(BaseNode):
    """
    Node to generate personalized career/learning roadmaps.
    
    This node creates detailed, actionable roadmaps based on:
    1. Student's request and goals
    2. Student's current academic context (subjects, grade level)
    3. Educational best practices and career guidance
    
    Input: user_message, student_id, roadmap_approved
    Output: roadmap_content
    """
    
    def __init__(self, llm_client: OpenAIProvider, session: Optional[AsyncSession] = None):
        """
        Initialize the roadmap generator node.
        
        Args:
            llm_client: OpenAI provider instance for text generation
            session: Optional database session for student context
        """
        self.llm_client = llm_client
        self.session = session
        self.logger = logger
        if session:
            self.classroom_service = ClassRoomService(session)
        else:
            self.classroom_service = None
        
    async def execute(self, state: ChatbotState) -> ChatbotState:
        """
        Execute the roadmap generation logic.
        
        Args:
            state: Current chatbot state
            
        Returns:
            Updated state with roadmap_content
        """
        try:
            self.logger.info("Executing roadmap generator node")
            
            # Check if roadmap generation was approved
            roadmap_approved = state.get("roadmap_approved", False)
            if not roadmap_approved:
                self.logger.info("Roadmap generation not approved, skipping")
                state["roadmap_content"] = None
                return state
            
            # Get user message and student ID from state
            user_message = state.get("user_message", "").strip()
            student_id = state.get("student_id", "")
            
            if not user_message:
                self.logger.warning("Empty user message provided for roadmap generation")
                state["roadmap_content"] = (
                    "I need more details about your career goals or learning objectives "
                    "to create a personalized roadmap for you."
                )
                return state
            
            # Get student context if available
            student_context = await self._get_student_context(student_id)
            
            # Generate personalized roadmap
            roadmap_content = await self._generate_roadmap(user_message, student_id, student_context)
            
            # Update state with generated roadmap
            state["roadmap_content"] = roadmap_content
            
            self.logger.info("Successfully generated roadmap content")
            return state
            
        except Exception as e:
            self.logger.error(f"Error in roadmap generator: {e}")
            # Fallback roadmap content
            state["roadmap_content"] = (
                "I encountered an issue while creating your personalized roadmap. "
                "Please try again later or contact support if the problem persists."
            )
            return state
    
    async def _get_student_context(self, student_id: str) -> Dict[str, Any]:
        """
        Get student's academic context for personalized roadmap generation.
        
        Args:
            student_id: Student's unique identifier
            
        Returns:
            Dictionary containing student's academic context
        """
        context = {
            "grade_level": None,
            "subjects": [],
            "current_classrooms": [],
            "academic_focus": None
        }
        
        try:
            if not self.classroom_service or not student_id:
                return context
            
            # Get student's current classrooms
            classrooms = await self.classroom_service.get_student_classrooms(student_id)
            
            if classrooms:
                context["current_classrooms"] = classrooms
                
                # Extract grade level (assuming consistent across classrooms)
                if classrooms[0].get('grade_level'):
                    context["grade_level"] = classrooms[0]['grade_level']
                
                # Extract subjects
                subjects = []
                for classroom in classrooms:
                    if classroom.get('subject_name'):
                        subjects.append(classroom['subject_name'])
                context["subjects"] = list(set(subjects))  # Remove duplicates
                
                # Determine academic focus based on subjects
                context["academic_focus"] = self._determine_academic_focus(subjects)
            
            self.logger.info(f"Retrieved context for student {student_id}: {context}")
            return context
            
        except Exception as e:
            self.logger.error(f"Error getting student context: {e}")
            return context
    
    def _determine_academic_focus(self, subjects: list) -> Optional[str]:
        """
        Determine student's academic focus based on enrolled subjects.
        
        Args:
            subjects: List of subject names
            
        Returns:
            Academic focus area or None
        """
        if not subjects:
            return None
        
        # Define subject categories
        stem_subjects = {'mathematics', 'physics', 'chemistry', 'biology', 'computer science', 'engineering'}
        humanities_subjects = {'history', 'literature', 'philosophy', 'languages', 'english', 'social studies'}
        arts_subjects = {'art', 'music', 'drama', 'design', 'visual arts', 'performing arts'}
        business_subjects = {'economics', 'business', 'accounting', 'finance', 'management'}
        
        subjects_lower = [s.lower() for s in subjects]
        
        # Count subjects in each category
        stem_count = sum(1 for s in subjects_lower if any(stem in s for stem in stem_subjects))
        humanities_count = sum(1 for s in subjects_lower if any(hum in s for hum in humanities_subjects))
        arts_count = sum(1 for s in subjects_lower if any(art in s for art in arts_subjects))
        business_count = sum(1 for s in subjects_lower if any(bus in s for bus in business_subjects))
        
        # Determine predominant focus
        max_count = max(stem_count, humanities_count, arts_count, business_count)
        
        if max_count == 0:
            return "General Education"
        elif stem_count == max_count:
            return "STEM (Science, Technology, Engineering, Mathematics)"
        elif humanities_count == max_count:
            return "Humanities and Social Sciences"
        elif arts_count == max_count:
            return "Arts and Creative Studies"
        elif business_count == max_count:
            return "Business and Economics"
        else:
            return "Interdisciplinary Studies"
    
    async def _generate_roadmap(self, user_message: str, student_id: str, student_context: Dict[str, Any]) -> str:
        """
        Generate personalized roadmap using LLM.
        
        Args:
            user_message: Student's roadmap request
            student_id: Student's ID
            student_context: Student's academic context
            
        Returns:
            Generated roadmap content
        """
        try:
            # Enhance the prompt with student context
            enhanced_prompt = self._enhance_prompt_with_context(user_message, student_id, student_context)
            
            # Generate roadmap using LLM
            roadmap_prompt = ROADMAP_GENERATION_PROMPT.format(
                user_message=enhanced_prompt,
                student_id=student_id
            )
            
            response = self.llm_client.generate_text(
                prompt=roadmap_prompt,
                chat_history=[],
                max_output_tokens=1500,  # Longer output for detailed roadmaps
                temperature=0.4  # Balanced creativity for comprehensive content
            )
            
            if not response or not response.strip():
                self.logger.warning("LLM failed to generate roadmap content")
                return self._generate_fallback_roadmap(user_message, student_context)
            
            return response.strip()
            
        except Exception as e:
            self.logger.error(f"Error generating roadmap with LLM: {e}")
            return self._generate_fallback_roadmap(user_message, student_context)
    
    def _enhance_prompt_with_context(self, user_message: str, student_id: str, student_context: Dict[str, Any]) -> str:
        """
        Enhance the user message with student context for better roadmap generation.
        
        Args:
            user_message: Original student request
            student_id: Student's ID
            student_context: Student's academic context
            
        Returns:
            Enhanced message with context
        """
        context_parts = [user_message]
        
        if student_context.get("grade_level"):
            context_parts.append(f"Current Grade Level: {student_context['grade_level']}")
        
        if student_context.get("subjects"):
            subjects_str = ", ".join(student_context["subjects"])
            context_parts.append(f"Current Subjects: {subjects_str}")
        
        if student_context.get("academic_focus"):
            context_parts.append(f"Academic Focus: {student_context['academic_focus']}")
        
        return "\n".join(context_parts)
    
    def _generate_fallback_roadmap(self, user_message: str, student_context: Dict[str, Any]) -> str:
        """
        Generate a basic fallback roadmap when LLM fails.
        
        Args:
            user_message: Student's request
            student_context: Student's academic context
            
        Returns:
            Basic roadmap content
        """
        grade_level = student_context.get("grade_level", "your current level")
        academic_focus = student_context.get("academic_focus", "your area of interest")
        
        return f"""
# Learning Roadmap: {user_message}

## Goal Overview
Based on your request and current academic standing at {grade_level}, here's a personalized learning roadmap.

## Getting Started
1. **Assess Current Knowledge**: Evaluate what you already know in {academic_focus}
2. **Set Clear Goals**: Define specific, measurable objectives
3. **Create Study Schedule**: Dedicate consistent time for learning

## Learning Path

### Phase 1: Foundation Building (1-3 months)
- Review fundamentals in your current subjects
- Strengthen core skills and knowledge gaps
- Develop good study habits and learning strategies

### Phase 2: Skill Development (3-6 months)
- Focus on practical applications of your learning
- Seek hands-on projects and real-world experience
- Connect with mentors or professionals in your field of interest

### Phase 3: Advanced Learning (6-12 months)
- Pursue advanced topics and specializations
- Consider extracurricular activities or competitions
- Prepare for next academic level or career steps

## Next Steps
1. Start with Phase 1 activities
2. Track your progress regularly
3. Adjust the roadmap based on your interests and opportunities
4. Seek guidance from teachers and career counselors

## Additional Resources
- Consult with your school's career counseling services
- Explore online learning platforms relevant to your interests
- Connect with professionals in your field of interest

Remember: This roadmap is a starting point. Adapt it based on your unique interests, strengths, and opportunities!
"""