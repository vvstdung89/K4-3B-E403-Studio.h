"""Benchmark Evaluator script for Discord Assistant AI decision workflow.
Runs input testcases from eval/*.json files and compares output against expected_output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add codebase directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai_decide.eval_formatter import process_eval_batch


def run_eval(json_file_path: Path) -> bool:
    print(f"==================================================")
    print(f"  RUNNING BENCHMARK EVALUATION: {json_file_path.name}")
    print(f"==================================================")

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

    # Execute workflow formatting
    actual = process_eval_batch(input_msgs, provider="gemini")

    # Print Actual JSON Output
    print("\n--- ACTUAL WORKFLOW OUTPUT (JSON) ---")
    print(json.dumps(actual, indent=2, ensure_ascii=False))

    # Evaluate against expected output rules
    print("\n--- MATCHING EVALUATION ---")
    passed = True

    # 1. Scope & Count checks
    if actual["message_count"] == expected["message_count"]:
        print(f"[PASS] message_count: {actual['message_count']} == {expected['message_count']}")
    else:
        print(f"[FAIL] message_count: {actual['message_count']} != {expected['message_count']}")
        passed = False

    if actual["question_count"] == expected["question_count"]:
        print(f"[PASS] question_count: {actual['question_count']} == {expected['question_count']}")
    else:
        print(f"[FAIL] question_count: {actual['question_count']} != {expected['question_count']}")
        passed = False

    # 2. Counts dict checks
    actual_counts = actual["counts"]
    expected_counts = expected.get("counts", {})

    for k in ["answered", "partial_or_deferred", "no_visible_response", "ignored_messages"]:
        act_val = actual_counts.get(k, 0)
        exp_val = expected_counts.get(k, 0)
        if act_val == exp_val:
            print(f"[PASS] counts.{k}: {act_val} == {exp_val}")
        else:
            print(f"[FAIL] counts.{k}: {act_val} != {exp_val}")
            passed = False

    # 3. Questions matching
    actual_questions = actual["questions"]
    expected_questions = expected.get("questions", [])

    if len(actual_questions) != len(expected_questions):
        print(f"[FAIL] Number of questions match: actual {len(actual_questions)} vs expected {len(expected_questions)}")
        passed = False
    else:
        for idx, (act_q, exp_q) in enumerate(zip(actual_questions, expected_questions)):
            q_msg_id = act_q["msg_id"]
            mismatches = []
            for field in ["msg_id", "input_index", "is_question", "label", "response_status", "responder", "needs_labcoach_review"]:
                if act_q.get(field) != exp_q.get(field):
                    mismatches.append(f"{field} (actual={act_q.get(field)} vs exp={exp_q.get(field)})")
            
            if not mismatches:
                print(f"[PASS] Question #{idx+1} ({q_msg_id}): All required fields match perfectly!")
            else:
                print(f"[FAIL] Question #{idx+1} ({q_msg_id}) Mismatches: {', '.join(mismatches)}")
                passed = False

    print("\n==================================================")
    if passed:
        print("  BENCHMARK RESULT: 100% MATCHED (SUCCESS)")
    else:
        print("  BENCHMARK RESULT: MISMATCH DETECTED (FAILED)")
    print("==================================================\n")

    return passed


def main():
    parser = argparse.ArgumentParser(description="Run benchmark evaluation against json testcases.")
    parser.add_argument(
        "--file",
        type=str,
        default="../eval/testcases/K4-H11.json",
        help="Path to evaluation JSON testcase file.",
    )
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        # Fallback check
        alt_path = Path("../eval/K4-H11.json")
        if alt_path.exists():
            file_path = alt_path

    json_path = file_path.resolve()
    success = run_eval(json_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
