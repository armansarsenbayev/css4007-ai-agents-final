# Semester Week 12 Progress Report

## Completed Work

- **Data loading** (`ielts_agent/data.py`): `load_data()` reads the schedule, fee rules, policy handbook and city aliases once and checks their structure (unique session ids, valid ISO dates, allowed module and delivery values, required fee keys, required handbook fields). A broken file raises `DataError` at start-up instead of causing wrong answers later.
- **`normalize_city`** (`ielts_agent/core.py`): maps city names in English, Russian and Kazakh, old names (Алма-Ата, Нур-Султан, Ақмола), different dashes and upper/lower case to one canonical name. It also removes Russian and Kazakh case endings ("Алматыда", "Нур-Султане", "Астанаға", "Шымкентте"), but only when the rest is an exact known name. A misspelled or unknown city is never corrected: the function returns `None` and similar cities as suggestions.
- **Core functions** on the mock data, which will become the LLM tools in week 13:
  - `find_test_sessions(city, module, delivery, date_from, date_to)`: filters and sorts sessions, hides past sessions, and marks each session `open`, `full` or `registration_closed`.
  - `calculate_change_fee(session_id, action, request_date)`: counts the days before the test, finds the transfer or cancellation window and returns the fee or refund with the rule id.
  - `estimate_results_date(session_id)`: test date + 3 days (computer) or + 13 days (paper).
  - `search_policy(query, top_k)`: my own small BM25 implementation (k1 = 1.5, b = 0.75) over the 12 handbook sections, so no extra library is needed.
- **Input validation**: every function checks types, enum values (`academic`/`general`, `computer`/`paper`, `transfer`/`cancel`), ISO dates, `date_from <= date_to`, `top_k` from 1 to 5, query length, and unknown session ids (with similar ids as suggestions). Bad input returns `{"error": ..., "hint": ...}` instead of an exception, so the model will be able to read the problem and fix its call.
- **Structured output** (`ielts_agent/answer.py`): the model now has to reply with a JSON object `{language, answer, facts, sources, tools_used, needs_human}` (requested with `response_format={"type": "json_object"}`). `validate_answer()` checks the fields and types, that the language matches the user's message, that `tools_used` contains only tools that were really called, and that every value in `facts` and `sources` appears in a tool result (grounding check). If anything fails, the user gets a fallback answer in their language with `needs_human: true`.
- **Language detection** `detect_language()` for the validator and the fallback: Kazakh-only letters or frequent Kazakh words → `kk`, other Cyrillic → `ru`, Latin → `en`.
- **System prompt v1**: rules for Kazakh, Russian, English and mixed messages, the JSON format and the rule that facts may only come from tool results.
- **CLI**: `--json` prints the full structured answer, and `--call FUNCTION '{json args}'` runs a core function directly without the model.
- **Tests**: 75 new pytest tests (91 in total, all without an API key): data loading, 15 city spellings, filters and statuses, fee window boundaries (35/34/14/13 days and the test day), refunds, results dates across the new year, policy search for 7 typical questions, invalid input for every function, language detection, answer validation, grounding and fallback, CLI.

AI assistance: I used Claude Code (Anthropic) to write the functions and tests together with me. I ran all tests and the real requests and checked the results.

## Important Commits

- "Week 12: data loading, normalize_city and core functions with input validation" (`ielts_agent/data.py`, `ielts_agent/core.py`, `tests/test_core.py`).
- "Week 12: structured JSON answer with grounding check and prompt v1" (`ielts_agent/answer.py`, `ielts_agent/prompts.py`, `ielts_agent/model_client.py`, `ielts_agent/__main__.py`, `tests/test_answer.py`, `tests/test_model_client.py`).
- "Week 12: documentation and progress report" (`PROJECT.md`, `reports/week-12.md`).

The hashes are shown by `git log` and `npm run activity`.

## Current Functionality

The core functions work on the mock data and can be run from the command line:

```text
$ python -m ielts_agent --call calculate_change_fee '{"session_id": "ala-1212-cd", "action": "transfer"}'
{"session_id": "ALA-1212-CD", "action": "transfer", "test_date": "2026-12-12", "request_date": "2026-11-20",
 "days_before_test": 22, "rule_id": "TR-2", "test_fee_kzt": 128000, "allowed": true, "fee_kzt": 60000,
 "policy_section": "POL-06"}

$ python -m ielts_agent --call find_test_sessions '{"city": "Нур-Султане", "date_from": "2026-12-01", "date_to": "2026-12-31"}'
→ city "Astana", 2 sessions: AST-1205-CD (seats_left 0, status "full"), AST-1219-PB (seats_left 7, status "open")

$ python -m ielts_agent --call find_test_sessions '{"city": "Almatu"}'
→ {"error": "There are no test sessions in 'Almatu'.", "available_cities": ["Almaty", "Astana", "Shymkent"], "similar_cities": ["Almaty"]}
```

The model answers in the structured format, and every answer is validated. Real run with `gpt-5.6-luna` (prompt v1, no tools yet):

| Question | language | needs_human | validation | tokens in / out | cost |
|---|---|---|---|---|---|
| Алматыда тест бар ма? | kk | true | ok | 492 / 83 | $0.000198 |
| Я записан на ALA-1212-CD. Сколько будет стоить перенос сегодня? | ru | true | ok | 504 / 87 | $0.000205 |
| What is the difference between IELTS Academic and General Training? | en | false | ok | 496 / 108 | $0.000229 |
| What band score will I get if I study for two weeks? | en | false | ok | 498 / 92 | $0.000210 |

```json
{
  "language": "kk",
  "answer": "Алматыдағы IELTS тесті туралы нақты күндер мен бос орындарды қазір тексере алмаймын. Нақты ақпарат алу үшін тест орталығына хабарласыңыз. Мен тіркеу немесе тест күнін брондау әрекеттерін орындай алмаймын.",
  "facts": [], "sources": [], "tools_used": [], "needs_human": true
}
```

The model chose the right language every time, returned valid JSON, left `facts` empty because it had no tool results, and set `needs_human` for the schedule and fee questions. The model still cannot call the core functions; that is week 13.

Tests: `python -m pytest -q` gives 91 passed; `npm test` passes.

## Problems Encountered

1. **Kazakh detected as Russian.** My first `detect_language()` only looked for Kazakh-only letters (ә, ғ, қ, ң, ө, ұ, ү, һ, і). The test with "Алматыда тест бар ма?" failed: this Kazakh sentence has none of these letters, so it was detected as Russian and a correct Kazakh answer would have been rejected.
2. **Facts from the user's message.** In week 11 the model repeated the session id "ALA-1212-CD" from the question. With the grounding check such an id would count as an invented fact, because it is not in any tool result.
3. **Weak policy search for questions the handbook does not cover.** "parking near the centre" still returns POL-09 and POL-02 (score about 1.6) only because the word "centre" appears there. Correct matches score 6 to 9.
4. **City names in grammatical cases.** Users write "в Нур-Султане" or "Алматыда", which are not in the alias table.
5. **The longer prompt costs more.** The input grew from 213 to about 495 tokens per request after adding the JSON format and the language rules, so a request costs about twice as much (still about $0.0002).
6. **Date-dependent results.** Session status and the transfer fee depend on today's date, so tests would start failing over time.

## Solutions

1. I added a small list of frequent Kazakh words that contain no Kazakh-only letters and are not Russian words (бар, ма, ме, керек, неше, туралы, ...), matched as whole words. Tests check that "Алматыда тест бар ма?" is `kk` while "Сколько стоит перенос на март?" stays `ru`.
2. The prompt now says that values that only come from the user's message are not facts or sources. The answer text can still repeat them.
3. Not solved yet, but recorded. The model will also see the scores; in week 16 I will measure a minimum score threshold on the evaluation set instead of guessing a number from four queries now.
4. `normalize_city` removes common Russian and Kazakh case endings, but only if the rest is an exact alias. This handles grammar without fuzzy guessing ("Almatu" is still not corrected).
5. Accepted for now: about $0.0002 per request is very small. I will count tokens again when the tool definitions are added in week 13.
6. All functions take an optional `today` parameter, used only in tests (it is not exposed to the model or the CLI), and the tests use a fixed date, 2026-11-20.

## What I Learned

- How BM25 works in detail: IDF gives weight to rare words, and the length normalisation (`b`) stops long sections from winning just because they are long. I also saw its weakness: it scores word overlap, not meaning.
- Grounding is easier to check on structured data than on free text. Keeping language-neutral `facts` next to the multilingual answer text avoids parsing "12 декабря" and "12 желтоқсан".
- Returning errors as data with a hint is better than raising exceptions when the caller is an LLM: the model can read the message and correct its arguments.
- Boundary tests matter for rules with day windows: the difference between 13 and 14 days changes the answer from "transfer for 60 000 KZT" to "no transfer".
- Language detection by letters alone is not enough for Kazakh, which shares most of its alphabet with Russian.

## Next Week

- Write JSON schemas for the four tools with precise parameter descriptions and register them with the model.
- Let the model choose the tools itself and write `search_policy` queries in English.
- Add argument validation before each tool call (types, enums, no extra keys) and a dispatcher `execute_tool` that never crashes.
- Log every tool call to `logs/tool_calls.jsonl`.
- First real requests where the model calls a tool and the answer passes the grounding check.
