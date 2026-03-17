"""
spaced_repetition.py
~~~~~~~~~~~~~~~~~~~~
SM-2 spaced repetition algorithm for concept review scheduling.
Tracks mastery per concept per student.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


# Response quality codes (matches SM-2 spec)
QUALITY_PERFECT = 5           # Perfect response, no hesitation
QUALITY_CORRECT_SLIGHT = 4   # Correct with slight hesitation
QUALITY_CORRECT_EFFORT = 3   # Correct after significant effort
QUALITY_INCORRECT_EASY = 2   # Incorrect but answer seemed easy on seeing it
QUALITY_INCORRECT = 1         # Incorrect, difficult to recall
QUALITY_BLACKOUT = 0          # Complete blackout

MIN_EASE_FACTOR = 1.3


@dataclass
class ConceptCard:
    """Tracks a student's mastery of one concept."""
    concept_id: str
    student_id: str
    repetition: int = 0
    ease_factor: float = 2.5
    interval_days: int = 1
    mastery_score: float = 0.0        # 0-1, our interpretation of SM-2 state
    next_review_date: date = field(default_factory=date.today)
    total_attempts: int = 0
    successful_attempts: int = 0

    @property
    def is_overdue(self) -> bool:
        return date.today() >= self.next_review_date

    @property
    def days_until_review(self) -> int:
        return (self.next_review_date - date.today()).days

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "student_id": self.student_id,
            "repetition": self.repetition,
            "ease_factor": round(self.ease_factor, 3),
            "interval_days": self.interval_days,
            "mastery_score": round(self.mastery_score, 3),
            "next_review_date": self.next_review_date.isoformat(),
            "total_attempts": self.total_attempts,
            "successful_attempts": self.successful_attempts,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConceptCard":
        obj = cls(
            concept_id=data["concept_id"],
            student_id=data["student_id"],
        )
        obj.repetition = data.get("repetition", 0)
        obj.ease_factor = data.get("ease_factor", 2.5)
        obj.interval_days = data.get("interval_days", 1)
        obj.mastery_score = data.get("mastery_score", 0.0)
        obj.next_review_date = date.fromisoformat(data.get("next_review_date", date.today().isoformat()))
        obj.total_attempts = data.get("total_attempts", 0)
        obj.successful_attempts = data.get("successful_attempts", 0)
        return obj


def update_card(card: ConceptCard, quality: int) -> ConceptCard:
    """
    Apply one SM-2 iteration to a concept card.

    Args:
        card: Current state of the concept card
        quality: Response quality (0-5)

    Returns:
        Updated concept card with new schedule
    """
    card.total_attempts += 1
    if quality >= 3:
        card.successful_attempts += 1

    # SM-2 ease factor update
    new_ef = card.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    card.ease_factor = max(MIN_EASE_FACTOR, new_ef)

    # Interval calculation
    if quality < 3:
        # Failed — restart sequence
        card.repetition = 0
        card.interval_days = 1
    else:
        if card.repetition == 0:
            card.interval_days = 1
        elif card.repetition == 1:
            card.interval_days = 6
        else:
            card.interval_days = round(card.interval_days * card.ease_factor)
        card.repetition += 1

    card.next_review_date = date.today() + timedelta(days=card.interval_days)

    # Mastery score: weighted by ease_factor and success rate
    success_rate = card.successful_attempts / max(1, card.total_attempts)
    ef_normalized = (card.ease_factor - MIN_EASE_FACTOR) / (4.0 - MIN_EASE_FACTOR)
    card.mastery_score = min(1.0, (success_rate * 0.6 + ef_normalized * 0.4))

    return card


def quality_from_hints(hints_needed: int, total_hints: int, correct: bool) -> int:
    """
    Convert hint usage into SM-2 quality score.

    Args:
        hints_needed: How many hints the student used
        total_hints: Maximum hints available
        correct: Whether they ultimately got it right
    """
    if not correct:
        return QUALITY_BLACKOUT if hints_needed == total_hints else QUALITY_INCORRECT

    ratio = hints_needed / max(1, total_hints)
    if ratio == 0:
        return QUALITY_PERFECT
    elif ratio <= 0.33:
        return QUALITY_CORRECT_SLIGHT
    elif ratio <= 0.66:
        return QUALITY_CORRECT_EFFORT
    else:
        return QUALITY_INCORRECT_EASY


def get_due_reviews(cards: list[ConceptCard], limit: int = 5) -> list[ConceptCard]:
    """Return cards due for review, sorted by most overdue first."""
    due = [c for c in cards if c.is_overdue]
    due.sort(key=lambda c: c.next_review_date)
    return due[:limit]
