"""Model parameter compatibility without making API requests."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "codebase"))

from ai_decide.llm_factory import LLMFactory


class ModelParametersTests(unittest.TestCase):
    def test_reasoning_model_omits_temperature(self):
        with patch.dict(os.environ, {"OPENAI_REASONING_EFFORT": "medium"}), patch("langchain_openai.ChatOpenAI") as constructor:
            LLMFactory.get_llm(provider="openai", model_name="gpt-5.4")
        self.assertNotIn("temperature", constructor.call_args.kwargs)
        self.assertEqual(constructor.call_args.kwargs["reasoning_effort"], "medium")

    def test_existing_model_keeps_temperature(self):
        with patch("langchain_openai.ChatOpenAI") as constructor:
            LLMFactory.get_llm(provider="openai", model_name="gpt-4o-mini", temperature=0.0)
        self.assertEqual(constructor.call_args.kwargs["temperature"], 0.0)
        self.assertNotIn("reasoning_effort", constructor.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
