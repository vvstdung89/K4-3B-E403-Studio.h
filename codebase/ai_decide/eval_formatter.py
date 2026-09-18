"""Format evidence-based classifications and group LabCoach reminders.
"""

from __future__ import annotations

import os
from typing import Any

from ai_decide.graph import create_batch_eval_graph
from ai_decide.schemas import (
    BatchAnalysisOutput,
    BatchEvidence,
    BatchMessageClassification,
    EvalBenchmarkOutputSchema,
    EvalCounts,
    QuestionEvalItem,
)


def _is_bot(msg: dict[str, Any]) -> bool:
    val = msg.get("is_bot")
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in {"true", "1", "yes"}


def _derive_label(is_question: bool, status: str, responder: str) -> str:
    if not is_question:
        return "not_a_question"
    if status == "partial_or_deferred":
        if responder == "user":
            return "partial_response_by_user"
        if responder == "bot":
            return "partial_response_by_bot"
    return status


def _same_conversation(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (a.get("guild"), a.get("channel")) == (b.get("guild"), b.get("channel"))


def _apply_code_guardrails(
    messages: list[dict[str, Any]], analysis: BatchAnalysisOutput
) -> dict[int, BatchMessageClassification]:
    indexes = [item.input_index for item in analysis.classifications]
    if len(indexes) != len(messages) or set(indexes) != set(range(len(messages))):
        raise ValueError("Batch must classify every input_index exactly once")
    by_index = {item.input_index: item for item in analysis.classifications}
    out: dict[int, BatchMessageClassification] = {}
    for idx, msg in enumerate(messages):
        item = by_index[idx].model_copy(deep=True)
        if _is_bot(msg) or not str(msg.get("content") or "").strip():
            item.is_standalone_question = False
        if not item.is_standalone_question:
            item.response_status = "no_visible_response"
            item.responder = "none"
            item.needs_labcoach_review = False
            item.evidence = []
            item.same_issue_as = None
            out[idx] = item
            continue

        # Check references mechanically; semantic relevance remains the model's job.
        evidence: list[BatchEvidence] = []
        seen: set[int] = set()
        for ev in item.evidence:
            j = ev.input_index
            if j == idx or j in seen or not 0 <= j < len(messages):
                continue
            reply = messages[j]
            if not _same_conversation(msg, reply):
                continue
            direct = bool(msg.get("msg_id")) and reply.get("reply_to") == msg.get("msg_id")
            content = str(reply.get("content") or "").strip().lower()
            broadcast = reply.get("msg_type") == "announcement" or content.startswith(("thông báo:", "thong bao:"))
            addresses_asker = bool(msg.get("author")) and f"[@{msg['author']}]".lower() in content
            if broadcast and not direct and not addresses_asker:
                continue
            seen.add(j)
            evidence.append(BatchEvidence(input_index=j, link_type="direct_reply" if direct else "context_inference"))
        if not evidence:
            # A linked response proves only that a response exists, not completeness.
            evidence = [BatchEvidence(input_index=j, link_type="direct_reply")
                        for j, reply in enumerate(messages)
                        if j != idx and msg.get("msg_id")
                        and reply.get("reply_to") == msg.get("msg_id")
                        and _same_conversation(msg, reply)
                        and not by_index[j].is_standalone_question
                        and str(reply.get("content") or "").strip()
                        and reply.get("author") != msg.get("author")]
            if evidence:
                item.response_status = "partial_or_deferred"
                item.reason += " [Response link found, but the model did not establish completeness.]"
        if not evidence:
            if item.response_status != "no_visible_response":
                item.reason += " [Unsupported response status: no valid evidence.]"
            item.response_status = "no_visible_response"
            item.responder = "none"
        else:
            if item.response_status == "no_visible_response" or item.unresolved_parts:
                item.response_status = "partial_or_deferred"
            responders = []
            for ev in evidence:
                reply = messages[ev.input_index]
                responders.append("bot" if _is_bot(reply) else "self" if msg.get("author") and reply.get("author") == msg.get("author") else "user")
            if item.responder not in responders:
                item.responder = responders[0]
        item.evidence = evidence
        item.needs_labcoach_review = item.response_status != "answered"
        out[idx] = item
    return out


def _review_groups(messages, classified, policy):
    if policy not in {"per_issue", "per_message"}:
        raise ValueError("reminder_policy must be per_issue or per_message")
    groups: dict[int, list[int]] = {}
    roots: dict[int, int] = {}
    for idx, item in classified.items():
        if not item.needs_labcoach_review:
            continue
        parent = item.same_issue_as
        root = idx
        if policy == "per_issue" and parent is not None and parent < idx and parent in roots:
            a, b = messages[idx], messages[parent]
            if (a.get("author") and a.get("author") == b.get("author")
                    and _same_conversation(a, b)
                    and str(a.get("mentions_bot", False)).lower() == str(b.get("mentions_bot", False)).lower()):
                root = roots[parent]
        roots[idx] = root
        groups.setdefault(root, []).append(idx)
    return groups


def format_eval_output(
    messages: list[dict[str, Any]],
    analysis: BatchAnalysisOutput,
    data_quality_flags: list[str],
    reminder_policy: str = "per_issue",
) -> dict[str, Any]:
    classified = _apply_code_guardrails(messages, analysis)
    questions: list[QuestionEvalItem] = []
    ignored: list[dict[str, Any]] = []
    counts = EvalCounts()

    for idx, msg in enumerate(messages):
        item = classified[idx]
        input_index = msg.get("input_index", idx)
        msg_id = str(msg.get("msg_id", f"M{idx}"))
        guild = str(msg.get("guild", ""))
        channel = str(msg.get("channel", ""))
        created_at_vn = str(msg.get("created_at_vn", ""))
        label = _derive_label(item.is_standalone_question, item.response_status, item.responder)

        if item.is_standalone_question:
            evidence = [dict(
                input_index=e.input_index,
                msg_id=str(messages[e.input_index].get("msg_id", f"M{e.input_index}")),
                guild=str(messages[e.input_index].get("guild", "")),
                channel=str(messages[e.input_index].get("channel", "")),
                created_at_vn=str(messages[e.input_index].get("created_at_vn", "")),
                link_type=e.link_type,
            ) for e in item.evidence]
            questions.append(
                QuestionEvalItem(
                    input_index=int(input_index),
                    msg_id=msg_id,
                    guild=guild,
                    channel=channel,
                    created_at_vn=created_at_vn,
                    is_question=True,
                    label=label,
                    response_status=item.response_status,
                    responder=item.responder,
                    needs_labcoach_review=item.needs_labcoach_review,
                    evidence=evidence,
                    reason=item.reason,
                )
            )
            if item.response_status == "answered":
                counts.answered += 1
            elif item.response_status == "partial_or_deferred":
                counts.partial_or_deferred += 1
            else:
                counts.no_visible_response += 1
        else:
            counts.ignored_messages += 1
            ignored.append(
                {
                    "input_index": int(input_index),
                    "msg_id": msg_id,
                    "guild": guild,
                    "channel": channel,
                    "created_at_vn": created_at_vn,
                    "label": "not_a_question",
                    "reason": item.reason or "not_standalone_question_or_help_request",
                }
            )

    groups = _review_groups(messages, classified, reminder_policy)
    question_by_index = {q.input_index: q for q in questions}
    review_items = []
    for indexes in groups.values():
        keys = [question_by_index[messages[i].get("input_index", i)].model_dump(include={"input_index", "msg_id", "guild", "channel", "created_at_vn"}) for i in indexes]
        review_items.append({"message_keys": keys, "reason": classified[indexes[-1]].reason})
    counts.labcoach_review_items = len(review_items)

    return EvalBenchmarkOutputSchema(
        scope="input_only",
        message_count=len(messages),
        question_count=len(questions),
        questions=questions,
        ignored_messages=ignored,
        labcoach_review_items=review_items,
        data_quality_flags=data_quality_flags,
        counts=counts,
    ).model_dump()


def process_eval_batch(
    input_messages: list[dict[str, Any]],
    provider: str | None = None,
    model_name: str | None = None,
    reminder_policy: str = "per_issue",
) -> dict[str, Any]:
    """Detect requests, resolve their evidence, then format the whole window."""
    data_quality_flags: list[str] = []
    seen_ids: set[str] = set()
    for idx, msg in enumerate(input_messages):
        msg_id = msg.get("msg_id")
        if not msg_id:
            data_quality_flags.append(f"Missing msg_id at index {idx}")
        elif msg_id in seen_ids:
            data_quality_flags.append(f"Duplicate msg_id: {msg_id} at index {idx}")
        else:
            seen_ids.add(str(msg_id))

    active_provider = provider or os.getenv("LLM_PROVIDER", "openai")
    app = create_batch_eval_graph(provider=active_provider, model_name=model_name)
    final_state = app.invoke({"input_messages": input_messages, "data_quality_flags": data_quality_flags})
    analysis = final_state.get("analysis") if isinstance(final_state, dict) else None
    if analysis is None:
        analysis = BatchAnalysisOutput(classifications=[])
    elif isinstance(analysis, dict):
        analysis = BatchAnalysisOutput(**analysis)
    return format_eval_output(input_messages, analysis, data_quality_flags, reminder_policy)
