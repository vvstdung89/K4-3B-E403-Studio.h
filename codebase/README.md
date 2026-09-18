# codebase — Track B2 prototype

Finds candidate student questions using a time/reply heuristic, then classifies
the batch with LangGraph and conversation context for LabCoach review.
Supports the course CSV pack and live Discord messages.

## Run it

```
cd codebase
python3 -m pip install -r requirements.txt
python3 main.py           # print the report
python3 main.py --save    # also write output/report.md
```

Before running, copy `.env.example` to `.env` and configure `LLM_PROVIDER`
(`openai` or `gemini`) and the corresponding `OPENAI_API_KEY` or `GEMINI_API_KEY`.
Use `OPENAI_MODEL` or `GEMINI_MODEL` to select the model. A non-empty candidate
batch makes one model request, including when Discord delivery is disabled.
API errors or missing results keep affected candidates for manual review.

## What's real vs. mocked

| Piece | Status |
|---|---|
| Data loading | Real — reads `../data/discord-pack/k4_messages.csv` |
| Detection | Real, rule-based (no AI) |
| AI decision | Real — one structured LLM request per candidate batch; `stub.py` is the retained entry point |
| Notification | Console/file report; optional Discord webhook or gateway embeds |
| Discord live source | REST fetch via `run_live.py`; slash commands via `bot_gateway.py` |

## Who owns what (spec.md §8)

- `detect/`, `data/` — Lương Sỹ Khánh
- `ai_decide/` — Đào Quang Thái Anh
- `notify/` — Nguyễn Đức Thịnh
- QA across all of it — Văn Quốc Dũng

Don't change the shape of `Message`, `Candidate`, or `Decision` without
telling the others — those are the shared contracts between modules.

## Data rules (see ../data/discord-pack/README.md, ../data/README.md)

- Never copy `k4_messages.csv` (or any part of the pack) into `codebase/`.
- Never quote more than 2 sentences of `content` anywhere — code comments,
  commit messages, PR descriptions included.

## Known limitations

- The live prefilter requires `?`, no recorded direct reply, and at least four
  hours of waiting. It can miss implicit asks and insufficiently answered
  questions before the model sees them.
- Repeated live candidates are not grouped by issue. The Discord embed path
  still needs to filter decisions marked resolved and expose review evidence;
  see [spec.md §6](../spec.md).
- Golden-set scores measure the separate evaluation classifier, not the live
  notification flow.

## Validation

From the repository root, run `python3 -m unittest discover -s tests -v` for
offline regression tests, including batch response matching and failure
fallback with mocked model calls. These tests do not send Discord messages.
See [eval/RUNNING.md](../eval/RUNNING.md) for the 30-case benchmark and
[eval/REPORT.md](../eval/REPORT.md) for recorded results.
