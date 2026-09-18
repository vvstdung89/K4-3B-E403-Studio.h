"""Offline contract tests for the live batch decision graph."""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "codebase"))

from ai_decide.schemas import BatchCandidateOutput
from ai_decide.stub import decide
from data.loader import Message
from detect.rules import Candidate


def message(msg_id, content, reply_to=None):
    return Message(
        msg_id=msg_id, guild="test-guild", channel="test-channel",
        author="coach" if reply_to else "student", is_bot=False,
        msg_type="reply" if reply_to else "message",
        created_at=datetime(2026, 9, 18, 9), reply_to=reply_to,
        mentions_bot=False, n_attachments=0, n_chars=len(content), content=content,
    )


def analysis(msg_id, needs_attention):
    return dict(
        msg_id=msg_id, is_question=True, still_needs_attention=needs_attention,
        confidence=0.9, summary="Student request", rationale="Checked context",
    )


class LiveBatchTests(unittest.TestCase):
    def setUp(self):
        self.questions = [message("q1", "Where is the guide?"), message("q2", "How do I log in?")]
        self.candidates = [Candidate(m, "Awaiting review", 5.0) for m in self.questions]

    def test_one_call_uses_context_and_matches_reordered_results(self):
        reply = message("a1", "The guide is in the course library.", reply_to="q1")
        output = BatchCandidateOutput(items=[analysis("q2", True), analysis("q1", False)])
        with patch("ai_decide.graph._invoke_structured", return_value=(output, "raw")) as invoke:
            decisions = decide(self.candidates, all_messages=[*self.questions, reply],
                               provider="openai", model_name="test-model")
        invoke.assert_called_once()
        self.assertEqual(invoke.call_args.args[2:4], ("openai", "test-model"))
        self.assertIn(reply.content, invoke.call_args.args[1])
        self.assertIn("reply_to=q1", invoke.call_args.args[1])
        self.assertEqual([d.candidate for d in decisions], self.candidates)
        self.assertEqual([d.still_needs_attention for d in decisions], [False, True])

    def test_missing_item_keeps_only_missing_candidate_for_review(self):
        output = BatchCandidateOutput(items=[analysis("q1", False)])
        with patch("ai_decide.graph._invoke_structured", return_value=(output, "raw")):
            decisions = decide(self.candidates, provider="openai")
        self.assertEqual([d.candidate for d in decisions], self.candidates)
        self.assertEqual([d.still_needs_attention for d in decisions], [False, True])
        self.assertIn("Missing item", decisions[1].rationale)

    def test_api_failure_keeps_every_candidate_for_review(self):
        with patch("ai_decide.graph._invoke_structured", side_effect=RuntimeError("API unavailable")):
            decisions = decide(self.candidates, provider="openai")
        self.assertEqual([d.candidate for d in decisions], self.candidates)
        self.assertTrue(all(d.still_needs_attention for d in decisions))

    def test_graph_failure_keeps_every_candidate_for_review(self):
        with patch("ai_decide.stub.create_ai_decision_graph") as create_graph:
            create_graph.return_value.invoke.side_effect = RuntimeError("Graph failed")
            decisions = decide(self.candidates, provider="openai")
        self.assertEqual([d.candidate for d in decisions], self.candidates)
        self.assertTrue(all(d.still_needs_attention for d in decisions))
        self.assertTrue(all("Graph failed" in d.rationale for d in decisions))

    def test_invalid_structured_output_keeps_every_candidate_for_review(self):
        invalid = {"items": [{**analysis("q1", False), "confidence": 2}]}
        with patch("ai_decide.graph._invoke_structured", return_value=(invalid, "invalid")):
            decisions = decide(self.candidates, provider="openai")
        self.assertEqual([d.candidate for d in decisions], self.candidates)
        self.assertTrue(all(d.still_needs_attention for d in decisions))

    def test_empty_batch_does_not_create_graph(self):
        with patch("ai_decide.stub.create_ai_decision_graph") as create_graph:
            self.assertEqual(decide([], provider="openai"), [])
        create_graph.assert_not_called()


if __name__ == "__main__":
    unittest.main()
