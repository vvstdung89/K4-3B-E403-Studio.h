"""Regression checks for distinct questions sharing a message ID."""

import copy
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "codebase"))

from run_eval_benchmark import run_eval


class BenchmarkIdentityTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "eval" / "golden_set" / "K4-H21.json"
        self.expected = json.loads(self.path.read_text(encoding="utf-8"))["expected_output"]

    def score(self, actual, path=None):
        with patch("run_eval_benchmark.process_eval_batch", return_value=actual), redirect_stdout(io.StringIO()):
            return run_eval(path or self.path)

    def test_duplicate_message_ids_in_different_channels_can_pass(self):
        self.assertTrue(self.score(copy.deepcopy(self.expected)))

    def test_wrong_first_question_with_reused_id_is_not_overwritten(self):
        actual = copy.deepcopy(self.expected)
        actual["questions"][0]["response_status"] = "no_visible_response"
        self.assertFalse(self.score(actual))

    def test_duplicate_question_index_fails(self):
        actual = copy.deepcopy(self.expected)
        actual["questions"][0] = copy.deepcopy(actual["questions"][1])
        self.assertFalse(self.score(actual))

    def test_reminder_for_same_id_in_wrong_channel_fails(self):
        actual = copy.deepcopy(self.expected)
        target = actual["labcoach_review_items"][0]["message_keys"][0]
        first_question = actual["questions"][0]
        for field in target:
            target[field] = first_question[field]
        self.assertFalse(self.score(actual))

    def test_original_fixture_without_indexes_keeps_legacy_matching(self):
        path = ROOT / "eval" / "golden_set" / "K4-01.json"
        expected = json.loads(path.read_text(encoding="utf-8"))["expected_output"]
        self.assertTrue(self.score(expected, path))


if __name__ == "__main__":
    unittest.main()
