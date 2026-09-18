"""Renders the LabCoach-facing list of still-open questions.

Console/file output only -- pure string-building, no network access. Real
delivery lives in notify/discord_client.py (send_to_discord), kept separate
so this module never needs a network call.

SAFETY: never print the raw `author` (D#### code) as a labeled identifier in
the report -- track-b-discord-assistant.md's safety notes say not to name or
identify students in anything that could be shown. msg_id + a placeholder
location + a short excerpt is enough for LabCoach to find the message
themselves.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ai_decide.stub import Decision

MAX_EXCERPT_SENTENCES = 2
EMBED_COLOR_AMBER = 0xF0B232


def _excerpt(content: str) -> str:
    """Truncates to <=2 sentences, matching data/discord-pack/README.md's
    citation rule -- enforced here, not just at some later "public" stage,
    since console output can end up in a screenshot for the pitch deck."""
    parts = [p.strip() for p in content.replace("\n", " ").split(".") if p.strip()]
    excerpt = ". ".join(parts[:MAX_EXCERPT_SENTENCES])
    if not excerpt:
        return content.strip()[:120]
    suffix = "..." if len(parts) > MAX_EXCERPT_SENTENCES else ""
    return excerpt + suffix


def _location(decision: Decision) -> str:
    """Placeholder location, not a real Discord link.

    The anonymized data pack has no real server/channel IDs (channel names
    are deliberately withheld -- data/discord-pack/DATA_DICTIONARY.md), so a
    working discord.com/channels/<guild>/<channel>/<msg_id> URL can't be
    built from this data. Swap this for a real link once live Discord IDs
    are available.
    """
    m = decision.candidate.message
    return f"[msg_id: {m.msg_id}, guild: {m.guild}, channel: {m.channel}]"


def format_report(decisions: list[Decision]) -> str:
    flagged = [d for d in decisions if d.still_needs_attention]
    if not flagged:
        return "No unanswered questions found."

    lines = [f"{len(flagged)} question(s) still need LabCoach attention:\n"]
    for d in flagged:
        c = d.candidate
        lines.append(
            f"- {_location(d)} · waiting {c.hours_since_posted:.1f}h\n"
            f"  \"{_excerpt(c.message.content)}\"\n"
            f"  ({d.rationale})"
        )
    return "\n".join(lines)


def _short_question(content: str) -> str:
    """Deterministic truncation to the first '?' -- every candidate has one
    (guaranteed by detect/rules.py's filter), so this never invents or
    paraphrases text, just trims it."""
    idx = content.find("?")
    return content[: idx + 1].strip() if idx != -1 else content.strip()


def format_candidate_embed(decision: Decision, min_hours_unanswered: float, tick_time: datetime) -> dict:
    """Builds one Discord embed dict matching outputs/workflow.jpg's message
    layout for a single still-unanswered candidate.

    SAFETY: same rule as _location() -- never put the (anonymized) author
    code in the "Học viên" field, per data/loader.py and
    track-b-discord-assistant.md's safety notes. The field is a placeholder,
    not the real identifier.

    No functional buttons -- Discord message components require a real bot
    with an interactions endpoint, which a plain incoming webhook (the only
    delivery path this project has) cannot provide.
    """
    c = decision.candidate
    m = c.message
    return {
        "title": "⚠️ Câu hỏi chưa được phản hồi",
        "color": EMBED_COLOR_AMBER,
        "fields": [
            {"name": "👤 Học viên", "value": "*(ẩn danh)*", "inline": True},
            {"name": "📍 Nguồn", "value": f"#{m.channel} · {m.guild}", "inline": True},
            {"name": "💬 Câu hỏi", "value": _short_question(m.content), "inline": False},
            {"name": "📝 Nội dung", "value": f"> *{_excerpt(m.content)}*", "inline": False},
            {
                "name": "🕐 Thời gian chờ",
                "value": f"{c.hours_since_posted:.1f} giờ · Đăng lúc {m.created_at:%Y-%m-%d %H:%M}",
                "inline": True,
            },
            {"name": "💬 Phản hồi", "value": "0 phản hồi · Chưa tiếp nhận", "inline": True},
            {
                "name": "🎯 Độ tin cậy",
                "value": f"{decision.confidence:.0%}" if decision.confidence is not None else "N/A",
                "inline": True,
            },
        ],
        "timestamp": tick_time.isoformat(),
    }


def write_report(report_text: str, out_path: str | Path) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_text, encoding="utf-8")
