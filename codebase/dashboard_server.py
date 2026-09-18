"""Local dashboard: view bot_gateway.py's run workflow log, and browse the
demo CSV packs as a full chat transcript.

stdlib http.server only -- a JSON API + one static page doesn't need a new
dependency (same reasoning already used for notify/discord_client.py's raw
urllib instead of requests).

Run from the codebase/ directory:

    python3 dashboard_server.py

Then open http://localhost:8765 -- no browser is auto-launched, for
portability across machines/setups.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from ai_decide.stub import Decision, decide
from data.discord_live import fetch_recent_messages
from data.loader import Message, load_messages, load_test_case
from detect.rules import explain_detection, find_unanswered_questions
from notify.dashboard_log import log_run, read_llm_traces, read_run, read_runs

load_dotenv()  # must run before any os.environ.get() below, or .env-only values are silently ignored

PORT = 8765
DASHBOARD_HTML_PATH = Path(__file__).resolve().parent / "dashboard" / "index.html"
# Deliberately duplicated from bot_gateway.py rather than imported -- importing
# that module would require live Discord bot credentials (its module-level
# SystemExit check) and instantiate a discord.Client just for two path
# constants, even though this server never touches Discord itself.
DISCORD_PACK_DIR = Path(__file__).resolve().parent.parent / "data" / "discord-pack"
EVAL_TESTCASES_DIR = Path(__file__).resolve().parent.parent / "eval" / "testcases"  # golden set, spec.md §7
DEMO_CACHE_DIR = Path("output/demo_cache")

# Pipeline constants for the dashboard's own "Run" button (/api/run) --
# same values as bot_gateway.py's, duplicated for the same reason as the
# path constants above: no import from bot_gateway.py.
MIN_HOURS_UNANSWERED = 4.0  # CSV/testcase datasets -- matches bot_gateway.py's demo-path threshold
MAX_CONTEXT_HOURS = MIN_HOURS_UNANSWERED + 2.0  # bounds the LLM context window
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini")

# Live-chat transcript support -- reads the same env vars as bot_gateway.py,
# but degrades gracefully (LIVE_AVAILABLE=False) instead of raising, since
# this server should still be usable for the CSV/log views without a bot
# configured at all.
LIVE_MIN_HOURS_UNANSWERED = float(os.environ.get("LIVE_MIN_HOURS_UNANSWERED", "0.5"))
LOOKBACK_SAFETY_MARGIN_HOURS = 2.0
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
CHANNEL_IDS = [c.strip() for c in os.environ.get("DISCORD_CHANNEL_IDS", "").split(",") if c.strip()]
LIVE_AVAILABLE = bool(BOT_TOKEN and GUILD_ID and CHANNEL_IDS)


def _enrich_run_with_expected(run: dict) -> dict:
    """When a logged run's source is an eval/testcases/*.json golden-set
    case, attaches that case's ground-truth `expected` entry to each
    candidate in `ai_review` (by msg_id), so the Runs & Workflow tab can
    show the same actual-vs-expected comparison the Chat Transcript tab
    shows -- without changing what log_run() actually wrote to disk."""
    source = run.get("source", "")
    if not source.endswith(".json"):
        return run
    case_path = EVAL_TESTCASES_DIR / source
    if not case_path.exists():
        return run

    _messages, case = load_test_case(case_path)
    expected_by_id = {q["msg_id"]: q for q in case.get("expected_output", {}).get("questions", [])}
    enriched = dict(run)
    enriched["case_description"] = case.get("description")
    enriched["ai_review"] = [
        {**entry, "expected": expected_by_id.get(entry["msg_id"])} for entry in run.get("ai_review", [])
    ]
    return enriched


def _run_summary(run: dict) -> dict:
    return {
        "run_id": run["run_id"],
        "command": run["command"],
        "source": run["source"],
        "started_at": run["started_at"],
        "n_candidates": len(run.get("candidates", [])),
        "n_posted": len(run.get("posted", [])),
    }


def _message_to_dict(m: Message) -> dict:
    return {
        "msg_id": m.msg_id,
        "channel": m.channel,
        "guild": m.guild,
        "is_bot": m.is_bot,
        "created_at": m.created_at.isoformat(),
        "reply_to": m.reply_to,
        "content": m.content,
    }


def _most_recent_ai_review(command: str, source: str | None = None) -> dict:
    """Best-effort lookup of the most recently logged run's ai_review,
    keyed by msg_id -- reused so a transcript page render never needs a
    fresh LLM call just to display something."""
    for run in reversed(read_runs()):
        if run.get("command") != command:
            continue
        if source is not None and run.get("source") != source:
            continue
        return {a["msg_id"]: a for a in run.get("ai_review", [])}
    return {}


def _load_dataset_transcript(dataset: str) -> dict:
    csv_path = DISCORD_PACK_DIR / dataset
    messages = load_messages(csv_path)

    cache_path = DEMO_CACHE_DIR / f"{Path(dataset).stem}.json"
    decisions_by_id = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        decisions_by_id = {d["msg_id"]: d for d in cache["decisions"]}

    rows = []
    for m in messages:
        row = _message_to_dict(m)
        row["decision"] = decisions_by_id.get(m.msg_id)  # None if never a candidate
        rows.append(row)
    return {"dataset": dataset, "messages": rows}


def _load_live_transcript() -> dict:
    """Fetches the real channel using the same 30-min-ish lookback window as
    /labcoach-check (LIVE_MIN_HOURS_UNANSWERED + LOOKBACK_SAFETY_MARGIN_HOURS),
    so "show the live chat" reflects exactly what that command would see.

    No AI decision is computed here (this endpoint doesn't call the LLM --
    a page load shouldn't burn API quota) -- instead it best-effort reuses
    the most recent logged /labcoach-check run's ai_review for rationale, if
    one exists and is recent enough to still be relevant; otherwise a
    candidate just shows as rule-based-flagged, unreviewed.
    """
    now = datetime.now()
    since = now - timedelta(hours=LIVE_MIN_HOURS_UNANSWERED + LOOKBACK_SAFETY_MARGIN_HOURS)
    messages = fetch_recent_messages(CHANNEL_IDS, GUILD_ID, BOT_TOKEN, since)
    candidates = find_unanswered_questions(messages, now=now, min_hours_unanswered=LIVE_MIN_HOURS_UNANSWERED)
    candidate_ids = {c.message.msg_id for c in candidates}

    ai_by_id = _most_recent_ai_review("labcoach-check")

    rows = []
    for m in messages:
        row = _message_to_dict(m)
        if m.msg_id in candidate_ids:
            # Defaults to NOT flagged -- detect/rules.py now only excludes
            # bot messages, so most of the live channel qualifies as a rule-
            # based candidate; without a logged AI review, "needs attention"
            # isn't a real judgment, just an unreviewed default.
            row["decision"] = ai_by_id.get(m.msg_id) or {
                "msg_id": m.msg_id,
                "source": "unreviewed",
                "still_needs_attention": False,
                "confidence": None,
                "rationale": "Rule-based candidate -- run /labcoach-check in Discord to get an AI review",
            }
        else:
            row["decision"] = None
        rows.append(row)
    return {"dataset": "live", "messages": rows}


def _load_testcase_transcript(dataset: str) -> dict:
    """eval/testcases/*.json golden-set case -- unlike a plain CSV dataset,
    each message also gets its ground-truth `expected` label (from
    expected_output.questions), so the transcript is a real eval/comparison
    view, not just a chat log. `decision` is the same best-effort reuse of
    the most recently logged /labcoach-demo run for this exact case (no
    fresh LLM call just to render the page)."""
    messages, case = load_test_case(EVAL_TESTCASES_DIR / dataset)
    expected_by_id = {q["msg_id"]: q for q in case.get("expected_output", {}).get("questions", [])}
    ai_by_id = _most_recent_ai_review("labcoach-demo", source=dataset)

    rows = []
    for m in messages:
        row = _message_to_dict(m)
        row["expected"] = expected_by_id.get(m.msg_id)
        row["decision"] = ai_by_id.get(m.msg_id)
        rows.append(row)
    return {"dataset": dataset, "messages": rows, "case": {"case_id": case.get("case_id"), "description": case.get("description")}}


def _load_dataset_messages(dataset: str) -> list[Message]:
    """Same split as bot_gateway.py's own _load_dataset_messages -- .json is
    an eval/testcases golden-set case, .csv is the plain discord-pack
    format. Duplicated rather than imported for the same reason as the path
    constants above."""
    if dataset.endswith(".json"):
        messages, _case = load_test_case(EVAL_TESTCASES_DIR / dataset)
        return messages
    return load_messages(DISCORD_PACK_DIR / dataset)


def _ai_source(decision: Decision, used_cache: bool) -> str:
    if decision.rationale.startswith("[Rule-based only] Not in demo cache"):
        return "cache-miss-fallback"
    if decision.rationale.startswith("[Rule-based only]"):
        return "rule-based-cap"
    return "cache" if used_cache else "live-ai"


def _load_cached_decisions(dataset: str, candidates: list) -> list[Decision] | None:
    cache_path = DEMO_CACHE_DIR / f"{Path(dataset).stem}.json"
    if not cache_path.exists():
        return None
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    cached_by_id = {d["msg_id"]: d for d in cache["decisions"]}
    decisions = []
    for c in candidates:
        cached = cached_by_id.get(c.message.msg_id)
        if cached is None:
            # An incomplete cache cannot silently clear unreviewed candidates.
            return None
        else:
            decisions.append(
                Decision(
                    candidate=c,
                    still_needs_attention=cached["still_needs_attention"],
                    confidence=cached["confidence"],
                    rationale=cached["rationale"],
                )
            )
    return decisions


def run_pipeline_and_log(dataset: str) -> dict:
    """The dashboard's own "Run" button -- same detect -> cache/AI-review ->
    log pipeline bot_gateway.py's /labcoach-demo uses (same log_run() record
    shape, so it shows up identically in the Runs tab), triggered from the
    dashboard instead of a Discord interaction. No Discord posting -- this
    is purely local/analysis."""
    messages = _load_dataset_messages(dataset)
    now = max(m.created_at for m in messages)

    run_id = f"{datetime.now():%Y%m%dT%H%M%S%f}"
    record: dict = {
        "run_id": run_id,
        "command": "dashboard-run",
        "source": dataset,
        "started_at": datetime.now().isoformat(),
        "now": now.isoformat(),
        "fetch": {"message_count": len(messages), "min_hours_unanswered": MIN_HOURS_UNANSWERED},
    }

    breakdown = explain_detection(messages, now=now, min_hours_unanswered=MIN_HOURS_UNANSWERED)
    candidates = breakdown.candidates
    record["detection_breakdown"] = {
        "total_messages": breakdown.total_messages,
        "bot_messages": breakdown.bot_messages,
        "candidates": len(breakdown.candidates),
    }
    record["candidates"] = [
        {
            "msg_id": c.message.msg_id,
            "channel": c.message.channel,
            "content": c.message.content,
            "hours_since_posted": c.hours_since_posted,
        }
        for c in candidates
    ]
    if not candidates:
        record["ai_review"] = []
        record["posted"] = []
        log_run(record)
        return record

    used_cache = True
    decisions = _load_cached_decisions(dataset, candidates)
    if decisions is None:
        used_cache = False
        decisions = decide(candidates, all_messages=messages, provider=LLM_PROVIDER)

    record["ai_review"] = [
        {
            "msg_id": d.candidate.message.msg_id,
            "source": _ai_source(d, used_cache),
            "still_needs_attention": d.still_needs_attention,
            "confidence": d.confidence,
            "rationale": d.rationale,
        }
        for d in decisions
    ]
    record["posted"] = [d.candidate.message.msg_id for d in decisions if d.still_needs_attention]
    log_run(record)
    return record


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server's required method name)
        path = urlparse(self.path).path

        if path == "/":
            self._send_html(DASHBOARD_HTML_PATH.read_text(encoding="utf-8"))
            return

        if path == "/api/runs":
            runs = read_runs()
            self._send_json([_run_summary(r) for r in reversed(runs)])
            return

        if path.startswith("/api/runs/"):
            run_id = path.removeprefix("/api/runs/")
            run = read_run(run_id)
            if run is None:
                self._send_json({"error": "run not found"}, status=404)
                return
            self._send_json(_enrich_run_with_expected(run))
            return

        if path.startswith("/api/traces/"):
            msg_id = path.removeprefix("/api/traces/")
            self._send_json(read_llm_traces(msg_id))
            return

        if path == "/api/datasets":
            names = sorted(p.name for p in DISCORD_PACK_DIR.glob("*.csv"))
            names += sorted(p.name for p in EVAL_TESTCASES_DIR.glob("*.json"))
            if LIVE_AVAILABLE:
                names = ["live"] + names
            self._send_json(names)
            return

        if path.startswith("/api/datasets/") and path.endswith("/transcript"):
            dataset = path.removeprefix("/api/datasets/").removesuffix("/transcript")
            if dataset == "live":
                if not LIVE_AVAILABLE:
                    self._send_json(
                        {"error": "Live fetch not configured -- set DISCORD_BOT_TOKEN, DISCORD_GUILD_ID, DISCORD_CHANNEL_IDS in .env"},
                        status=400,
                    )
                    return
                try:
                    self._send_json(_load_live_transcript())
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=502)
                return

            if dataset.endswith(".json"):
                case_path = EVAL_TESTCASES_DIR / dataset
                if not case_path.exists():
                    self._send_json({"error": f"no such dataset: {dataset}"}, status=404)
                    return
                self._send_json(_load_testcase_transcript(dataset))
                return

            csv_path = DISCORD_PACK_DIR / dataset
            if not csv_path.exists():
                self._send_json({"error": f"no such dataset: {dataset}"}, status=404)
                return
            self._send_json(_load_dataset_transcript(dataset))
            return

        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802 (http.server's required method name)
        path = urlparse(self.path).path

        if path == "/api/run":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send_json({"error": "invalid JSON body"}, status=400)
                return

            dataset = body.get("dataset", "")
            if dataset == "live":
                self._send_json({"error": "Use /labcoach-check in Discord to run against the live channel"}, status=400)
                return
            dataset_dir = EVAL_TESTCASES_DIR if dataset.endswith(".json") else DISCORD_PACK_DIR
            if not (dataset_dir / dataset).exists():
                self._send_json({"error": f"no such dataset: {dataset}"}, status=404)
                return

            try:
                record = run_pipeline_and_log(dataset)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=502)
                return
            self._send_json(record)
            return

        self._send_json({"error": "not found"}, status=404)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 (matches base class signature)
        pass  # quiet by default -- flip this on if you need request-level debugging


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Dashboard running at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
