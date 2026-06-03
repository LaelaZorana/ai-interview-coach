"""Deterministic, offline LLM stub.

This is the default provider when no API key is configured. It is not a random
mock: it does light NLP on the inputs (skill extraction from the job
description, heuristic features of the answer) so the questions are genuinely
role-specific and the scores respond sensibly to answer quality. The same input
always yields the same output, which makes the whole product demoable and the
scoring logic unit-testable without a network call.
"""
from __future__ import annotations

import hashlib
import re
from typing import Dict, List

from app.llm.base import (
    AxisScore,
    GeneratedQuestion,
    LLMProvider,
    ScoredAnswer,
)
from app.rubric import AXES, band, clamp_score, to_percent, weighted_overall

# Curated skill vocabulary -> the interview question that probes it. Order is the
# priority in which we surface questions when several skills are detected.
_SKILL_QUESTIONS: List[tuple] = [
    ("system design", "Walk me through how you would design a scalable system for a core feature in this role. What are the main trade-offs?"),
    ("distributed systems", "Describe a distributed-systems problem you've tackled. How did you reason about consistency, latency, and failure?"),
    ("api", "Tell me about an API you designed or owned. How did you think about versioning, contracts, and backward compatibility?"),
    ("database", "How do you decide on a data model and indexing strategy under real production load? Give a concrete example."),
    ("python", "Describe a non-trivial Python codebase you've worked on. What did you do to keep it maintainable as it grew?"),
    ("javascript", "Walk me through a complex front-end feature you shipped. How did you manage state and performance?"),
    ("react", "Tell me about a React application you built. How did you structure components and handle data fetching?"),
    ("machine learning", "Describe an ML model you took from prototype to production. How did you evaluate it and monitor it after launch?"),
    ("data", "Tell me about a time you used data to change a decision. What was the analysis and what was the outcome?"),
    ("cloud", "Describe your experience deploying and operating services in the cloud. How did you handle reliability and cost?"),
    ("security", "Walk me through how you think about securing a service. Describe a vulnerability or risk you mitigated."),
    ("leadership", "Tell me about a time you led a project end to end. How did you align the team and measure success?"),
    ("stakeholder", "Describe a situation where you had to manage conflicting stakeholder priorities. How did you resolve it?"),
    ("communication", "Tell me about a time you had to explain something technical to a non-technical audience."),
    ("agile", "How do you operate within an agile team? Describe a time a process change you drove improved delivery."),
    ("testing", "Walk me through your approach to testing. Describe a bug that better tests would have caught."),
    ("performance", "Tell me about a time you diagnosed and fixed a serious performance problem. What was your process?"),
    ("product", "Describe a product decision you influenced. How did you balance user needs against constraints?"),
]

# Always-useful behavioural questions, used to top up when few skills match.
_FALLBACK_QUESTIONS: List[tuple] = [
    ("ownership", "Tell me about a project you're most proud of. What was your specific contribution and impact?"),
    ("failure", "Describe a time something you owned failed or went wrong. What did you learn and change afterwards?"),
    ("collaboration", "Tell me about a time you disagreed with a teammate. How did you reach a good outcome?"),
    ("growth", "What's a skill you deliberately developed in the last year, and how did you go about it?"),
    ("motivation", "Why are you interested in this role specifically, and what would you want to accomplish in your first 90 days?"),
]

_STAR_HINTS = ("result", "impact", "increased", "reduced", "improved", "led", "shipped", "delivered", "grew", "saved", "%")
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")
_FILLER_RE = re.compile(r"\b(um+|uh+|like|kinda|sort of|stuff|things|whatever)\b", re.I)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z+#.\-]*")


def _stable_unit(*parts: str) -> float:
    """A deterministic value in [0, 1) derived from the inputs.

    Used to add small, reproducible variation so two different answers of similar
    quality don't always land on an identical integer.
    """
    h = hashlib.sha256("␟".join(parts).encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


class StubProvider(LLMProvider):
    name = "stub"

    # -- question generation -------------------------------------------------

    def generate_questions(
        self, job_description: str, count: int = 5
    ) -> List[GeneratedQuestion]:
        count = max(1, min(10, count))
        jd = job_description.lower()

        questions: List[GeneratedQuestion] = []
        used_skills = set()
        for skill, text in _SKILL_QUESTIONS:
            if skill in jd and skill not in used_skills:
                questions.append(GeneratedQuestion(text=text, skill=skill))
                used_skills.add(skill)
            if len(questions) >= count:
                break

        # Top up with behavioural staples (deterministic order) if needed.
        for skill, text in _FALLBACK_QUESTIONS:
            if len(questions) >= count:
                break
            if skill not in used_skills:
                questions.append(GeneratedQuestion(text=text, skill=skill))
                used_skills.add(skill)

        return questions[:count]

    # -- answer scoring ------------------------------------------------------

    def score_answer(
        self, job_description: str, question: str, answer: str
    ) -> ScoredAnswer:
        features = self._features(job_description, question, answer)
        axis_scores = [
            AxisScore(
                axis_id=axis.id,
                score=features[axis.id]["score"],
                reason=features[axis.id]["reason"],
            )
            for axis in AXES
        ]
        score_map: Dict[str, int] = {a.axis_id: a.score for a in axis_scores}
        overall = weighted_overall(score_map)

        strengths = [
            f["praise"] for f in features.values() if f["score"] >= 4 and f.get("praise")
        ]
        improvements = [
            f["fix"] for f in features.values() if f["score"] <= 3 and f.get("fix")
        ]

        return ScoredAnswer(
            axis_scores=axis_scores,
            overall=overall,
            percent=to_percent(overall),
            band=band(overall),
            summary=self._summary(overall, strengths, improvements),
            strengths=strengths,
            improvements=improvements,
        )

    # -- internals -----------------------------------------------------------

    def _features(self, jd: str, question: str, answer: str) -> Dict[str, dict]:
        ans = answer.strip()
        words = _WORD_RE.findall(ans)
        n_words = len(words)
        lower = ans.lower()

        has_numbers = bool(_NUMBER_RE.search(ans))
        n_star = sum(1 for h in _STAR_HINTS if h in lower)
        n_filler = len(_FILLER_RE.findall(ans))
        n_sentences = max(1, ans.count(".") + ans.count("!") + ans.count("?"))
        first_person = sum(1 for w in words if w.lower() in ("i", "my", "we", "our"))

        # overlap between the answer and the question's content words (relevance signal)
        q_terms = {w.lower() for w in _WORD_RE.findall(question) if len(w) > 4}
        a_terms = {w.lower() for w in words}
        overlap = len(q_terms & a_terms)
        jitter = _stable_unit(question, answer)

        # --- relevance ---
        if n_words < 8:
            rel, rel_reason = 1, "The answer is too short to address the question."
            rel_praise, rel_fix = "", "Actually answer the question with a complete response."
        else:
            rel = 2 + min(2, overlap) + (1 if jitter > 0.5 else 0)
            rel_reason = (
                f"Touches {overlap} key term(s) from the question; "
                + ("stays on topic." if overlap else "connection to the question is thin.")
            )
            rel_praise = "Directly engages with what was asked." if rel >= 4 else ""
            rel_fix = "" if rel >= 4 else "Mirror the question's keywords and answer it head-on."

        # --- specificity ---
        spec = 1
        if n_words >= 40:
            spec += 1
        if has_numbers:
            spec += 2
        if n_filler == 0 and n_words >= 25:
            spec += 1
        spec_reason = (
            ("Includes concrete figures. " if has_numbers else "No concrete numbers or metrics. ")
            + (f"{n_filler} filler phrase(s) detected." if n_filler else "Crisp wording.")
        )
        spec_praise = "Grounded in concrete, quantified detail." if spec >= 4 else ""
        spec_fix = "" if spec >= 4 else "Add specific numbers, names, and examples instead of generalities."

        # --- structure ---
        avg_sentence = n_words / n_sentences
        struct = 2
        if 8 <= avg_sentence <= 28:
            struct += 1
        if n_sentences >= 3:
            struct += 1
        if n_star >= 2:
            struct += 1
        struct_reason = (
            f"{n_sentences} sentence(s), ~{avg_sentence:.0f} words each; "
            + ("clear situation/action/result shape." if n_star >= 2 else "lacks an explicit result.")
        )
        struct_praise = "Well organised, easy to follow." if struct >= 4 else ""
        struct_fix = "" if struct >= 4 else "Use a Situation -> Task -> Action -> Result structure."

        # --- impact ---
        imp = 1
        if n_star >= 1:
            imp += 1
        if has_numbers:
            imp += 1
        if any(h in lower for h in ("led", "owned", "drove", "shipped", "delivered")):
            imp += 1
        if first_person and has_numbers:
            imp += 1
        imp_reason = (
            ("Shows measurable outcomes and ownership." if (has_numbers and n_star) else "Outcome and personal ownership are unclear.")
        )
        imp_praise = "Demonstrates clear, owned impact." if imp >= 4 else ""
        imp_fix = "" if imp >= 4 else "State the measurable result and your personal role in achieving it."

        return {
            "relevance": {"score": clamp_score(rel), "reason": rel_reason, "praise": rel_praise, "fix": rel_fix},
            "specificity": {"score": clamp_score(spec), "reason": spec_reason, "praise": spec_praise, "fix": spec_fix},
            "structure": {"score": clamp_score(struct), "reason": struct_reason, "praise": struct_praise, "fix": struct_fix},
            "impact": {"score": clamp_score(imp), "reason": imp_reason, "praise": imp_praise, "fix": imp_fix},
        }

    @staticmethod
    def _summary(overall: float, strengths: List[str], improvements: List[str]) -> str:
        verdict = band(overall)
        head = f"{verdict} answer (scored {overall:.1f}/5). "
        if strengths:
            head += "Strengths: " + "; ".join(strengths[:2]) + ". "
        if improvements:
            head += "To improve: " + "; ".join(improvements[:2]) + "."
        elif not strengths:
            head += "Add detail and a concrete result to lift every axis."
        return head.strip()
