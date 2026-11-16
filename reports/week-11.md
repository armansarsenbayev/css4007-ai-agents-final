# Semester Week 11 Progress Report

## Completed Work

- Set up the Python environment: `requirements.txt` (`openai`, `python-dotenv`, `pytest`), `pytest.ini`, a `.venv`, and an updated `.env.example` with `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` and `LLM_REASONING_EFFORT`. Checked that `.env` and `logs/` are in `.gitignore`.
- Implemented the model adapter `complete(messages, tools)` in `ielts_agent/model_client.py`. It sends one Chat Completions request and returns a `ModelReply` with the text, the tool calls (name and raw JSON arguments), input and output tokens, time and cost. It can also turn the reply back into an assistant message, which the agent loop will need in week 14 to send tool results back to the model.
- Error handling in the adapter: a missing key, a rejected key, rate limit (429), timeout, connection error, a rejected request (400) and server errors (5xx) all become one `ModelError` with a short message. The OpenAI SDK retries timeouts, 429 and 5xx up to 3 times with back-off before that.
- Wrote system prompt v0 (`ielts_agent/prompts.py`): answer in the language of the user, do not mix languages, and never invent dates, seats, fees or results dates while the tools do not exist yet.
- Made a command line prototype: `python -m ielts_agent "question"` prints the answer and the model, tokens, time and cost; `--json` prints the same as JSON. An empty question and model errors give a clear message and a non-zero exit code.
- Wrote the first version of the mock data in `data/`: 12 test sessions in Almaty, Astana and Shymkent (December 2026 to February 2027), transfer and cancellation windows with fees and refunds, results timing for computer and paper tests, a 12-section policy handbook, and city aliases in English, Russian and Kazakh including old names (Алма-Ата, Нур-Султан, Акмола).
- Wrote 16 pytest tests that run without an API key: 9 for the adapter (with a fake client) and 7 for the consistency of the mock data. Added the Python tests to the GitHub Actions workflow.
- Added `PROJECT.md` with setup, configuration, run and test instructions and the design decisions.

AI assistance: I used Claude Code (Anthropic) to write the adapter, tests and mock data together with me. I ran the tests and the first real requests myself and checked every file.

## Important Commits

- Week 11 commit: "Week 11: model adapter, CLI prototype, mock data and tests" (`ielts_agent/`, `data/`, `tests/test_*.py`, `requirements.txt`, `.env.example`, `PROJECT.md`, workflow). The hash is shown by `git log` and `npm run activity`.

## Current Functionality

The application can take a question in Kazakh, Russian or English from the command line, send it to `gpt-5.6-luna` with the system prompt, and print the answer with token usage and cost. It does not have tools yet, so for questions about dates and fees the prompt makes it say that it cannot look them up instead of inventing them. General questions (for example Academic versus General Training) are answered directly.

First real run (`python -m ielts_agent "<question>"`):

TODO: paste the output of the first real requests here (English, Russian and Kazakh question), including the token and cost line.

Tests: `python -m pytest -q` gives 16 passed; `npm test` passes.

## Problems Encountered

1. The newest `openai` package (3.x) no longer uses `httpx` but `httpx2`, so my tests that build SDK exception objects failed with `ModuleNotFoundError: No module named 'httpx'`.
2. My first data test assumed that the session id starts with the first three letters of the city, so it expected `ALM-1205-PB` instead of `ALA-1205-PB`.
3. The Windows console uses an old code page and cannot print Kazakh letters such as ә, ғ, қ, ң.
4. `gpt-5.6-luna` rejects any temperature other than the default and refuses tool definitions unless `reasoning_effort="none"` (I already saw this in HW4), but other providers (OpenRouter backup) may not accept `reasoning_effort` at all.
5. Tests must not depend on an API key, otherwise CI fails and every test run costs money.

## Solutions

1. The tests import `httpx2` and fall back to `httpx`, so they work with both versions of the SDK.
2. Session ids use airport-style city codes (ALA, AST, SHY). The test now has an explicit `CITY_CODE` table; it also checks that the registration deadline is 5 days before a computer test and 14 days before a paper test.
3. The CLI switches `stdout` to UTF-8 before printing.
4. The adapter never sends `temperature`, and `reasoning_effort` comes from `LLM_REASONING_EFFORT` (default `none`, empty means not sent).
5. `complete()` accepts an injected client. The tests use a fake client that records the request and returns prepared responses or raises prepared errors.

## What I Learned

- How to keep all provider-specific code in one adapter and give the rest of the program one simple result type and one error type. This also makes the code easy to test.
- What the OpenAI SDK already does for reliability (automatic retries with back-off for 429, 5xx and timeouts) and which errors I still have to handle myself.
- How tool calls come back from the API: `message.tool_calls`, each with an id, a function name and the arguments as a JSON string, and that this message has to be added to the conversation before the tool results.
- Writing tests for data consistency is useful before writing the tools: the test that every day from 0 to 400 falls into exactly one fee window guarantees that the fee tool will never find zero or two rules.

## Next Week

- Implement `load_data()` and `normalize_city()` with the alias table and suggestions for unknown cities.
- Implement the core functions on the mock data (session search, fee calculation, results date) as plain Python functions with input validation.
- Define the structured final answer (`language`, `answer`, `facts`, `sources`, `tools_used`, `needs_human`) and its validation.
- Add unit tests for these functions.
