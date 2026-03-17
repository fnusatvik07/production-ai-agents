"""
supervisor.py
~~~~~~~~~~~~~
LangGraph tutoring supervisor with long-term student memory and scaffolded HITL.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.types import interrupt, Command
from pydantic import BaseModel
from typing_extensions import TypedDict

from .memory.spaced_repetition import (
    ConceptCard,
    get_due_reviews,
    quality_from_hints,
    update_card,
)

logger = logging.getLogger(__name__)

MAX_HINTS = 3


# ── State ──────────────────────────────────────────────────────────────────────

class TutoringState(TypedDict):
    messages: Annotated[list, add_messages]
    student_id: str
    question: str
    topic: str
    concept_id: str

    # Memory
    student_profile: dict[str, Any]
    due_reviews: list[dict]
    relevant_memories: list[str]

    # Tutoring
    subject: Literal["math", "code", "science", "general"]
    hints_given: int
    student_correct: bool
    explanation: str

    # Output
    response: str
    mastery_update: dict[str, Any] | None


# ── LLM ───────────────────────────────────────────────────────────────────────

def get_llm() -> ChatAnthropic:
    return ChatAnthropic(model="claude-sonnet-4-6", temperature=0.3, max_tokens=2048)


# ── Nodes ─────────────────────────────────────────────────────────────────────

async def recall_student_context(state: TutoringState, store: BaseStore) -> dict:
    """Load student profile, due reviews, and relevant past struggles."""
    namespace = ("student", state["student_id"])

    # Search for relevant memories
    memories = store.search(namespace, query=state["question"], limit=5)
    relevant = [m.value.get("content", "") for m in memories if isinstance(m.value, dict)]

    # Check for due reviews
    all_cards_items = store.search(namespace, query="concept_card", limit=50)
    all_cards = []
    for item in all_cards_items:
        if isinstance(item.value, dict) and "concept_id" in item.value:
            all_cards.append(ConceptCard.from_dict(item.value))

    due = get_due_reviews(all_cards, limit=3)

    # Student profile
    profile_items = store.search(namespace, query="student profile preferences", limit=1)
    profile = profile_items[0].value if profile_items else {"preferences": "unknown"}

    logger.info(
        "Student %s: %d relevant memories, %d due reviews",
        state["student_id"], len(relevant), len(due)
    )

    return {
        "student_profile": profile,
        "due_reviews": [c.to_dict() for c in due],
        "relevant_memories": relevant,
    }


async def classify_topic(state: TutoringState) -> dict:
    """Classify question into subject area and identify concept."""
    llm = get_llm()

    class TopicClassification(BaseModel):
        subject: Literal["math", "code", "science", "general"]
        concept_id: str  # slug like "recursion", "quadratic_equations"
        topic: str       # human-readable

    structured_llm = llm.with_structured_output(TopicClassification)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Classify this student question into a subject area and identify the core concept being asked about."),
        ("human", "{question}"),
    ])

    result = await (prompt | structured_llm).ainvoke({"question": state["question"]})
    return {
        "subject": result.subject,
        "concept_id": result.concept_id,
        "topic": result.topic,
    }


async def check_due_reviews(state: TutoringState) -> dict:
    """If there are overdue reviews, proactively bring them up before answering."""
    if state["due_reviews"]:
        due_list = ", ".join(c["concept_id"] for c in state["due_reviews"])
        logger.info("Student %s has overdue reviews: %s", state["student_id"], due_list)
    return {}


async def generate_tutoring_response(state: TutoringState) -> dict:
    """Generate the expert answer for the subject. Uses scaffolded hint approach."""
    llm = get_llm()

    # Build context from memories
    memory_context = "\n".join(f"- {m}" for m in state["relevant_memories"][:3])
    profile_context = json.dumps(state["student_profile"])

    # Subject-specific system prompts
    subject_prompts = {
        "code": "You are an expert programming tutor. Focus on understanding over memorization. Use concrete code examples.",
        "math": "You are a patient math tutor. Build from first principles. Show your reasoning step by step.",
        "science": "You are an engaging science tutor. Connect concepts to real-world phenomena.",
        "general": "You are a helpful academic tutor with broad knowledge.",
    }

    system_prompt = subject_prompts.get(state["subject"], subject_prompts["general"])

    # Add student context
    if memory_context:
        system_prompt += f"\n\nWhat you know about this student:\n{memory_context}"

    # SCAFFOLDED HINT LOOP — up to MAX_HINTS interruptions
    hints_given = 0
    student_correct = False

    for hint_num in range(1, MAX_HINTS + 1):
        # Generate hint (getting progressively more revealing)
        hint_prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", """Student question: {question}

This is hint #{hint_num} of {max_hints}.
- Hint 1: Give a guiding question that points toward the answer
- Hint 2: Give a partial explanation
- Hint 3: Give a nearly complete explanation with one step left for the student

Generate hint #{hint_num}. Do NOT give the full answer yet."""),
        ])

        hint_response = await (hint_prompt | llm).ainvoke({
            "question": state["question"],
            "hint_num": hint_num,
            "max_hints": MAX_HINTS,
        })

        hint_text = hint_response.content

        # HITL: pause and wait for student response
        student_input = interrupt({
            "kind": "hint_response",
            "hint_number": hint_num,
            "hint": hint_text,
            "question": state["question"],
            "prompt": "Try to answer, or ask for another hint.",
        })

        hints_given = hint_num
        student_attempt = student_input.get("attempt", "")

        # Evaluate student's attempt
        if student_attempt:
            eval_prompt = ChatPromptTemplate.from_messages([
                ("system", "Evaluate if the student's attempt demonstrates understanding of the concept. Be lenient — credit partial understanding."),
                ("human", "Question: {question}\nCorrect concept: {concept}\nStudent attempt: {attempt}"),
            ])

            class EvalResult(BaseModel):
                correct: bool
                understanding_level: Literal["correct", "partial", "incorrect"]
                feedback: str

            eval_llm = llm.with_structured_output(EvalResult)
            eval_result = await (eval_prompt | eval_llm).ainvoke({
                "question": state["question"],
                "concept": state["concept_id"],
                "attempt": student_attempt,
            })

            if eval_result.correct or eval_result.understanding_level == "correct":
                student_correct = True
                break

        if student_input.get("want_more_hints") is False:
            break

    # Generate full explanation after hints
    final_prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Now provide the complete, thorough explanation for: {question}"),
    ])
    final_response = await (final_prompt | llm).ainvoke({"question": state["question"]})

    return {
        "hints_given": hints_given,
        "student_correct": student_correct,
        "explanation": final_response.content,
        "response": final_response.content,
    }


async def update_student_memory(state: TutoringState, store: BaseStore) -> dict:
    """Update spaced repetition card and store session memory."""
    namespace = ("student", state["student_id"])

    # Update spaced repetition card
    card_key = f"card_{state['concept_id']}"
    card_items = store.search(namespace, query=state["concept_id"], limit=1)

    if card_items and isinstance(card_items[0].value, dict) and "concept_id" in card_items[0].value:
        card = ConceptCard.from_dict(card_items[0].value)
    else:
        card = ConceptCard(
            concept_id=state["concept_id"],
            student_id=state["student_id"],
        )

    quality = quality_from_hints(
        hints_needed=state["hints_given"],
        total_hints=MAX_HINTS,
        correct=state["student_correct"],
    )
    updated_card = update_card(card, quality)
    store.put(namespace, key=card_key, value=updated_card.to_dict())

    # Store episodic memory of this session
    session_memory = {
        "content": f"Asked about {state['concept_id']} ({state['topic']}). "
                   f"{'Understood' if state['student_correct'] else 'Struggled'} after {state['hints_given']} hints. "
                   f"Mastery: {updated_card.mastery_score:.2f}",
        "concept_id": state["concept_id"],
        "mastery_after": updated_card.mastery_score,
        "hints_used": state["hints_given"],
        "correct": state["student_correct"],
    }
    import time
    store.put(namespace, key=f"session_{int(time.time())}", value=session_memory)

    mastery_update = {
        "concept_id": state["concept_id"],
        "new_mastery": updated_card.mastery_score,
        "next_review_date": updated_card.next_review_date.isoformat(),
        "interval_days": updated_card.interval_days,
    }

    logger.info(
        "Updated mastery for %s/%s: %.2f → next review in %d days",
        state["student_id"], state["concept_id"],
        updated_card.mastery_score, updated_card.interval_days,
    )

    return {"mastery_update": mastery_update}


# ── Graph ──────────────────────────────────────────────────────────────────────

def build_tutoring_graph(store: BaseStore | None = None):
    if store is None:
        store = InMemoryStore()

    async def _recall(state: TutoringState) -> dict:
        return await recall_student_context(state, store)

    async def _update_memory(state: TutoringState) -> dict:
        return await update_student_memory(state, store)

    builder = StateGraph(TutoringState)
    builder.add_node("recall_student_context", _recall)
    builder.add_node("classify_topic", classify_topic)
    builder.add_node("check_due_reviews", check_due_reviews)
    builder.add_node("generate_tutoring_response", generate_tutoring_response)
    builder.add_node("update_student_memory", _update_memory)

    builder.add_edge(START, "recall_student_context")
    builder.add_edge("recall_student_context", "classify_topic")
    builder.add_edge("classify_topic", "check_due_reviews")
    builder.add_edge("check_due_reviews", "generate_tutoring_response")
    builder.add_edge("generate_tutoring_response", "update_student_memory")
    builder.add_edge("update_student_memory", END)

    from langgraph.checkpoint.memory import InMemorySaver
    return builder.compile(checkpointer=InMemorySaver(), store=store)
