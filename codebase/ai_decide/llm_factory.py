"""LLM Factory supporting OpenAI, Gemini, and Anthropic providers.

Reads LLM_PROVIDER from environment variables if not specified.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

# Load .env relative to codebase directory
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

class LLMFactory:
    @staticmethod
    def get_llm(
        provider: str | None = None,
        model_name: str | None = None,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> BaseChatModel:
        if not provider:
            provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        else:
            provider = provider.lower()

        if provider == "openai":
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as exc:
                raise ImportError(
                    "langchain-openai is required for OpenAI provider. Install with `pip install langchain-openai`"
                ) from exc
            
            selected_model = model_name or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            api_key = os.getenv("OPENAI_API_KEY")
            if selected_model.startswith("gpt-5"):
                # Reasoning requests do not support temperature sampling.
                kwargs.setdefault("reasoning_effort", os.getenv("OPENAI_REASONING_EFFORT", "medium"))
            else:
                kwargs["temperature"] = temperature
            return ChatOpenAI(
                model=selected_model,
                api_key=api_key if api_key else "mock-key",
                **kwargs,
            )

        elif provider == "gemini":
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError as exc:
                raise ImportError(
                    "langchain-google-genai is required for Gemini provider. Install with `pip install langchain-google-genai`"
                ) from exc
            
            selected_model = model_name or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            return ChatGoogleGenerativeAI(
                model=selected_model,
                temperature=temperature,
                google_api_key=api_key if api_key else "mock-key",
                **kwargs,
            )

        elif provider == "anthropic":
            try:
                from langchain_anthropic import ChatAnthropic
            except ImportError as exc:
                raise ImportError(
                    "langchain-anthropic is required for Anthropic provider. Install with `pip install langchain-anthropic`"
                ) from exc
            
            selected_model = model_name or os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")
            api_key = os.getenv("ANTHROPIC_API_KEY")
            return ChatAnthropic(
                model=selected_model,
                temperature=temperature,
                api_key=api_key if api_key else "mock-key",
                **kwargs,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: '{provider}'. Allowed values: 'openai', 'gemini', 'anthropic'")
