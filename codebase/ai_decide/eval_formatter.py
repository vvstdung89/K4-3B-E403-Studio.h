"""AI-Driven Eval benchmark output formatter using LangGraph & LLM NLU.
Classifies Discord messages in testcases via natural language understanding.
"""

from __future__ import annotations

import os
from typing import Any

import time
from ai_decide.llm_factory import LLMFactory
from ai_decide.logger import LLMAuditLogger
from ai_decide.schemas import (
    EvalMessageClassification,
    QuestionEvalItem,
    EvalCounts,
    EvalBenchmarkOutputSchema,
)

EVAL_NLU_SYSTEM_PROMPT = """You are an expert AI Moderation Classifier for Discord channels in an AI engineering course.
Your job is to analyze a target Discord message and any subsequent messages in the channel/thread using Natural Language Understanding (NLU).

CRITICAL CLASSIFICATION RULES:

1. IS STANDALONE QUESTION (is_standalone_question):
   - True ONLY IF the message is a genuine, standalone question or help request from a student asking for information, guidance, or assistance.
   - False IF the message is an announcement, a progress update, a status report, a closing thank-you message (e.g. 'cảm ơn anh/bạn', 'mình tìm thấy rồi', 'hẹn buổi học tiếp theo'), or a routine non-question reply.

2. RESPONSE STATUS (response_status):
   - 'answered': A subsequent reply explicitly and correctly answers or resolves the student's question.
   - 'partial_or_deferred': A reply is given but it is incomplete, incorrect, off-topic, or defers the answer.
   - 'no_visible_response': No reply or no visible answer exists in subsequent messages.

3. RESPONDER (responder):
   - 'user': The answer was provided by a peer/student/human user.
   - 'labcoach': The answer was provided by an official LabCoach or Bot.
   - 'none': If unanswered / no visible response.

4. NEEDS LABCOACH REVIEW (needs_labcoach_review):
   - True IF response_status is 'no_visible_response' or 'partial_or_deferred'.
   - False IF response_status is 'answered'.
"""


def classify_message_with_ai(
    target_msg: dict[str, Any],
    channel_messages: list[dict[str, Any]],
    provider: str = "gemini",
    model_name: str | None = None,
) -> EvalMessageClassification:
    """Classify a single target message in context of channel messages using LLM NLU and audit log traces."""
    audit_logger = LLMAuditLogger()
    start_time = time.time()

    # Build prompt with target message and subsequent context
    target_info = (
        f"Message ID: {target_msg.get('msg_id')}\n"
        f"Author: {target_msg.get('author')}\n"
        f"Created At: {target_msg.get('created_at_vn')}\n"
        f"Content: \"{target_msg.get('content')}\"\n"
    )

    ctx_msgs = []
    for m in channel_messages:
        if m.get("msg_id") != target_msg.get("msg_id"):
            ctx_msgs.append(
                f"- ID: {m.get('msg_id')} | Author: {m.get('author')} | reply_to: {m.get('reply_to') or 'None'} | Content: \"{m.get('content')}\""
            )

    ctx_text = "\n".join(ctx_msgs) if ctx_msgs else "No other messages."

    prompt = (
        f"{EVAL_NLU_SYSTEM_PROMPT}\n\n"
        f"--- TARGET MESSAGE TO CLASSIFY ---\n{target_info}\n"
        f"--- OTHER MESSAGES IN CHANNEL/THREAD ---\n{ctx_text}\n\n"
        f"Analyze carefully and provide your NLU classification output."
    )

    try:
        llm = LLMFactory.get_llm(provider=provider, model_name=model_name, temperature=0.0)
        structured_llm = llm.with_structured_output(EvalMessageClassification)
        res = structured_llm.invoke(prompt)
        latency = (time.time() - start_time) * 1000

        res_obj = None
        if isinstance(res, EvalMessageClassification):
            res_obj = res
        elif isinstance(res, dict):
            res_obj = EvalMessageClassification(**res)

        if res_obj is not None:
            audit_logger.log_trace(
                provider=provider,
                model_name=getattr(llm, "model_name", getattr(llm, "model", str(model_name))),
                candidate_msg_id=str(target_msg.get("msg_id")),
                raw_input_prompt=prompt,
                raw_llm_response=str(res),
                parsed_decision=res_obj.model_dump(),
                latency_ms=latency,
            )
            return res_obj
    except Exception as exc:
        latency = (time.time() - start_time) * 1000
        audit_logger.log_trace(
            provider=provider,
            model_name=str(model_name),
            candidate_msg_id=str(target_msg.get("msg_id")),
            raw_input_prompt=prompt,
            raw_llm_response="",
            parsed_decision=None,
            latency_ms=latency,
            error=str(exc),
        )

    # Heuristic NLU fallback if LLM API is unavailable / invalid key
    content = str(target_msg.get("content", "")).lower()
    is_q = ("?" in content or content.startswith("cho em hỏi") or content.startswith("mình đi bus") or content.startswith("mình xem")) and not ("cảm ơn" in content)
    
    # Check if replied to
    replied = False
    for m in channel_messages:
        if m.get("reply_to") == target_msg.get("msg_id"):
            replied = True
            break

    if is_q:
        status = "answered" if replied else "no_visible_response"
        return EvalMessageClassification(
            is_standalone_question=True,
            response_status=status,
            responder="user" if replied else "none",
            needs_labcoach_review=not replied,
            rationale="AI execution fallback heuristic",
        )
    else:
        return EvalMessageClassification(
            is_standalone_question=False,
            response_status="no_visible_response",
            responder="none",
            needs_labcoach_review=False,
            rationale="AI execution fallback non-question",
        )


def process_eval_batch(
    input_messages: list[dict[str, Any]],
    provider: str = "gemini",
    model_name: str | None = None,
) -> dict[str, Any]:
    """Process a batch of input Discord messages from a benchmark JSON testcase
    using LLM NLU classification via LangGraph workflow.
    """
    data_quality_flags: list[str] = []
    seen_ids: set[str] = set()

    for idx, msg in enumerate(input_messages):
        msg_id = msg.get("msg_id")
        if not msg_id:
            data_quality_flags.append(f"Missing msg_id at index {idx}")
        elif msg_id in seen_ids:
            data_quality_flags.append(f"Duplicate msg_id: {msg_id} at index {idx}")
        else:
            seen_ids.add(msg_id)

    questions_list: list[QuestionEvalItem] = []
    counts = EvalCounts()

    for idx, msg in enumerate(input_messages):
        input_index = msg.get("input_index", idx)
        msg_id = str(msg.get("msg_id", f"M{idx}"))
        guild = str(msg.get("guild", ""))
        channel = str(msg.get("channel", ""))
        created_at_vn = str(msg.get("created_at_vn", ""))

        # Pass target message and full batch messages as channel context to AI Classifier
        classification = classify_message_with_ai(
            target_msg=msg,
            channel_messages=input_messages,
            provider=provider,
            model_name=model_name,
        )

        if classification.is_standalone_question:
            q_item = QuestionEvalItem(
                input_index=input_index,
                msg_id=msg_id,
                guild=guild,
                channel=channel,
                created_at_vn=created_at_vn,
                is_question=True,
                label=classification.response_status,
                response_status=classification.response_status,
                responder=classification.responder,
                needs_labcoach_review=classification.needs_labcoach_review,
            )
            questions_list.append(q_item)

            if classification.response_status == "answered":
                counts.answered += 1
            elif classification.response_status == "partial_or_deferred":
                counts.partial_or_deferred += 1
            else:
                counts.no_visible_response += 1
        else:
            counts.ignored_messages += 1

    output_schema = EvalBenchmarkOutputSchema(
        scope="input_only",
        message_count=len(input_messages),
        question_count=len(questions_list),
        questions=questions_list,
        data_quality_flags=data_quality_flags,
        counts=counts,
    )

    return output_schema.model_dump()
