# Content Generator Agent + RAG Pipeline

## Plan 10 of 21 — Competency Intelligence Platform MVP

---

### Objective

Implement the Content Generator Agent and the RAG (Retrieval-Augmented Generation) pipeline. The agent generates learning content (explanations, scenarios, quizzes, dialogues) calibrated to learner proficiency, using pgvector similarity search to retrieve validated high-quality content as few-shot examples. Includes OpenAI embeddings, content embedding storage, and the full RAG retrieval flow.

### Prerequisites

- **Plan 2** (Database Schema) — ContentItem table with pgvector embedding column
- **Plan 5** (LangGraph Orchestrator) — BaseAgent, LLM Router
- **Plan 8** (Learning State Manager) — Employee context retrieval

### Spec References

| Section | Content |
|---------|---------|
| §3 Content Generator Agent | Full agent spec |
| §18.1 RAG Pipeline Sub-Component | embed_content(), retrieve_similar_content() (Listing 20) |

---

### Files to Create/Modify

```
competency-platform/backend/app/
├── agents/
│   └── content_generator.py     # Agent implementation
├── core/
│   └── embeddings.py            # RAG pipeline (pgvector operations)
└── prompts/
    └── content_generator.txt    # Content generation prompt templates
```

---

### Detailed Implementation Steps

#### Step 1: RAG Pipeline (from §18.1 Listing 20)

```python
# app/core/embeddings.py
"""RAG Pipeline — pgvector content retrieval and embedding.

From spec §18.1 Listing 20:
Used by Content Generator Agent and Competency Architect Agent
to ground LLM outputs in validated organisational knowledge.
"""
from langchain_openai import OpenAIEmbeddings
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy import text
from app.core.config import settings

embeddings_model = OpenAIEmbeddings(
    model=settings.OPENAI_EMBEDDING_MODEL,  # text-embedding-3-small
    dimensions=settings.EMBEDDING_DIMENSIONS,  # 1536
)


async def embed_content(content: str) -> list[float]:
    """Generate embedding vector for content text."""
    return await embeddings_model.aembed_query(content)


async def retrieve_similar_content(
    session: AsyncSession,
    query: str,
    skill_id: str,
    content_type: str,
    top_k: int = 3,
    min_quality: float = 0.82,
) -> list[dict]:
    """Retrieve similar validated content from pgvector.
    
    Uses cosine distance (<=> operator) for similarity search.
    Only returns content with quality_score >= min_quality threshold.
    """
    query_vec = await embed_content(query)
    result = await session.exec(text("""
        SELECT id, content_body, quality_score, difficulty_level,
               1 - (embedding <=> :qv::vector) AS similarity
        FROM content_items
        WHERE skill_id = :sid
          AND content_type = :ctype
          AND quality_score >= :mq
          AND embedding IS NOT NULL
        ORDER BY embedding <=> :qv::vector
        LIMIT :tk
    """), {"qv": str(query_vec), "sid": skill_id,
           "ctype": content_type, "mq": min_quality, "tk": top_k})
    return [dict(row) for row in result]


async def embed_and_store(
    session: AsyncSession,
    content_item_id: str,
    content_text: str,
):
    """Generate and store embedding for a content item."""
    embedding = await embed_content(content_text)
    await session.exec(text("""
        UPDATE content_items SET embedding = :emb::vector
        WHERE id = :cid
    """), {"emb": str(embedding), "cid": content_item_id})
    await session.commit()
```

#### Step 2: Content Generator Agent

```python
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

    async def process(self, state: AgentState) -> dict:
        """Generate content for the current learning module."""
        session_id = state.get("session_id", "")
        skill_info = state.get("generated_content", {}).get("skill_node", {})
        content_type = state.get("generated_content", {}).get("content_type", "explanation")
        difficulty = state.get("generated_content", {}).get("difficulty_level", 3)
        employee_ctx = state.get("generated_content", {}).get("employee_context", {})

        # Get appropriate LLM based on content type
        llm = get_llm_for_content(content_type)

        # RAG: Retrieve similar validated content as few-shot examples
        # (requires db_session — injected via graph context)
        rag_examples = "No previous content available."
        # In production, retrieve from pgvector here

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
        import json
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

        self.logger.info(
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
    return await content_generator(state)
```

---

### Configuration & Environment

```env
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
```

---

### Verification Criteria

1. **Embedding generation**: `embed_content("test")` returns 1536-dim float list
2. **RAG retrieval**: Insert content with embedding → `retrieve_similar_content()` returns it
3. **Content generation**: Agent produces Markdown content with interaction prompts
4. **Content type routing**: SCENARIO uses GPT-4o, EXPLANATION uses GPT-4o-mini
5. **Few-shot**: RAG examples included in prompt when available
6. **Output structure**: Returns content_body, interaction_prompts, expected_response_schema

### Notes & Gotchas

- **Embedding cost**: text-embedding-3-small is cheapest; ~$0.02/1M tokens
- **HNSW index**: Required for fast similarity search at scale; created in Plan 2
- **Content caching**: Approved content stored with embedding for future RAG retrieval
- **Temperature**: 0.7 for creative content generation (higher than evaluation agents)
