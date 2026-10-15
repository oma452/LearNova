"""
Prompt templates for request classification.
"""

REQUEST_CLASSIFICATION_PROMPT = """
You are an educational AI assistant for a learning platform. Your task is to classify student requests into one of three categories:

CATEGORIES:
1. "roadmap" - Requests for career guidance, learning paths, course recommendations, or educational roadmaps
2. "lesson_question" - Questions about specific lessons, course content, homework help, or study materials
3. "irrelevant" - Questions unrelated to education, personal matters, inappropriate content, or off-topic requests

CLASSIFICATION RULES:
- Focus on the core intent of the request
- If there's any educational component, prefer "lesson_question" over "irrelevant"
- Only classify as "roadmap" if explicitly asking for guidance, planning, or recommendations
- Be strict about "irrelevant" - only use for clearly non-educational content

EXAMPLES:
- "What is photosynthesis?" → lesson_question
- "Can you help me plan my computer science career?" → roadmap
- "What's the weather today?" → irrelevant
- "I need help with my math homework" → lesson_question
- "What courses should I take to become a doctor?" → roadmap
- "Tell me a joke" → irrelevant

USER REQUEST: "{user_message}"

Analyze the request and respond with ONLY a JSON object in this exact format:
{{
    "request_type": "roadmap|lesson_question|irrelevant",
    "confidence_score": 0.95,
    "reasoning": "Brief explanation of classification"
}}
"""

ROADMAP_CLASSIFICATION_PROMPT = """
You are analyzing a student request to determine if it's asking for a roadmap or learning guidance.

ROADMAP INDICATORS:
- Career planning questions
- Course selection guidance
- Learning path recommendations
- Skill development roadmaps
- Educational goal planning
- "What should I study to..."
- "How do I become..."
- "What's the best way to..."

USER REQUEST: "{user_message}"

Is this a roadmap request? Respond with ONLY "YES" or "NO" followed by confidence (0.0-1.0):
Format: YES 0.95 or NO 0.85
"""