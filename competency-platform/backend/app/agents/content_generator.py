# app/agents/content_generator.py
"""Content Generator Agent — generates learning content calibrated to learner.

From spec §3:
Role: Generates learning content for a specific skill node, calibrated
to the learner's current proficiency and inferred modality preference.

Inputs: skill_node, content_type (EXPLANATION/SCENARIO/QUIZ/DIALOGUE),
        difficulty_level (1-5), employee_context, rag_context
Outputs: content_body (Markdown), interaction_prompts, expected_response_schema,
         metadata (ContentMetadata)

Tools: pgvector similarity search, Neo4j (related skill context)
Memory Scope: None (outputs routed to Content Reviewer before delivery)
LLM: GPT-4o for SCENARIO/DIALOGUE; GPT-4o-mini for EXPLANATION/QUIZ

Prompt Strategy: Few-shot with 2-3 retrieved similar high-quality content.
System prompt enforces: active voice, concrete examples from target industry.
"""
import structlog
import json
from app.agents.base import BaseAgent
from app.graphs.state import AgentState
from app.services.llm_router import get_llm_for_content
from app.services.langsmith import get_runnable_config
from app.core.embeddings import retrieve_similar_content
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a Content Generator Agent for an AI-powered competency learning platform.

Your role is to generate high-quality learning content for a specific skill.

## Content Type: {content_type}
## Skill: {skill_name}
## Description: {skill_description}
## Difficulty Level: {difficulty_level}/5
## Learning Strategy: {learning_strategy}
## Employee Context: Role={employee_role}, Industry={industry}

## Content Guidelines:
1. Use ACTIVE VOICE throughout
2. Include CONCRETE EXAMPLES from the {industry} industry
3. Stay strictly within the scope of "{skill_name}" — do not drift to adjacent topics
4. Calibrate complexity to difficulty level {difficulty_level}/5
5. Use Markdown formatting for readability

## Content Type Specific Rules:
- EXPLANATION: Teach the concept with examples. Include 2-3 interaction prompts for comprehension checks.
- SCENARIO: Create a realistic workplace scenario. Present a problem and ask the learner to solve it.
- QUIZ: Generate 3-5 questions with varying difficulty. Include expected response schemas.
- DIALOGUE: Create a Socratic dialogue where the learner must reason through a problem step-by-step.

## Similar High-Quality Content (Few-Shot Examples):
{rag_examples}

Generate content that is at least as good as the examples above.

## Output Requirements:
Return the content as a JSON with:
- content_body: The main content in Markdown
- interaction_prompts: List of questions/tasks embedded in content
- expected_response_schema: What a good response looks like for each prompt
"""


class ContentGeneratorAgent(BaseAgent):
    """Generates learning content with RAG-enhanced quality."""

    def __init__(self, llm=None):
        super().__init__(agent_name="ContentGeneratorAgent")
        self.custom_llm = llm

    async def process(self, state: AgentState) -> dict:
        """Generate content for the current learning module."""
        session_id = state.get("session_id", "")
        skill_info = state.get("generated_content", {}).get("skill_node", {})
        content_type = state.get("generated_content", {}).get("content_type", "explanation")
        difficulty = state.get("generated_content", {}).get("difficulty_level", 3)
        employee_ctx = state.get("generated_content", {}).get("employee_context", {})

        # Get appropriate LLM based on content type
        llm = self.custom_llm or get_llm_for_content(content_type)

        # RAG: Retrieve similar validated content as few-shot examples
        # (requires db_session — injected via graph context)
        rag_examples = "No previous content available."
        db_session = state.get("db_session")
        if db_session and skill_info.get("id"):
            try:
                similar = await retrieve_similar_content(
                    session=db_session,
                    query=skill_info.get("name", ""),
                    skill_id=skill_info.get("id"),
                    content_type=content_type,
                )
                if similar:
                    rag_examples = "\n\n".join([
                        f"Example (Quality Score: {item['quality_score']}):\n{item['content_body']}"
                        for item in similar
                    ])
            except Exception as e:
                logger.warning("rag_retrieval_failed", error=str(e))

        # Build prompt
        system = SYSTEM_PROMPT.format(
            content_type=content_type.upper(),
            skill_name=skill_info.get("name", "Unknown Skill"),
            skill_description=skill_info.get("description", ""),
            difficulty_level=difficulty,
            learning_strategy=skill_info.get("learning_strategy", "conceptual"),
            employee_role=employee_ctx.get("role", "general"),
            industry=employee_ctx.get("industry", "general"),
            rag_examples=rag_examples,
        )

        user_prompt = (
            f"Generate {content_type} content for the skill '{skill_info.get('name', '')}' "
            f"at difficulty level {difficulty}/5."
        )

        config = self.get_config(session_id)
        result = await llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=user_prompt)],
            config=config,
        )

        # Parse LLM output
        try:
            content_data = json.loads(result.content)
        except json.JSONDecodeError:
            content_data = {
                "content_body": result.content,
                "interaction_prompts": [],
                "expected_response_schema": {},
            }

        generated = {
            "content_body": content_data.get("content_body", result.content),
            "content_type": content_type,
            "difficulty_level": difficulty,
            "interaction_prompts": content_data.get("interaction_prompts", []),
            "expected_response_schema": content_data.get("expected_response_schema", {}),
            "skill_node": skill_info,
            "metadata": {
                "model_used": llm.model_name if hasattr(llm, 'model_name') else "unknown",
                "content_type": content_type,
            },
        }

        logger.info(
            "content_generated",
            content_type=content_type,
            skill=skill_info.get("name"),
            difficulty=difficulty,
        )

        return {
            "generated_content": generated,
            "current_node": "generate_content",
        }


# LangGraph node function
content_generator = ContentGeneratorAgent()


async def generate_content_node(state: AgentState) -> dict:
    """LangGraph node wrapper for the Content Generator Agent."""
    return await content_generator(state)
