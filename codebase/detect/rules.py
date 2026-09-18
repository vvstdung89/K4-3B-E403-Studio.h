"""Rule-based detection of still-unanswered student questions.

No AI call here — this is the CP2 baseline. Originally also filtered on a
literal '?' in content, no reply_to in the pack, and a time threshold, but
that literal-'?' check was found to systematically miss real Vietnamese
questions phrased without one ("cho mình hỏi... nhỉ", "vậy ạ") — confirmed
against eval/testcases/'s golden set, where it excluded 8/10 real questions
in one case. Deliberately narrowed to ONLY exclude bot messages now; every
human message becomes an AI-review candidate, letting ai_decide/'s graph
model (which already reasons about is_question and still_needs_attention
with full context) make that judgment instead of a crude keyword check.

  SOLVED HERE:
  - bot messages wrongly counted as questions -> excluded via is_bot == False

  DEFERRED TO ai_decide/ (CP3) -- everything else: is this even a question,
  was it answered (same thread or elsewhere), is it a duplicate of another
  student's question.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from data.loader import Message


@dataclass(frozen=True)
class Candidate:
    message: Message
    reason: str
    hours_since_posted: float


@dataclass(frozen=True)
class DetectionBreakdown:
    """Per-message funnel behind find_unanswered_questions's final
    candidate list. Only one exclusion now (bot messages) -- built for the
    dashboard's "what did rule-based detection actually do" view;
    find_unanswered_questions's own behavior/contract is unchanged, it's
    just this breakdown's .candidates field now."""

    total_messages: int
    bot_messages: int
    candidates: list[Candidate]


def explain_detection(
    messages: list[Message],
    now: datetime,
    min_hours_unanswered: float = 4.0,  # unused -- kept for signature compatibility with existing callers
) -> DetectionBreakdown:
    bot_messages = 0
    candidates: list[Candidate] = []
    for m in messages:
        if m.is_bot:
            bot_messages += 1
            continue

        hours = (now - m.created_at).total_seconds() / 3600
        candidates.append(
            Candidate(
                message=m,
                reason=f"non-bot message, {hours:.1f}h old",
                hours_since_posted=hours,
            )
        )

    candidates.sort(key=lambda c: c.hours_since_posted, reverse=True)
    return DetectionBreakdown(
        total_messages=len(messages),
        bot_messages=bot_messages,
        candidates=candidates,
    )


def find_unanswered_questions(
    messages: list[Message],
    now: datetime,
    min_hours_unanswered: float = 4.0,
) -> list[Candidate]:
    return explain_detection(messages, now, min_hours_unanswered).candidates
