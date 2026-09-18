"""Pre-computes real LangGraph decisions for a sample CSV pack and saves
them to a cache file, so /labcoach-demo (bot_gateway.py) can replay a real
demo instantly and repeatedly without depending on the graph model live --
important given Gemini's free-tier quota (as low as ~15-20 req/day on some
models, confirmed by hitting it during this project's own testing).

This is a one-time (or occasional) build step, not part of any live path --
it deliberately does NOT apply bot_gateway.py's AI-review cap, since it
only needs to run once to fill the cache, not stay fast on every call.

Run from the codebase/ directory:

    python3 build_demo_cache.py                                   # k4_messages.csv, all candidates
    python3 build_demo_cache.py --csv path/to/other.csv
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from ai_decide.stub import decide
from data.loader import default_csv_path, load_messages
from detect.rules import find_unanswered_questions

load_dotenv()  # must run before any os.environ.get() below, or .env-only values are silently ignored

MIN_HOURS_UNANSWERED = 4.0
MAX_CONTEXT_HOURS = 6.0  # matches bot_gateway.py's bounded context window
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini")  # only GEMINI_API_KEY is configured in .env
# No model_name is passed to decide() -- ai_decide/llm_factory.py already
# resolves the right one per provider (OPENAI_MODEL/GEMINI_MODEL/ANTHROPIC_MODEL,
# see .env.example). Passing one here would hardcode a Gemini-shaped model
# name that breaks if LLM_PROVIDER is ever switched to openai/anthropic.
CACHE_DIR = Path("output/demo_cache")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=str, default=None, help="Path to the CSV pack to cache (default: data/discord-pack/)")
    args = parser.parse_args()

    csv_path = args.csv or default_csv_path()
    messages = load_messages(csv_path)
    now = max(m.created_at for m in messages)
    candidates = find_unanswered_questions(messages, now=now, min_hours_unanswered=MIN_HOURS_UNANSWERED)
    print(f"Loaded {len(messages)} messages, {len(candidates)} rule-based candidate(s) to review")

    context_pool = [m for m in messages if now - timedelta(hours=MAX_CONTEXT_HOURS) <= m.created_at <= now]
    decisions = decide(candidates, all_messages=context_pool, provider=LLM_PROVIDER, model_name=GEMINI_MODEL)

    cache = {
        "dataset": Path(csv_path).name,
        "generated_at": datetime.now().isoformat(),
        "reference_now": now.isoformat(),
        "decisions": [
            {
                "msg_id": d.candidate.message.msg_id,
                "still_needs_attention": d.still_needs_attention,
                "confidence": d.confidence,
                "rationale": d.rationale,
            }
            for d in decisions
        ],
    }

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CACHE_DIR / f"{Path(csv_path).stem}.json"
    out_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")

    n_real = sum(1 for d in decisions if "AI execution fallback" not in d.rationale)
    print(f"Saved {len(decisions)} decision(s) to {out_path} ({n_real} real AI classifications, {len(decisions) - n_real} fallback)")


if __name__ == "__main__":
    main()
