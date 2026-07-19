# app/agents/adaptive_tutor.py
"""Adaptive Tutor Agent — drives the live learning session.

From spec §3:
Role: Drives the live learning session. Presents content, interprets responses,
decides next interaction, maintains session coherence.

Inputs: session_state, employee_response, current_module, assessment_signal
Outputs: tutor_response, next_action (CONTINUE/REINFORCE/ADVANCE/COMPLETE/ESCALATE),
         difficulty_adjustment (delta: -1, 0, +1)

Tools: Read session state from Redis, trigger Content Generator
Memory Scope: Short-term (full session state in Redis; read at each invocation)
LLM: GPT-4o (dialogue coherence across turns; uses LangGraph memory)

Prompt Strategy: Socratic dialogue pattern.
- Always acknowledges response before correcting
- Does not give answers directly; asks guiding questions first
- Maintains persona as a senior domain expert
"""
import structlog
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from app.agents.base import BaseAgent
from app.graphs.state import AgentState
from app.services.llm_router import get_llm
from app.services.langsmith import get_runnable_config
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

logger = structlog.get_logger()


class TutorAction(str, Enum):
    CONTINUE = "CONTINUE"
    REINFORCE = "REINFORCE"
    ADVANCE = "ADVANCE"
    COMPLETE = "COMPLETE"
    ESCALATE = "ESCALATE"


SYSTEM_PROMPT = """You are an Adaptive Tutor Agent — a senior domain expert who guides learners through personalized learning sessions using Socratic dialogue.

## Your Persona
- You are a patient, encouraging senior expert in {skill_name}
- You have deep knowledge of {industry} industry applications
- You adapt your teaching style to the learner's level

## Socratic Dialogue Rules (STRICT)
1. ALWAYS acknowledge the employee's response first before any correction
2. NEVER give answers directly — ask guiding questions to lead them to understanding
3. If they're wrong, ask "What made you think that?" before correcting
4. If they're right, reinforce with "Exactly! And how does that connect to...?"
5. Use concrete examples from {industry} to illustrate points
6. Maintain continuity — reference what was discussed earlier in the session

## Current Session Context
- Skill: {skill_name} (Difficulty: {difficulty}/5)
- Session Interaction #{interaction_count}
- Current Score: {current_score}/100
- Mastery Level: {mastery_level}/5
- Assessment Signal: {assessment_signal}

## Previous Session Messages
{message_history}

## Current Content Being Taught
{current_content}

## Decision Logic (determine next_action)
- Score improving AND engagement high → ADVANCE (increase difficulty)
- Score stable, good understanding → CONTINUE (next content piece)
- Score low OR misconceptions detected → REINFORCE (same difficulty, different angle)
- Mastery threshold reached → COMPLETE (end session)
- Employee confused repeatedly → ESCALATE (flag for human intervention)

## Difficulty Adjustment
- If ADVANCE: suggest difficulty_adjustment = +1
- If REINFORCE: suggest difficulty_adjustment = -1
- Otherwise: difficulty_adjustment = 0

## Your Response Must Include
1. Acknowledgment of the employee's response
2. Feedback (Socratic — guide, don't tell)
3. Next question or content transition
4. Your recommendation for next_action and difficulty_adjustment
"""


class TutorOutput(BaseModel):
    tutor_response: str = Field(..., description="Next message to employee")
    next_action: TutorAction
    difficulty_adjustment: int = Field(default=0, ge=-1, le=1)
    reasoning: str = ""


class AdaptiveTutorAgent(BaseAgent):
    """Drives live learning sessions with Socratic dialogue."""

    def __init__(self, llm=None):
        super().__init__(agent_name="AdaptiveTutorAgent")
        self.custom_llm = llm

    async def process(self, state: AgentState) -> dict:
        session_id = state.get("session_id", "")
        messages = state.get("messages", [])
        content = state.get("generated_content", {})
        assessment = state.get("assessment_result", {})
        skill_info = content.get("skill_node", {})
        interaction_count = state.get("interaction_count", 0)

        # Build message history for context
        msg_history = self._format_message_history(messages[-10:])  # Last 10 messages

        system = SYSTEM_PROMPT.format(
            skill_name=skill_info.get("name", "Unknown"),
            industry=content.get("employee_context", {}).get("industry", "general"),
            difficulty=content.get("difficulty_level", 3),
            interaction_count=interaction_count,
            current_score=state.get("current_proficiency", 0),
            mastery_level=assessment.get("mastery_level", 0) if assessment else 0,
            assessment_signal=str(assessment) if assessment else "No assessment yet",
            message_history=msg_history,
            current_content=content.get("content_body", "")[:1000],
        )

        # Use the latest employee response
        latest_response = ""
        if messages:
            latest = messages[-1]
            if hasattr(latest, 'content'):
                latest_response = latest.content

        config = self.get_config(session_id)
        llm = self.custom_llm or get_llm(self.agent_name)

        result = await llm.ainvoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=f"Employee's response: {latest_response}\n\nProvide your tutor response, next_action, and difficulty_adjustment."),
            ],
            config=config,
        )

        # Parse tutor response
        tutor_response = result.content
        next_action, difficulty_adj = self._determine_action(state, assessment)

        logger.info(
            "tutor_response_generated",
            next_action=next_action,
            difficulty_adjustment=difficulty_adj,
            interaction=interaction_count,
        )

        return {
            "generated_content": {
                **content,
                "tutor_response": tutor_response,
                "next_action": next_action,
                "difficulty_adjustment": difficulty_adj,
            },
            "interaction_count": interaction_count + 1,
            "current_node": "deliver_to_tutor",
            "next_action": next_action,
        }

    def _determine_action(self, state: AgentState, assessment: dict) -> tuple[str, int]:
        """Determine next action based on assessment signals."""
        score = state.get("current_proficiency", 0)
        interaction_count = state.get("interaction_count", 0)
        composite = assessment.get("composite_score", 50) if assessment else 50

        if composite >= 75 and interaction_count >= 3:
            return "ADVANCE", 1
        elif composite < 45:
            return "REINFORCE", -1
        elif interaction_count >= 20:
            return "COMPLETE", 0
        else:
            return "CONTINUE", 0

    def _format_message_history(self, messages: list) -> str:
        lines = []
        for msg in messages:
            role = "Employee" if isinstance(msg, HumanMessage) else "Tutor"
            content = msg.content if hasattr(msg, 'content') else str(msg)
            lines.append(f"[{role}]: {content[:200]}")
        return "\n".join(lines) or "No previous messages."


# LangGraph node
adaptive_tutor = AdaptiveTutorAgent()


async def prepare_interaction_node(state: AgentState) -> dict:
    """LangGraph node wrapper for the Adaptive Tutor Agent."""
    return await adaptive_tutor(state)
