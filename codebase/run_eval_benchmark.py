"""Benchmark evaluator for batched request detection and resolution.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

from ai_decide.eval_formatter import process_eval_batch

load_dotenv(Path(__file__).resolve().parent / ".env")

CORE_QUESTION_FIELDS = (
    "msg_id",
    "input_index",
    "guild",
    "channel",
    "created_at_vn",
    "is_question",
    "label",
    "response_status",
    "responder",
    "needs_labcoach_review",
)
COUNT_FIELDS = (
    "answered",
    "partial_or_deferred",
    "no_visible_response",
    "ignored_messages",
    "labcoach_review_items",
)


def _present(value: object) -> bool:
    return value is not None


def _compare_question(actual: dict, expected: dict) -> list[str]:
    mismatches: list[str] = []
    for field in CORE_QUESTION_FIELDS:
        if field not in expected or not _present(expected.get(field)):
            continue
        if actual.get(field) != expected.get(field):
            mismatches.append(f"{field} (actual={actual.get(field)} vs exp={expected.get(field)})")
    return mismatches


def run_eval(json_file_path: Path, provider: str | None = None, reminder_policy: str = "per_issue", model_name: str | None = None) -> bool:
    print("=" * 50)
    print(f"  RUNNING BENCHMARK EVALUATION: {json_file_path.name}")
    print("=" * 50)

    if not json_file_path.exists():
        print(f"Error: File not found at {json_file_path}")
        return False

    with json_file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    case_id = data.get("case_id", "UNKNOWN")
    description = data.get("description", "")
    input_msgs = data.get("input", [])
    expected = data.get("expected_output", {})

    print(f"Case ID: {case_id}")
    print(f"Description: {description}")
    print(f"Input messages: {len(input_msgs)}")

    print(f"Reminder policy: {reminder_policy}; model: {model_name or 'provider default'}")
    try:
        actual = process_eval_batch(input_msgs, provider=provider, model_name=model_name, reminder_policy=reminder_policy)
    except Exception as exc:
        print(f"[ERROR] Classification failed: {type(exc).__name__}: {exc}")
        return False

    print("\n--- ACTUAL WORKFLOW OUTPUT (JSON) ---")
    print(json.dumps(actual, indent=2, ensure_ascii=False))

    print("\n--- MATCHING EVALUATION ---")
    passed = True

    if actual["message_count"] == expected.get("message_count"):
        print(f"[PASS] message_count: {actual['message_count']}")
    else:
        print(f"[FAIL] message_count: {actual['message_count']} != {expected.get('message_count')}")
        passed = False

    if actual["question_count"] == expected.get("question_count"):
        print(f"[PASS] question_count: {actual['question_count']}")
    else:
        print(f"[FAIL] question_count: {actual['question_count']} != {expected.get('question_count')}")
        passed = False

    actual_counts = actual.get("counts") or {}
    expected_counts = expected.get("counts") or {}
    for key in COUNT_FIELDS:
        if key not in expected_counts:
            continue
        act_val = actual_counts.get(key, 0)
        exp_val = expected_counts.get(key, 0)
        if act_val == exp_val:
            print(f"[PASS] counts.{key}: {act_val}")
        else:
            print(f"[FAIL] counts.{key}: {act_val} != {exp_val}")
            passed = False

    actual_questions = actual.get("questions") or []
    expected_questions = expected.get("questions") or []
    # Synthetic windows can reuse msg_id across channels. Original fixtures
    # without input_index retain their legacy msg_id matching contract.
    key_field = "input_index" if expected_questions and all(
        q.get("input_index") is not None for q in expected_questions
    ) else "msg_id"
    act_by_id = {q.get(key_field): q for q in actual_questions}
    exp_by_id = {q.get(key_field): q for q in expected_questions}
    if len(act_by_id) != len(actual_questions):
        print(f"[FAIL] duplicate question identities: {key_field}")
        passed = False
    if len(exp_by_id) != len(expected_questions):
        print(f"[FAIL] ambiguous expected question identities: {key_field}")
        passed = False

    extra = sorted(set(act_by_id) - set(exp_by_id), key=repr)
    missing = sorted(set(exp_by_id) - set(act_by_id), key=repr)
    if extra:
        print(f"[FAIL] extra questions: {extra}")
        passed = False
    if missing:
        print(f"[FAIL] missing questions: {missing}")
        passed = False

    for identity in sorted(set(exp_by_id) & set(act_by_id), key=repr):
        msg_id = exp_by_id[identity]["msg_id"]
        description = f"{msg_id} [{key_field}={identity}]"
        mismatches = _compare_question(act_by_id[identity], exp_by_id[identity])
        if not mismatches:
            print(f"[PASS] {description}")
        else:
            print(f"[FAIL] {description}: {', '.join(mismatches)}")
            passed = False

    if "labcoach_review_items" in expected:
        use_message_keys = bool(expected["labcoach_review_items"]) and all(
            "message_keys" in item for item in expected["labcoach_review_items"]
        )

        def group_ids(item):
            if use_message_keys:
                return tuple(sorted(
                    (tuple(key.get(field) for field in (
                        "input_index", "msg_id", "guild", "channel", "created_at_vn"
                    )) for key in item.get("message_keys", [])), key=repr
                ))
            return tuple(sorted(item.get("message_ids") or [key["msg_id"] for key in item.get("message_keys", [])]))

        actual_groups = sorted((group_ids(item) for item in actual.get("labcoach_review_items", [])), key=repr)
        expected_groups = sorted((group_ids(item) for item in expected["labcoach_review_items"]), key=repr)
        if actual_groups != expected_groups:
            print(f"[FAIL] reminder groups: {actual_groups} != {expected_groups}")
            passed = False
        else:
            print("[PASS] reminder groups")

    print()
    print("=" * 50)
    if passed:
        print("  BENCHMARK RESULT: 100% MATCHED (SUCCESS)")
    else:
        print("  BENCHMARK RESULT: MISMATCH DETECTED (FAILED)")
    print("=" * 50)
    print()
    return passed


def _resolve_cases(args: argparse.Namespace) -> list[Path]:
    if args.file:
        return [Path(args.file)]
    root = Path(args.dir)
    names = [n.strip() for n in args.cases.split(",") if n.strip()]
    return [root / f"{name}.json" for name in names]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run batch LangGraph eval against golden-set cases.")
    parser.add_argument("--file", type=str, default=None, help="Single golden-set JSON file.")
    parser.add_argument("--dir", type=str, default=str(Path(__file__).resolve().parent.parent / "eval" / "golden_set"), help="Golden-set directory.")
    parser.add_argument(
        "--cases",
        type=str,
        default="K4-H11,K4-H12,K4-H13,K4-H14",
        help="Comma-separated case ids when --file is not set.",
    )
    parser.add_argument("--provider", type=str, default=None, help="LLM provider override.")
    parser.add_argument("--model", type=str, default=None, help="Model override for this run; does not modify environment configuration.")
    parser.add_argument("--reminder-policy", choices=("per_issue", "per_message"), default="per_issue", help="Group same-author repeats, or count each unresolved message independently.")
    args = parser.parse_args()

    provider = args.provider or os.getenv("LLM_PROVIDER", "openai")
    paths = _resolve_cases(args)
    results: list[tuple[str, bool]] = []
    for path in paths:
        ok = run_eval(path.resolve(), provider=provider, reminder_policy=args.reminder_policy, model_name=args.model)
        results.append((path.name, ok))

    print("=== SUITE ===")
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    failed = sum(1 for _, ok in results if not ok)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
