# IELTS Candidate Assistant

CSS 4007 final project, level C. A trilingual (Kazakh, Russian, English) agent that answers IELTS registration questions from tool results instead of from the model's memory. The design is in [reports/proposal.md](reports/proposal.md). Progress is in [reports/](reports/).

All schedules, fees and rules in [data/](data/) are mock data for a fictional test centre. They are simplified and are not official IELTS policy.

## Status (week 11)

- Model adapter `complete(messages, tools)` in [ielts_agent/model_client.py](ielts_agent/model_client.py), working with `gpt-5.6-luna` through the OpenAI Chat Completions API.
- Command line prototype: one question in, one answer out, with the token count, time and cost.
- System prompt v0: reply in the user's language and never invent dates or fees (no tools yet).
- Mock data: 12 sessions in 3 cities, fee and refund windows, results rules, a 12-section policy handbook, city aliases in three languages.
- 16 pytest tests that run without an API key.

Tools, the agent loop and answer validation come in weeks 12 to 14.

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
  prompts.py        system prompt
  __main__.py       command line interface
data/
  sessions.json     mock test sessions
  fees.json         transfer / cancellation windows, results timing
  policy.jsonl      mock policy handbook, one section per line
  cities.json       city name aliases (EN / RU / KZ, old names)
tests/
  test_model_client.py   adapter tests with a fake client
  test_data_files.py     consistency of the mock data
```

## Design decisions

- **One adapter.** Only `model_client.py` imports the `openai` SDK. The rest of the code gets a `ModelReply` (`text`, `tool_calls`, token usage) or a `ModelError`. Changing the provider means changing one file or `LLM_BASE_URL`.
- **No temperature parameter.** `gpt-5.6-luna` rejects any temperature except the default (seen in HW4), so the adapter does not send it.
- **`reasoning_effort="none"`.** The model refuses function tools with any other value. It is configurable, because other providers may not support the parameter.
- **Retries.** The OpenAI SDK retries timeouts, 429 and 5xx up to 3 times with back-off. After that the error becomes a short `ModelError`, and the CLI exits with code 1 instead of a stack trace.
- **Testable without the API.** `complete()` accepts an injected client, so the tests use a fake client and never need a key or the network.

## AI assistance

Claude Code (Anthropic) helped write the code, tests and mock data in this repository. I reviewed and ran everything and can explain each part.
