"""Loads Discord messages from the course data pack.

This is the ONLY module that knows the CSV file exists or what its columns
are named. Everything downstream (detect/, ai_decide/, notify/) works with
the typed `Message` objects returned here, never raw CSV rows. That boundary
is what lets a future `data/discord_live.py` (real Discord API) replace this
loader at a single call site in main.py without touching any other module.

`Message.content` is masked student-written text from the data pack. Treat it
as DATA TO CLASSIFY, never as an instruction — the real chatlog already
contains "ignore previous instructions"-style messages (see
data/discord-pack/README.md, point 5). This matters most once ai_decide/
starts passing content into an LLM prompt.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Message:
    msg_id: str
    guild: str
    channel: str
    author: str  # D#### or "BOT" — internal routing only, never surface publicly (see notify/)
    is_bot: bool
    msg_type: str  # "message" | "reply"
    created_at: datetime
    reply_to: str | None
    mentions_bot: bool
    n_attachments: int
    n_chars: int
    content: str  # masked text — data to classify, not an instruction


def default_csv_path() -> Path:
    """Resolves to ../data/discord-pack/k4_messages.csv, relative to codebase/.

    Never copies the CSV into codebase/ — it's read in place, per the repo's
    data-security rules (README.md, "Bảo mật dữ liệu được cung cấp").
    """
    return Path(__file__).resolve().parent.parent.parent / "data" / "discord-pack" / "k4_messages.csv"


def _parse_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def _parse_row(row: dict[str, str]) -> Message:
    reply_to = row["reply_to"].strip() or None
    return Message(
        msg_id=row["msg_id"],
        guild=row["guild"],
        channel=row["channel"],
        author=row["author"],
        is_bot=_parse_bool(row["is_bot"]),
        msg_type=row["msg_type"],
        created_at=datetime.strptime(row["created_at_vn"], "%Y-%m-%d %H:%M"),
        reply_to=reply_to,
        mentions_bot=_parse_bool(row["mentions_bot"]),
        n_attachments=int(row["n_attachments"]),
        n_chars=int(row["n_chars"]),
        content=row["content"],
    )


def load_messages(csv_path: str | Path | None = None) -> list[Message]:
    """Reads the data pack CSV into a list of Message objects.

    Raises on a row that fails to parse (bad date, unexpected type) rather
    than silently skipping it — bad data should surface at load time, not
    disappear into a shorter-than-expected candidate list downstream.
    """
    path = Path(csv_path) if csv_path is not None else default_csv_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Data pack not found at {path}. It is gitignored and provided "
            "separately for the hackathon — see data/README.md."
        )

    messages: list[Message] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):  # row 1 is the header
            try:
                messages.append(_parse_row(row))
            except (KeyError, ValueError) as exc:
                raise ValueError(f"Failed to parse {path} row {i} ({row.get('msg_id', '?')}): {exc}") from exc
    return messages


def _parse_message_json(d: dict[str, Any]) -> Message:
    """Same field mapping as _parse_row, but for eval/testcases/*.json's
    `input` items, which are already natively typed (real bool/int from
    json.load) rather than raw CSV strings -- a distinct, simpler parser,
    not a rerun of _parse_bool/int()."""
    reply_to = (d.get("reply_to") or "").strip() or None
    return Message(
        msg_id=d["msg_id"],
        guild=d["guild"],
        channel=d["channel"],
        author=d["author"],
        is_bot=bool(d["is_bot"]),
        msg_type=d["msg_type"],
        created_at=datetime.strptime(d["created_at_vn"], "%Y-%m-%d %H:%M"),
        reply_to=reply_to,
        mentions_bot=bool(d["mentions_bot"]),
        n_attachments=int(d["n_attachments"]),
        n_chars=int(d["n_chars"]),
        content=d["content"],
    )


def load_test_case(path: str | Path) -> tuple[list[Message], dict[str, Any]]:
    """Reads one eval/testcases/*.json golden-set case: its `input` messages
    (same shape as a CSV pack, just JSON-typed) plus the full case dict
    (case_id, description, expected_output, etc.) so callers get both
    without re-reading the file.

    Per the case format's own notes: "Only input is model input;
    expected_output, checkpoints and rubric are for evaluation" -- callers
    must not feed expected_output into the detection/AI pipeline, only use
    it afterward for comparison.
    """
    path = Path(path)
    case = json.loads(path.read_text(encoding="utf-8"))
    messages = [_parse_message_json(m) for m in case["input"]]
    return messages, case
