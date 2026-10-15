"""
Prompt templates for quality reflection and enhancement.
"""

QUALITY_REFLECTION_PROMPT = """
You are a quality assessment expert for educational content. Evaluate the provided response for quality, accuracy, and helpfulness.

EVALUATION CRITERIA:
1. ACCURACY: Is the information correct and factual?
2. COMPLETENESS: Does it fully address the student's question?
3. CLARITY: Is it easy to understand for the target student level?
4. RELEVANCE: Does it stay focused on the educational topic?
5. HELPFULNESS: Will this genuinely help the student learn?

RESPONSE TO EVALUATE:
"{response_content}"

ORIGINAL QUESTION:
"{original_question}"

Analyze the response and provide feedback in this exact JSON format:
{{
    "needs_enhancement": true/false,
    "enhancement_feedback": "Specific suggestions for improvement or null if no enhancement needed",
    "quality_score": 0.85,
    "strengths": ["list", "of", "strengths"],
    "weaknesses": ["list", "of", "weaknesses"]
}}

Guidelines:
- Set needs_enhancement to true if quality_score < 0.8
- Provide actionable enhancement_feedback if improvements are needed
- Be constructive and specific in feedback
- Consider the educational context and student needs
"""

ENHANCEMENT_PROMPT = """
You are an educational content enhancement specialist. Improve the given response based on the provided feedback.

ORIGINAL RESPONSE:
"{original_response}"

ENHANCEMENT FEEDBACK:
"{enhancement_feedback}"

ORIGINAL QUESTION:
"{original_question}"

ENHANCEMENT GOALS:
- Address all points mentioned in the feedback
- Maintain educational accuracy and relevance
- Improve clarity and helpfulness
- Keep the response appropriate for students
- Preserve any correct information from the original

Provide the enhanced response in clear, educational language that directly helps the student understand the topic better.

ENHANCED RESPONSE:
"""