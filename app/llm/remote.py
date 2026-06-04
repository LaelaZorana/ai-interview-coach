"""Real LLM providers (Anthropic and OpenAI).

Both share the same prompt construction and JSON parsing; only the transport
differs. SDKs are imported lazily so the package, and the whole offline demo,
has no hard dependency on them. If a call fails for any reason we fall back to
the deterministic stub rather than 500-ing the request.
"""
from __future__ import annotations

import json
import re
from typing import List

from app.llm.base import (
    AxisScore,
    GeneratedQuestion,
    LLMProvider,
    ScoredAnswer,
)
from app.llm.stub import StubProvider
from app.rubric import AXES, band, clamp_score, to_percent, weighted_overall

_JSON_RE = re.compile(r"\{.*\}", re.S)


def _questions_prompt(job_description: str, count: int) -> str:
    return (
        "You are an expert technical interviewer. Read the job description and "
        f"write exactly {count} role-specific interview questions that probe the "
        "most important competencies for this role. Mix technical and behavioural "
        "questions as appropriate.\n\n"
        f"JOB DESCRIPTION:\n{job_description}\n\n"
        "Respond with STRICT JSON only, no prose, in this shape:\n"
        '{"questions": [{"skill": "<competency>", "text": "<question>"}]}'
    )


def _scoring_prompt(job_description: str, question: str, answer: str) -> str:
    axis_lines = "\n".join(f"- {a.id}: {a.description}" for a in AXES)
    return (
        "You are a rigorous interview coach. Score the candidate's answer on each "
        "axis from 1 (poor) to 5 (excellent) and give a one-sentence reason per "
        "axis. Then write a short overall summary, plus concrete strengths and "
        "improvements.\n\n"
        f"AXES:\n{axis_lines}\n\n"
        f"JOB DESCRIPTION:\n{job_description}\n\n"
        f"QUESTION:\n{question}\n\n"
        f"CANDIDATE ANSWER:\n{answer}\n\n"
        "Respond with STRICT JSON only, no prose, in this shape:\n"
        '{"axes": {"<axis_id>": {"score": <1-5>, "reason": "<text>"}}, '
        '"summary": "<text>", "strengths": ["..."], "improvements": ["..."]}'
    )


def _extract_json(raw: str) -> dict:
    match = _JSON_RE.search(raw or "")
    if not match:
        raise ValueError("no JSON object found in model output")
    return json.loads(match.group(0))


class _RemoteProvider(LLMProvider):
    """Common parsing for providers that return free-text containing JSON."""

    def __init__(self) -> None:
        self._fallback = StubProvider()

    def _complete(self, prompt: str) -> str:  # pragma: no cover - network
        raise NotImplementedError

    def generate_questions(
        self, job_description: str, count: int = 5
    ) -> List[GeneratedQuestion]:
        count = max(1, min(10, count))
        try:
            data = _extract_json(self._complete(_questions_prompt(job_description, count)))
            out = [
                GeneratedQuestion(
                    text=str(q["text"]).strip(),
                    skill=str(q.get("skill", "general")).strip() or "general",
                )
                for q in data.get("questions", [])
                if str(q.get("text", "")).strip()
            ]
            if out:
                return out[:count]
        except Exception:
            pass
        # Any failure -> deterministic, never-empty fallback.
        return self._fallback.generate_questions(job_description, count)

    def score_answer(
        self, job_description: str, question: str, answer: str
    ) -> ScoredAnswer:
        try:
            data = _extract_json(
                self._complete(_scoring_prompt(job_description, question, answer))
            )
            axes_in = data.get("axes", {})
            axis_scores = [
                AxisScore(
                    axis_id=axis.id,
                    score=clamp_score(axes_in.get(axis.id, {}).get("score")),
                    reason=str(axes_in.get(axis.id, {}).get("reason", "")).strip()
                    or "No reason provided.",
                )
                for axis in AXES
            ]
            score_map = {a.axis_id: a.score for a in axis_scores}
            overall = weighted_overall(score_map)
            return ScoredAnswer(
                axis_scores=axis_scores,
                overall=overall,
                percent=to_percent(overall),
                band=band(overall),
                summary=str(data.get("summary", "")).strip() or band(overall),
                strengths=[str(s).strip() for s in data.get("strengths", []) if str(s).strip()],
                improvements=[str(s).strip() for s in data.get("improvements", []) if str(s).strip()],
            )
        except Exception:
            return self._fallback.score_answer(job_description, question, answer)


class AnthropicProvider(_RemoteProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__()
        self._api_key = api_key
        self._model = model

    def _complete(self, prompt: str) -> str:  # pragma: no cover - network
        import anthropic  # lazy import

        client = anthropic.Anthropic(api_key=self._api_key)
        msg = client.messages.create(
            model=self._model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(getattr(block, "text", "") for block in msg.content)


class OpenAIProvider(_RemoteProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__()
        self._api_key = api_key
        self._model = model

    def _complete(self, prompt: str) -> str:  # pragma: no cover - network
        from openai import OpenAI  # lazy import

        client = OpenAI(api_key=self._api_key)
        resp = client.chat.completions.create(
            model=self._model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""
