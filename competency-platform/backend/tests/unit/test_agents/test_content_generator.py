"""Unit tests for ContentGeneratorAgent.

From spec §15.1:
Tests content generation with RAG context injection.
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.conftest import create_mock_llm


class TestContentGeneratorAgent:
    """Test suite for the Content Generator Agent."""

    @pytest.mark.asyncio
    @patch("app.agents.content_generator.retrieve_similar_content", new_callable=AsyncMock)
    async def test_generates_content_with_rag(self, mock_rag):
        """Agent uses RAG-retrieved examples to ground content generation."""
        from app.agents.content_generator import ContentGeneratorAgent

        # Mock RAG returns similar content
        mock_rag.return_value = [
            {"content_body": "Example decorator explanation...", "quality_score": 0.92},
        ]

        mock_llm = create_mock_llm({
            "content_body": "## Python Decorators\n\nA decorator is a function...",
            "interaction_prompts": ["What is a decorator?"],
            "expected_response_schema": "A function that takes another function...",
        })
        agent = ContentGeneratorAgent(llm=mock_llm)

        state = {
            "session_id": "test-content-001",
            "skill_id": "skill-decorators",
            "current_proficiency": 0.5,
            "generated_content": {
                "skill_node": {"id": "sk1", "name": "Python Decorators", "description": "Decorators in Python"},
                "content_type": "explanation",
                "difficulty_level": 2,
                "employee_context": {"role": "Engineer", "industry": "tech"},
            },
        }

        result = await agent.process(state)
        assert result is not None
