"""Data schemas for LangGraph State, LLM Structured Output, and Eval Benchmark JSON.
"""

from __future__ import annotations

from typing import TypedDict, Optional, Any
from pydantic import BaseModel, Field

from data.loader import Message
from detect.rules import Candidate


class CandidateAnalysisOutput(BaseModel):
    """Structured output returned by LLM classifier node."""
    is_question: bool = Field(
        description="Whether the message contains a genuine question or request for help from a student."
    )
    still_needs_attention: bool = Field(
        description="True if the question has NOT been satisfactorily answered by any subsequent messages or LabCoach. False if answered."
    )
    target_labcoach: Optional[str] = Field(
        default="General / Duty LabCoach",
        description="Extracted target LabCoach if tagged (e.g. '@Lab Coach - Duy Bách'), or 'General / Duty LabCoach' if untagged/general."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0 for the decision."
    )
    summary: str = Field(
        description="Concise 1-2 sentence summary of the student's question."
    )
    rationale: str = Field(
        description="Short explanation of why this question still needs attention or was marked resolved based on thread context."
    )


class GraphState(TypedDict, total=False):
    """State maintained across LangGraph nodes."""
    candidate: Candidate
    context_messages: list[Message]
    raw_prompt: str
    raw_response: str
    analysis: Optional[CandidateAnalysisOutput]
    decision: Optional[Any]


class EvalMessageClassification(BaseModel):
    """Structured NLU output returned by AI model when classifying each message in a benchmark batch."""
    is_standalone_question: bool = Field(
        description="True if the message is a genuine standalone question or help request from a student. False if it is an announcement, status update, thank-you closing message, or non-question reply."
    )
    response_status: str = Field(
        default="no_visible_response",
        description="Status of response: 'answered' (satisfactorily answered by reply/peer/coach), 'partial_or_deferred' (answered incorrectly, partially, or deferred), or 'no_visible_response' (unanswered/no reply)."
    )
    responder: str = Field(
        default="none",
        description="Who provided the answer: 'user' (student/peer/labcoach user), 'labcoach' (bot/labcoach), or 'none' (if unanswered)."
    )
    needs_labcoach_review: bool = Field(
        default=True,
        description="True if the question is unanswered, partially answered, or needs LabCoach review. False if satisfactorily answered."
    )
    rationale: str = Field(
        default="",
        description="Short natural language explanation of the classification."
    )



# --- SCHEMAS FOR EVAL BENCHMARK OUTPUT (matching eval/K4-H11.json expected_output) ---

class QuestionEvalItem(BaseModel):
    input_index: int
    msg_id: str
    guild: str
    channel: str
    created_at_vn: str
    is_question: bool = True
    label: str  # "answered" | "no_visible_response" | "partial_or_deferred"
    response_status: str  # "answered" | "no_visible_response" | "partial_or_deferred"
    responder: str  # "user" | "labcoach" | "none"
    needs_labcoach_review: bool


class EvalCounts(BaseModel):
    answered: int = 0
    partial_or_deferred: int = 0
    no_visible_response: int = 0
    ignored_messages: int = 0


class EvalBenchmarkOutputSchema(BaseModel):
    scope: str = "input_only"
    message_count: int
    question_count: int
    questions: list[QuestionEvalItem]
    data_quality_flags: list[str] = Field(default_factory=list)
    counts: EvalCounts
