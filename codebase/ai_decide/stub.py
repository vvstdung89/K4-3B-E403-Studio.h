"""CP3 LangGraph AI Decision Engine — one batch LLM call per tick.

Preserves `decide(candidates) -> list[Decision]`.
"""

from __future__ import annotations

import os
from typing import Any

from ai_decide.graph import create_ai_decision_graph
from ai_decide.types import Decision
from detect.rules import Candidate


def decide(
    candidates: list[Candidate],
    all_messages: list[Any] | None = None,
    provider: str | None = None,
    model_name: str | None = None,
) -> list[Decision]:
    """Classify the whole candidate batch in a single LangGraph invoke.

    Fail-open: on API errors, every candidate still_needs_attention=True.
    Never answers the student.
    """
    if not candidates:
        return []

    active_provider = provider or os.getenv("LLM_PROVIDER", "openai")
    app_graph = create_ai_decision_graph(provider=active_provider, model_name=model_name)

    try:
        final_state = app_graph.invoke(
            {
                "candidates": candidates,
                "context_messages": all_messages or [],
            }
        )
        decisions = final_state.get("decisions") if isinstance(final_state, dict) else None
        if decisions:
            return decisions
    except Exception as exc:
        return [
            Decision(
                candidate=candidate,
                still_needs_attention=True,
                confidence=0.5,
                rationale=f"[LangGraph batch fallback: {exc}] Kept for manual review.",
            )
            for candidate in candidates
        ]

    return [
        Decision(
            candidate=candidate,
            still_needs_attention=True,
            confidence=0.5,
            rationale="[LangGraph batch] Pipeline completed without decision output.",
        )
        for candidate in candidates
    ]
