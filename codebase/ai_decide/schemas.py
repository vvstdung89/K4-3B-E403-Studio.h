"""Data schemas for LangGraph State, LLM Structured Output, and Eval Benchmark JSON.
"""

from __future__ import annotations

from typing import TypedDict, Optional, Any, Literal
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
        description="Status of response: 'answered' (satisfactorily answered by reply/peer/coach), 'partial_or_deferred' (answered incorrectly, partially, or deferred), or 'no_visible_response' (unanswered/no reply).",
    )
    responder: str = Field(
        default="none",
        description="Who provided the answer: 'user' (student/peer), 'bot' (bot/labcoach bot), 'self' (same author closed it), or 'none' (if unanswered).",
    )
    needs_labcoach_review: bool = Field(
        default=True,
        description="True if the question is unanswered, partially answered, or needs LabCoach review. False if satisfactorily answered.",
    )
    rationale: str = Field(default="", description="Short natural language explanation of the classification.")


class QuestionEvalItem(BaseModel):
    input_index: int
    msg_id: str
    guild: str
    channel: str
    created_at_vn: str
    is_question: bool = True
    label: str
    response_status: str
    responder: str
    needs_labcoach_review: bool
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    reason: str = ""


class EvalCounts(BaseModel):
    answered: int = 0
    partial_or_deferred: int = 0
    no_visible_response: int = 0
    ignored_messages: int = 0
    labcoach_review_items: int = 0


class EvalBenchmarkOutputSchema(BaseModel):
    scope: str = "input_only"
    message_count: int
    question_count: int
    questions: list[QuestionEvalItem]
    ignored_messages: list[dict[str, Any]] = Field(default_factory=list)
    labcoach_review_items: list[dict[str, Any]] = Field(default_factory=list)
    data_quality_flags: list[str] = Field(default_factory=list)
    counts: EvalCounts


class BatchEvidence(BaseModel):
    input_index: int
    link_type: Literal["direct_reply", "context_inference"] = "context_inference"


class BatchMessageClassification(BaseModel):
    input_index: int
    is_standalone_question: bool = Field(description="A student ask, including an implicit problem report or follow-up. Helpers asking diagnostic questions are not new student asks.")
    asked_parts: list[str] = Field(default_factory=list, description="Each distinct fact, action or instruction requested by THIS message, interpreted in conversation context.")
    evidence: list[BatchEvidence] = Field(default_factory=list, description="Messages responding to THIS question, not questions this message answers. Inspect all direct replies and relevant conversation context before deciding status.")
    unresolved_parts: list[str] = Field(default_factory=list, description="Requested parts not resolved by the evidence. Empty when answered. A how/where question needs instructions, not proof they were executed.")
    reason: str = Field(default="", description="Explain how the cited evidence addresses or fails to address this original message.")
    response_status: Literal["answered", "partial_or_deferred", "no_visible_response"] = "no_visible_response"
    responder: Literal["user", "bot", "self", "none"] = "none"
    needs_labcoach_review: bool = True
    same_issue_as: int | None = Field(default=None, description="Earlier input_index from the SAME author in the SAME channel whose unresolved issue this question repeats or follows up. Never merge different authors or unrelated asks.")
    untrusted_instruction: bool = False


class BatchAnalysisOutput(BaseModel):
    classifications: list[BatchMessageClassification] = Field(
        description="Exactly one classification per input_index, including non-questions."
    )


class DetectedQuestion(BaseModel):
    input_index: int
    asked_parts: list[str] = Field(description="All requested facts, choices, resources or help, interpreted in context.")


class QuestionDetectionOutput(BaseModel):
    questions: list[DetectedQuestion]
    ignored_input_indexes: list[int] = Field(description="Every input index not in questions. Together both lists partition the entire input exactly once.")


class QuestionResolution(BaseModel):
    input_index: int
    evidence: list[BatchEvidence] = Field(description="Indexes of replies or contextual responses addressing THIS original question. Can precede it in the export.")
    unresolved_parts: list[str] = Field(description="Requested information still missing from the evidence. Empty only when fully answered.")
    reason: str = Field(description="Briefly compare every asked part with what the evidence actually says.")
    response_status: Literal["answered", "partial_or_deferred", "no_visible_response"]
    responder: Literal["user", "bot", "self", "none"]
    same_issue_as: int | None = Field(description="Earlier question index by same author and channel repeating this unresolved issue, otherwise null.")


class QuestionResolutionOutput(BaseModel):
    questions: list[QuestionResolution]


class BatchGraphState(TypedDict, total=False):
    input_messages: list[dict[str, Any]]
    data_quality_flags: list[str]
    raw_prompt: str
    raw_response: str
    analysis: Optional[BatchAnalysisOutput]
    output: dict[str, Any]
