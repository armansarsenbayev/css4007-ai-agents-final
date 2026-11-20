# IELTS Candidate Assistant

CSS 4007 final project, level C. A trilingual (Kazakh, Russian, English) agent that answers IELTS registration questions from tool results instead of from the model's memory. The design is in [reports/proposal.md](reports/proposal.md). Progress is in [reports/](reports/).

All schedules, fees and rules in [data/](data/) are mock data for a fictional test centre. They are simplified and are not official IELTS policy.

## Status (week 12)

- Model adapter `complete(messages, tools, response_format)` in [ielts_agent/model_client.py](ielts_agent/model_client.py), working with `gpt-5.6-luna` through the OpenAI Chat Completions API.
- Core functions on the mock data in [ielts_agent/core.py](ielts_agent/core.py): `normalize_city`, `find_test_sessions`, `calculate_change_fee`, `estimate_results_date`, `search_policy` (BM25). They validate every input and return an error object instead of raising.
- Data loading with structure checks in [ielts_agent/data.py](ielts_agent/data.py).
- Structured final answer (`language`, `answer`, `facts`, `sources`, `tools_used`, `needs_human`) and its validation with a grounding check in [ielts_agent/answer.py](ielts_agent/answer.py). An invalid or ungrounded answer is replaced by a fallback in the user's language with `needs_human: true`.
- System prompt v1: language rule for Kazakh, Russian, English and mixed messages, and the JSON output format.
- 91 pytest tests that run without an API key.

Not yet connected: the model cannot call the core functions yet. Tool schemas, tool selection by the model and logging come in week 13, the multi-round agent loop in week 14.

## Setup

Requirements: Python 3.11+, and Node.js 22+ for the course repository checks.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # then put your key into LLM_API_KEY
```

| Variable | Meaning | Default |
|---|---|---|
| `LLM_API_KEY` | API key (`OPENAI_API_KEY` is also accepted) | none, required |
| `LLM_MODEL` | model name | `gpt-5.6-luna` |
| `LLM_BASE_URL` | OpenAI-compatible endpoint, e.g. `https://openrouter.ai/api/v1` | OpenAI |
| `LLM_REASONING_EFFORT` | sent as `reasoning_effort`; empty means not sent | `none` |

`.env` is in `.gitignore`. The key is only passed to the OpenAI client and is never printed or logged.

## Run

```bash
python -m ielts_agent "Are there computer-delivered Academic tests in Almaty in December?"
python -m ielts_agent --json "Алматыда желтоқсанда компьютерлік Academic тест бар ма?"

# run a core function directly, without the model
python -m ielts_agent --call find_test_sessions '{"city": "Нур-Султан", "date_from": "2026-12-01", "date_to": "2026-12-31"}'
python -m ielts_agent --call calculate_change_fee '{"session_id": "ALA-1212-CD", "action": "transfer"}'
python -m ielts_agent --call estimate_results_date '{"session_id": "AST-1219-PB"}'
python -m ielts_agent --call search_policy '{"query": "ID documents passport copy", "top_k": 2}'
```

## Tests

```bash
python -m pytest -q    # project tests, no API key needed
npm test               # course starter tests
npm run validate       # course report checks
```

## Project layout

```text
ielts_agent/
  config.py         settings from environment / .env, prices
  model_client.py   complete(): the only code that calls the LLM; maps provider errors to ModelError
  data.py           load_data(): reads and checks the data files
  core.py           normalize_city and the four core functions (future tools)
  answer.py         structured answer format, language detection, validation and grounding check
  prompts.py        system prompts v0 and v1
  __main__.py       command line interface (--json, --call)
data/
  sessions.json     mock test sessions
  fees.json         transfer / cancellation windows, results timing
  policy.jsonl      mock policy handbook, one section per line
  cities.json       city name aliases (EN / RU / KZ, old names)
tests/
  test_model_client.py   adapter tests with a fake client
  test_data_files.py     consistency of the mock data
  test_core.py           data loading, city names, the four core functions, input validation
  test_answer.py         language detection, answer validation, grounding check, fallback
```

## Design decisions

- **One adapter.** Only `model_client.py` imports the `openai` SDK. The rest of the code gets a `ModelReply` (`text`, `tool_calls`, token usage) or a `ModelError`. Changing the provider means changing one file or `LLM_BASE_URL`.
- **No temperature parameter.** `gpt-5.6-luna` rejects any temperature except the default (seen in HW4), so the adapter does not send it.
- **`reasoning_effort="none"`.** The model refuses function tools with any other value. It is configurable, because other providers may not support the parameter.
- **Retries.** The OpenAI SDK retries timeouts, 429 and 5xx up to 3 times with back-off. After that the error becomes a short `ModelError`, and the CLI exits with code 1 instead of a stack trace.
- **Errors as data.** Core functions return `{"error": ..., "hint": ...}` for bad input instead of raising, so in week 13 the model can read the problem and fix its next call. An unknown city is never corrected silently; the function returns similar cities as suggestions.
- **Language-neutral facts.** The answer text is in the user's language ("12 декабря", "12 желтоқсан"), but every date, amount and id the answer uses is also listed in `facts` as an ISO date, integer or id. The validator checks these values against the tool results, which is much simpler and safer than parsing dates in three languages.
- **Testable without the API.** `complete()` accepts an injected client, so the tests use a fake client and never need a key or the network.

## AI assistance

Claude Code (Anthropic) helped write the code, tests and mock data in this repository. I reviewed and ran everything and can explain each part.
