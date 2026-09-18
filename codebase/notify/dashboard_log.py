"""Structured per-run logging for the local dashboard (dashboard_server.py).

Separate from ai_decide/logger.py's llm_traces.jsonl -- that one logs only
the AI classify step (raw prompt/response per candidate); this one logs a
full pipeline record per /labcoach-check or /labcoach-demo invocation
(fetch -> rule-based candidates -> AI review -> what got posted), which is
what the dashboard's workflow timeline actually needs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RUNS_LOG_PATH = Path("output/dashboard_logs/runs.jsonl")
# Same file ai_decide/logger.py's LLMAuditLogger writes to (its own
# __file__-relative default) -- resolved the same way here so reading it
# doesn't depend on the caller's cwd matching bot_gateway.py's.
LLM_TRACES_PATH = Path(__file__).resolve().parent.parent / "logs" / "llm_traces.jsonl"


def log_run(record: dict[str, Any]) -> None:
    RUNS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RUNS_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_runs() -> list[dict[str, Any]]:
    """All logged runs, oldest first. Empty list if nothing's been logged yet."""
    if not RUNS_LOG_PATH.exists():
        return []
    runs = []
    with RUNS_LOG_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                runs.append(json.loads(line))
    return runs


def read_run(run_id: str) -> dict[str, Any] | None:
    for run in read_runs():
        if run.get("run_id") == run_id:
            return run
    return None


def read_llm_traces(msg_id: str | None = None) -> list[dict[str, Any]]:
    """Reads ai_decide/logger.py's raw LLM audit trail (read-only -- that
    module is owned by the AI-logic teammate and stays untouched). Real
    proof a given answer came from an actual graph/model call: provider,
    exact model name, the full raw prompt sent, the full raw response, and
    latency -- a fallback or cached answer never has a matching entry here.
    Most recent first; optionally filtered to one candidate_msg_id."""
    if not LLM_TRACES_PATH.exists():
        return []
    traces = []
    with LLM_TRACES_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            trace = json.loads(line)
            if msg_id is None or trace.get("candidate_msg_id") == msg_id:
                traces.append(trace)
    return list(reversed(traces))
