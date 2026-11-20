"""Structured final answer: format, validation and grounding check.

The model must reply with one JSON object:

    {
      "language":    "kk" | "ru" | "en",
      "answer":      "text for the user, in the user's language",
      "facts":       [{"label": "transfer fee", "value": 60000}, {"label": "test date", "value": "2026-12-12"}],
      "sources":     ["ALA-1212-CD", "TR-2"],
      "tools_used":  ["calculate_change_fee"],
      "needs_human": false
    }

`facts` holds every date, amount, count or id the answer relies on, in a language-neutral
form (ISO dates, plain integers). The answer text can write "12 декабря" or "12 желтоқсан",
but the validator compares the facts with the tool results. A fact or source that does not
appear in any tool result of the request is treated as invented, and the answer is replaced
by a safe fallback that sends the user to a human.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .core import FUNCTIONS

LANGUAGES = ("kk", "ru", "en")
REQUIRED = {"language": str, "answer": str, "facts": list, "sources": list,
            "tools_used": list, "needs_human": bool}
MAX_ANSWER_CHARS = 2000

_KAZAKH_LETTERS = set("әғқңөұүһі")
# Frequent Kazakh words written without Kazakh-only letters, e.g. "Алматыда тест бар ма?".
# None of them is a common Russian word.
_KAZAKH_WORDS = {"бар", "ма", "ме", "ба", "бе", "па", "пе", "керек", "неше", "туралы", "немесе",
                 "бола", "болады", "болса", "мен", "сен", "маған", "саған", "жазу", "алу", "беру",
                 "тапсыру", "тапсырамын", "кезде", "дейін", "кейін", "барма", "керекпе"}

FALLBACK_TEXT = {
    "en": "Sorry, I could not prepare a reliable answer. Please contact the test centre staff, they will help you.",
    "ru": "Извините, я не смог подготовить надёжный ответ. Пожалуйста, обратитесь к сотрудникам тестового центра, они вам помогут.",
    "kk": "Кешіріңіз, сенімді жауап дайындай алмадым. Тест орталығының қызметкерлеріне хабарласыңыз, олар көмектеседі.",
}


def detect_language(text: str) -> str | None:
    """kk if the text has Kazakh-only letters or frequent Kazakh words, ru if it has other
    Cyrillic, en if only Latin.

    Returns None when there are no letters. Kazakh written in Latin script is detected as en;
    the validator therefore only enforces the language for Cyrillic messages.
    """
    lower = text.lower()
    if any(ch in _KAZAKH_LETTERS for ch in lower):
        return "kk"
    if _KAZAKH_WORDS & set(re.findall(r"[а-яё]+", lower)):
        return "kk"
    if re.search(r"[а-яё]", lower):
        return "ru"
    if re.search(r"[a-z]", lower):
        return "en"
    return None


def fallback_answer(language: str | None, reason: str) -> dict:
    language = language if language in LANGUAGES else "en"
    return {"language": language, "answer": FALLBACK_TEXT[language], "facts": [], "sources": [],
            "tools_used": [], "needs_human": True, "fallback_reason": reason}


def _as_key(value) -> str | None:
    """Comparable form of a scalar: 60000, 60000.0 and "60000" are the same fact."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return str(int(value)) if float(value).is_integer() else str(value)
    if isinstance(value, str):
        v = value.strip()
        if re.fullmatch(r"-?\d+(\.0+)?", v):
            return str(int(float(v)))
        return v.upper() if v else None
    return None


def grounded_values(tool_results: list[dict]) -> set[str]:
    """Every scalar value that appears anywhere in the tool results."""
    found: set[str] = set()

    def walk(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
        else:
            key = _as_key(obj)
            if key is not None:
                found.add(key)

    for r in tool_results:
        walk(r.get("result"))
    return found


@dataclass
class Validation:
    answer: dict
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def check_answer(raw, tool_results: list[dict], user_message: str) -> list[str]:
    """All problems of a model answer (empty list = valid and grounded).

    tool_results: [{"tool": name, "result": dict}, ...] for the tools run in this request.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return ["answer is not valid JSON"]
    if not isinstance(raw, dict):
        return ["answer is not a JSON object"]

    errors = []
    for key, typ in REQUIRED.items():
        if key not in raw:
            errors.append(f"missing field '{key}'")
        elif not isinstance(raw[key], typ):
            errors.append(f"field '{key}' must be {typ.__name__}")
    if errors:
        return errors

    if raw["language"] not in LANGUAGES:
        errors.append(f"language must be one of {LANGUAGES}")
    expected = detect_language(user_message)
    if expected in ("kk", "ru") and raw["language"] != expected:
        errors.append(f"answer language '{raw['language']}' does not match the user's language '{expected}'")
    if not raw["answer"].strip():
        errors.append("answer text is empty")
    elif len(raw["answer"]) > MAX_ANSWER_CHARS:
        errors.append("answer text is too long")

    used = {r["tool"] for r in tool_results}
    for name in raw["tools_used"]:
        if name not in FUNCTIONS:
            errors.append(f"unknown tool in tools_used: {name!r}")
        elif name not in used:
            errors.append(f"tools_used lists '{name}', which was not called")

    known = grounded_values(tool_results)
    for fact in raw["facts"]:
        if not isinstance(fact, dict) or "value" not in fact or not isinstance(fact.get("label", ""), str):
            errors.append(f"fact must be an object with label and value: {fact!r}")
            continue
        key = _as_key(fact["value"])
        if key is None or key not in known:
            errors.append(f"fact not found in tool results: {fact.get('label', '?')} = {fact['value']!r}")
    for source in raw["sources"]:
        if _as_key(source) not in known:
            errors.append(f"source not found in tool results: {source!r}")
    return errors


def validate_answer(raw, tool_results: list[dict], user_message: str) -> Validation:
    """The checked answer, or a fallback answer (needs_human = true) with the list of errors."""
    errors = check_answer(raw, tool_results, user_message)
    if errors:
        return Validation(fallback_answer(detect_language(user_message), "; ".join(errors)), errors)
    answer = json.loads(raw) if isinstance(raw, str) else raw
    return Validation({k: answer[k] for k in REQUIRED})
