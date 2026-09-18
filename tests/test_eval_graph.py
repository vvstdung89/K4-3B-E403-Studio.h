"""Offline tests for the two-stage classifier's coverage contract."""

import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "codebase"))

from ai_decide.graph import _invoke_complete, build_batch_eval_prompt, eval_classify_node
from ai_decide.schemas import QuestionDetectionOutput, QuestionResolutionOutput


class GraphTests(unittest.TestCase):
    def test_stages_preserve_original_question_index(self):
        messages = [
            dict(msg_id="q", author="student", is_bot=False, guild="g", channel="c", content="Where is the guide?"),
            dict(msg_id="a", author="coach", is_bot=False, guild="g", channel="c", reply_to="q", content="In the course library."),
        ]
        detected = QuestionDetectionOutput(questions=[dict(input_index=0, asked_parts=["guide location"])], ignored_input_indexes=[1])
        resolved = QuestionResolutionOutput(questions=[dict(input_index=0, evidence=[dict(input_index=1)],
            unresolved_parts=[], reason="Library location supplied", response_status="answered", responder="user", same_issue_as=None)])
        with patch("ai_decide.graph._invoke_structured", side_effect=[(detected, "detected"), (resolved, "resolved")]) as invoke:
            result = eval_classify_node(dict(input_messages=messages, raw_prompt=build_batch_eval_prompt(messages)))
        by_index = {q.input_index: q for q in result["analysis"].classifications}
        self.assertEqual(by_index[0].response_status, "answered")
        self.assertFalse(by_index[1].is_standalone_question)
        self.assertEqual(invoke.call_count, 2)
        self.assertIn('"direct_replies"', invoke.call_args_list[1].args[1])

    def test_incomplete_output_retries_then_rejects(self):
        invalid = QuestionDetectionOutput(questions=[], ignored_input_indexes=[0])
        with patch("ai_decide.graph._invoke_structured", return_value=(invalid, "raw")) as invoke:
            with self.assertRaises(ValueError):
                _invoke_complete(QuestionDetectionOutput, "prompt", "openai", None, "test", {0, 1},
                                 lambda r: r.ignored_input_indexes, "policy")
        self.assertEqual(invoke.call_count, 2)
        self.assertIn("Expected indexes exactly once", invoke.call_args.args[1])

    def test_api_failure_is_not_a_successful_empty_classification(self):
        messages = [dict(msg_id="q", content="Help", is_bot=False)]
        with patch("ai_decide.graph._invoke_structured", side_effect=RuntimeError("API unavailable")):
            with self.assertRaisesRegex(RuntimeError, "API unavailable"):
                eval_classify_node(dict(input_messages=messages, raw_prompt=build_batch_eval_prompt(messages)))


if __name__ == "__main__":
    unittest.main()
