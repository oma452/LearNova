from enum import Enum

class GraphNodeType(Enum):
    REQUEST_CLASSIFIER_NODE = "request_classifier_node"
    IRRELEVANT_HANDLER_NODE = "irrelevant_handler_node"
    HUMAN_APPROVAL_GATE_NODE = "human_approval_gate_node"
    LESSON_QA_NODE = "lesson_qa_node"
    ROADMAP_GENERATOR_NODE = "roadmap_generator_node"
    QUALITY_REFLECTION_NODE = "quality_reflection_node"
    ENHANCEMENT_NODE = "enhancement_node"
    OUTPUT_FORMATTER_NODE = "output_formatter_node"
    