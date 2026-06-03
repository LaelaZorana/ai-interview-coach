"""The interview-answer scoring rubric and aggregation logic.

Answers are graded on four independent axes, each 1-5, mirroring the per-axis
"score + reasoning" idiom used across the rest of the portfolio. Keeping the
rubric and aggregation in one dependency-free module makes the scoring logic
unit-testable without touching the web layer or any LLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

SCORE_MIN = 1
SCORE_MAX = 5


@dataclass(frozen=True)
class Axis:
    id: str
    label: str
    description: str
    weight: float


# Order matters: it drives both prompt construction and UI rendering.
AXES: List[Axis] = [
    Axis(
        id="relevance",
        label="Relevance",
        description="Does the answer directly address the question that was asked?",
        weight=1.0,
    ),
    Axis(
        id="specificity",
        label="Specificity",
        description="Concrete details, real examples, numbers — not vague generalities.",
        weight=1.0,
    ),
    Axis(
        id="structure",
        label="Structure",
        description="Clear, logical flow (e.g. situation -> action -> result).",
        weight=0.75,
    ),
    Axis(
        id="impact",
        label="Impact",
        description="Demonstrates measurable outcomes, ownership, and business value.",
        weight=1.25,
    ),
]

AXIS_IDS = [a.id for a in AXES]
AXIS_BY_ID: Dict[str, Axis] = {a.id: a for a in AXES}


def clamp_score(value: object) -> int:
    """Coerce an arbitrary model-supplied value into a valid 1-5 integer.

    The real LLM occasionally returns floats, numeric strings, or out-of-range
    values; we never want that to crash scoring, so we clamp defensively.
    """
    try:
        v = int(round(float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return SCORE_MIN
    return max(SCORE_MIN, min(SCORE_MAX, v))


def weighted_overall(axis_scores: Dict[str, int]) -> float:
    """Weighted mean of the per-axis scores, rounded to one decimal (1-5 scale).

    Missing axes are treated as the minimum score so an incomplete payload can
    never inflate the result.
    """
    total_weight = sum(a.weight for a in AXES)
    if total_weight == 0:
        return float(SCORE_MIN)
    acc = 0.0
    for axis in AXES:
        acc += axis.weight * clamp_score(axis_scores.get(axis.id, SCORE_MIN))
    return round(acc / total_weight, 1)


def to_percent(overall: float) -> int:
    """Map a 1-5 overall score onto a friendly 0-100 scale for the UI."""
    span = SCORE_MAX - SCORE_MIN
    if span == 0:
        return 100
    pct = (overall - SCORE_MIN) / span * 100
    return int(round(max(0.0, min(100.0, pct))))


def band(overall: float) -> str:
    """Human-readable verdict band for an overall 1-5 score."""
    if overall >= 4.5:
        return "Outstanding"
    if overall >= 3.5:
        return "Strong"
    if overall >= 2.5:
        return "Solid, needs polish"
    if overall >= 1.5:
        return "Needs work"
    return "Off track"
