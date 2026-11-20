"""Tests of the structured answer validation and grounding check (no API)."""
import json

import pytest

from ielts_agent.answer import check_answer, detect_language, validate_answer
from ielts_agent.core import calculate_change_fee

FEE_RESULT = [{"tool": "calculate_change_fee",
               "result": calculate_change_fee("ALA-1212-CD", "transfer", "2026-11-20")}]


def answer(**overrides):
    base = {"language": "ru", "answer": "Перенос стоит 60 000 тенге.",
            "facts": [{"label": "transfer fee", "value": 60000}, {"label": "test date", "value": "2026-12-12"}],
            "sources": ["ALA-1212-CD", "TR-2"], "tools_used": ["calculate_change_fee"], "needs_human": False}
    return {**base, **overrides}


@pytest.mark.parametrize("text, lang", [
    ("When is the test?", "en"), ("Когда тест?", "ru"), ("Тест қашан болады?", "kk"),
    ("Есть ли paper test в Нур-Султане?", "ru"), ("2026-12-12", None),
    ("Алматыда тест бар ма?", "kk"),                 # Kazakh without Kazakh-only letters
    ("Сколько стоит перенос на март?", "ru"),        # "ма" inside a Russian word is not a match
    ("Можно ли перенести тест на другую дату?", "ru"),
])
def test_detect_language(text, lang):
    assert detect_language(text) == lang


def test_grounded_answer_passes_and_extra_keys_are_dropped():
    v = validate_answer(json.dumps({**answer(), "debug": "x"}), FEE_RESULT, "Сколько стоит перенос?")
    assert v.ok and v.answer == answer()


def test_fact_values_match_in_any_scalar_form():
    facts = [{"label": "fee", "value": "60000"}, {"label": "fee", "value": 60000.0},
             {"label": "session", "value": "ala-1212-cd"}]
    assert check_answer(answer(facts=facts), FEE_RESULT, "Сколько?") == []


def test_invented_amount_is_rejected_and_replaced_by_fallback():
    v = validate_answer(answer(facts=[{"label": "transfer fee", "value": 45000}]), FEE_RESULT, "Сколько стоит перенос?")
    assert not v.ok and "fact not found" in v.errors[0]
    assert v.answer["needs_human"] is True and v.answer["language"] == "ru"
    assert "сотрудникам" in v.answer["answer"]


def test_facts_without_any_tool_call_are_rejected():
    errors = check_answer(answer(), [], "Сколько стоит перенос?")
    assert any("fact not found" in e for e in errors)
    assert any("source not found" in e for e in errors)
    assert any("was not called" in e for e in errors)


def test_answer_without_facts_and_tools_is_valid():
    a = {"language": "kk", "answer": "Кестені әзірге көре алмаймын.", "facts": [], "sources": [],
         "tools_used": [], "needs_human": True}
    assert validate_answer(a, [], "Тест қашан?").ok


@pytest.mark.parametrize("raw, message", [
    ("not json", "not valid JSON"),
    ("[1, 2]", "not a JSON object"),
    (json.dumps({k: v for k, v in answer().items() if k != "facts"}), "missing field 'facts'"),
    (answer(needs_human="no"), "'needs_human' must be bool"),
    (answer(language="de"), "language must be one of"),
    (answer(answer="  "), "empty"),
    (answer(tools_used=["delete_booking"]), "unknown tool"),
    (answer(facts=["60000"]), "must be an object"),
])
def test_malformed_answers_are_rejected(raw, message):
    errors = check_answer(raw, FEE_RESULT, "Сколько стоит перенос?")
    assert any(message in e for e in errors), errors


def test_answer_language_must_match_cyrillic_user_message():
    errors = check_answer(answer(language="en"), FEE_RESULT, "Сколько стоит перенос?")
    assert any("does not match" in e for e in errors)
    kk = validate_answer(answer(language="ru"), FEE_RESULT, "Ауыстыру қанша тұрады?")
    assert not kk.ok and kk.answer["language"] == "kk"   # fallback in the user's language
