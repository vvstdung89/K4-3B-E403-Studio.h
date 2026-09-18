# Running the classifier evaluation

Run from the repository root using the existing virtual environment and API key in `codebase/.env`:

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$env:OPENAI_REASONING_EFFORT = 'medium'
$cases = (1..10 | ForEach-Object { 'K4-{0:D2}' -f $_ }) -join ','
.\.venv\Scripts\python.exe codebase\run_eval_benchmark.py --dir eval\golden_set --provider openai --model gpt-5.4 --cases $cases --reminder-policy per_issue
```

`--model` overrides the model only for that run. Without it, the runner uses the existing provider/model environment configuration. Selecting a reasoning model is material to the result; scores from different models must be reported separately.

The classifier uses two batched requests per window: request detection followed by evidence-based resolution. Empty-question windows need only detection. Incomplete index coverage is retried once, then reported as an evaluation error rather than silently converted to ignored messages. Expected labels, case descriptions and scoring rubrics are never passed to the model.

The formatter validates evidence references and derives labels and counts. It preserves every question record. With `per_issue`, repeated unresolved requests from the same author, channel and recipient type share one reminder; `per_message` keeps every unresolved message as a separate reminder.

The golden set in `eval/golden_set.json` and `eval/golden_set/` contains all 30 original testcases. The real cases K4-01–K4-10 specify grouped reminders. The synthetic cases K4-H11–K4-H30 explicitly specify independent reminder counting. Run the synthetic suite with its declared policy:

```powershell
$cases = (11..30 | ForEach-Object { 'K4-H{0}' -f $_ }) -join ','
.\.venv\Scripts\python.exe codebase\run_eval_benchmark.py --dir eval\golden_set --provider openai --model gpt-5.4 --cases $cases --reminder-policy per_message
```

The scorer checks question identities, available expected fields, counts and reminder membership. Fixtures with `input_index` use that index to distinguish messages sharing an ID; legacy fixtures without indexes use `msg_id`. Duplicate question identities fail. Reminder membership uses full message keys when the fixture supplies them. Data-quality flags are excluded from scoring. The scorer does not require identical explanation wording or claim to replace human review of semantic evidence. Logs are in `codebase/logs/llm_traces.jsonl`; benchmark stdout includes the formatted result and each mismatch. See [REPORT.md](REPORT.md) for the latest run; raw outputs remain local.

Offline regression tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

These changes concern the golden-set classifier. The live candidate-decision graph has a separate contract and is not covered by these benchmark scores.

For GPT-5 reasoning requests, the factory omits temperature and uses `OPENAI_REASONING_EFFORT` (default `medium`), following the [official parameter compatibility guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.4).
