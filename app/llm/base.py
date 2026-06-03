"""Provider-agnostic interface for question generation and answer scoring.

Every concrete provider (offline stub, Anthropic, OpenAI) implements this small
surface. The web layer only ever talks to `LLMProvider`, so swapping models — or
running with no key at all — never touches application code.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class GeneratedQuestion:
    text: str
    skill: str  # the competency the question probes, e.g. "system design"


@dataclass
class AxisScore:
    axis_id: str
    score: int  # 1-5
    reason: str


@dataclass
class ScoredAnswer:
    axis_scores: List[AxisScore]
    overall: float  # 1-5 weighted mean
    percent: int  # 0-100
    band: str
    summary: str  # one-paragraph written feedback
    strengths: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)

    def axis_map(self) -> Dict[str, int]:
        return {a.axis_id: a.score for a in self.axis_scores}


class LLMProvider(abc.ABC):
    """Two responsibilities: invent role-specific questions, and grade answers."""

    name: str = "base"

    @abc.abstractmethod
    def generate_questions(
        self, job_description: str, count: int = 5
    ) -> List[GeneratedQuestion]:
        ...

    @abc.abstractmethod
    def score_answer(
        self, job_description: str, question: str, answer: str
    ) -> ScoredAnswer:
        ...
