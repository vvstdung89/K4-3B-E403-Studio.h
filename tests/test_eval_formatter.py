"""Offline regression checks for evidence validation and reminder grouping."""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "codebase"))

from ai_decide.eval_formatter import format_eval_output
from ai_decide.schemas import BatchAnalysisOutput, BatchMessageClassification


def message(msg_id, author="student", reply_to="", channel="help"):
    return dict(msg_id=msg_id, author=author, reply_to=reply_to, guild="course",
                channel=channel, created_at_vn="2026-09-18 12:00", content="text", is_bot=False)


def classify(index, question=False, **kwargs):
    return BatchMessageClassification(input_index=index, is_standalone_question=question, **kwargs)


class FormatterTests(unittest.TestCase):
    def output(self, messages, items, **kwargs):
        return format_eval_output(messages, BatchAnalysisOutput(classifications=items), [], **kwargs)

    def test_contextual_deferral_is_preserved(self):
        out = self.output([message("q"), message("reply", "helper")], [
            classify(0, True, response_status="partial_or_deferred", responder="user",
                     evidence=[{"input_index": 1}], unresolved_parts=["date"]), classify(1)])
        self.assertEqual(out["questions"][0]["response_status"], "partial_or_deferred")
        self.assertEqual(out["questions"][0]["evidence"][0]["msg_id"], "reply")

    def test_reply_before_parent_is_valid(self):
        out = self.output([message("reply", "helper", "q"), message("q")], [
            classify(0), classify(1, True, response_status="answered", responder="user",
                                  evidence=[{"input_index": 0}])])
        self.assertEqual(out["counts"]["answered"], 1)
        self.assertEqual(out["questions"][0]["evidence"][0]["link_type"], "direct_reply")

    def test_direct_link_does_not_prove_answer(self):
        out = self.output([message("q"), message("reply", "helper", "q")], [
            classify(0, True), classify(1)])
        self.assertEqual(out["counts"]["partial_or_deferred"], 1)

    def test_unresolved_part_prevents_answered(self):
        out = self.output([message("q"), message("reply", "helper", "q")], [
            classify(0, True, response_status="answered", evidence=[{"input_index": 1}],
                     unresolved_parts=["second part"]), classify(1)])
        self.assertTrue(out["questions"][0]["needs_labcoach_review"])

    def test_invalid_evidence_cannot_close_question(self):
        out = self.output([message("q"), message("reply", "helper", "q", channel="other")], [
            classify(0, True, response_status="answered", evidence=[{"input_index": 1}, {"input_index": 99}]), classify(1)])
        self.assertEqual(out["questions"][0]["response_status"], "no_visible_response")

    def test_general_broadcast_is_not_a_response_to_an_asker(self):
        messages = [message("q"), dict(message("notice", "helper"), msg_type="announcement")]
        out = self.output(messages, [classify(0, True, response_status="partial_or_deferred",
                                             evidence=[{"input_index": 1}]), classify(1)])
        self.assertEqual(out["questions"][0]["response_status"], "no_visible_response")
        self.assertEqual(out["questions"][0]["evidence"], [])

    def test_same_issue_groups_reminders_not_questions(self):
        msgs = [message("q1"), message("q2")]
        items = [classify(0, True), classify(1, True, same_issue_as=0)]
        grouped = self.output(msgs, items)
        separate = self.output(msgs, items, reminder_policy="per_message")
        self.assertEqual(grouped["question_count"], 2)
        self.assertEqual(grouped["counts"]["labcoach_review_items"], 1)
        self.assertEqual(len(grouped["labcoach_review_items"][0]["message_keys"]), 2)
        self.assertEqual(separate["counts"]["labcoach_review_items"], 2)

    def test_different_authors_cannot_group(self):
        out = self.output([message("q1"), message("q2", "someone_else")], [
            classify(0, True), classify(1, True, same_issue_as=0)])
        self.assertEqual(out["counts"]["labcoach_review_items"], 2)

    def test_different_recipient_types_cannot_group(self):
        messages = [message("q1"), dict(message("q2"), mentions_bot=True)]
        out = self.output(messages, [classify(0, True), classify(1, True, same_issue_as=0)])
        self.assertEqual(out["counts"]["labcoach_review_items"], 2)

    def test_missing_or_duplicate_classifications_fail_explicitly(self):
        for items in ([], [classify(0), classify(0)]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                self.output([message("q1"), message("q2")], items)


if __name__ == "__main__":
    unittest.main()
