"""Core functions of the assistant, working on the mock data.

In week 13 these functions become LLM tools. The rules they follow already now:
- validate every input and return {"error": ..., "hint": ...} instead of raising, so the model
  can read the problem and correct its next call;
- return short, language-neutral JSON (ISO dates, integer amounts in KZT, fixed English values);
- never guess: an unknown city or session id is reported, with suggestions, not corrected.

`data` and `today` are optional parameters for tests. They are not exposed to the model.
"""
from __future__ import annotations

import difflib
import math
import re
from collections import Counter
from datetime import date, timedelta
from functools import wraps

from .data import Data, get_data

MODULES = ("academic", "general")
DELIVERIES = ("computer", "paper")
ACTIONS = ("transfer", "cancel")
MAX_QUERY_CHARS = 300


class InputError(ValueError):
    def __init__(self, message: str, hint: str | None = None, **extra):
        super().__init__(message)
        self.hint, self.extra = hint, extra


def returns_error_json(func):
    """Turn an InputError into an error object that the model (or the CLI) can read."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except InputError as e:
            result = {"error": str(e)}
            if e.hint:
                result["hint"] = e.hint
            result.update(e.extra)
            return result
    return wrapper


# ---------------------------------------------------------------- input helpers

def _parse_date(value, name: str) -> date:
    if not isinstance(value, str):
        raise InputError(f"{name} must be a string in the format YYYY-MM-DD.")
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise InputError(f"{name} '{value}' is not a valid date.", hint="Use the format YYYY-MM-DD.") from None


def _check_enum(value, name: str, allowed: tuple[str, ...]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value.strip().lower() not in allowed:
        raise InputError(f"{name} must be one of: {', '.join(allowed)}.")
    return value.strip().lower()


def _get_session(session_id, data: Data) -> dict:
    if not isinstance(session_id, str) or not session_id.strip():
        raise InputError("session_id must be a non-empty string, for example 'ALA-1212-CD'.")
    sid = session_id.strip().upper()
    if sid not in data.sessions:
        close = difflib.get_close_matches(sid, list(data.sessions), n=3, cutoff=0.7)
        raise InputError(f"Session '{sid}' does not exist.",
                         hint="Use find_test_sessions to get a valid session_id.",
                         similar_sessions=close)
    return data.sessions[sid]


# ---------------------------------------------------------------- cities

_DASHES = re.compile(r"[‐-―−]")
# Russian and Kazakh case endings, e.g. "Алматыда", "Нур-Султане", "Астанаға", "Шымкентте".
# They are removed only if the rest is an exact known name; nothing is fuzzy-corrected.
_CASE_ENDINGS = ("дағы", "дегі", "тағы", "тегі", "дан", "ден", "тан", "тен", "нан", "нен",
                 "ға", "ге", "қа", "ке", "да", "де", "та", "те", "е", "у", "а")


def _clean_city(name: str) -> str:
    name = _DASHES.sub("-", name.strip().lower()).replace("ё", "е")
    name = re.sub(r"\s*-\s*", "-", name)
    return re.sub(r"\s+", " ", name)


def normalize_city(name, data: Data | None = None) -> tuple[str | None, list[str]]:
    """Map a city name in Kazakh, Russian or English to its canonical name.

    Returns (canonical, []) when the name is known, otherwise (None, suggestions), where the
    suggestions are similar known cities (possibly empty).
    """
    data = data or get_data()
    if not isinstance(name, str) or not name.strip():
        return None, []
    cleaned = _clean_city(name)
    if cleaned in data.city_aliases:
        return data.city_aliases[cleaned], []
    for ending in _CASE_ENDINGS:
        stem = cleaned[: -len(ending)]
        if cleaned.endswith(ending) and len(stem) >= 4 and stem in data.city_aliases:
            return data.city_aliases[stem], []
    close = difflib.get_close_matches(cleaned, list(data.city_aliases), n=5, cutoff=0.6)
    suggestions = list(dict.fromkeys(data.city_aliases[c] for c in close))
    return None, suggestions


# ---------------------------------------------------------------- find_test_sessions

def _status(session: dict, today: date) -> str:
    if session["seats_left"] <= 0:
        return "full"
    if date.fromisoformat(session["registration_deadline"]) < today:
        return "registration_closed"
    return "open"


@returns_error_json
def find_test_sessions(city, module=None, delivery=None, date_from=None, date_to=None, *,
                       data: Data | None = None, today: date | None = None) -> dict:
    """Test sessions in a city, filtered by module, delivery format and date range.

    Every matching session has a status: open, full or registration_closed.
    """
    data, today = data or get_data(), today or date.today()
    canonical, suggestions = normalize_city(city, data)
    if canonical is None:
        raise InputError(f"There are no test sessions in '{city}'.",
                         hint="Tell the user which cities have sessions. Do not guess another city.",
                         available_cities=data.cities, similar_cities=suggestions)
    module = _check_enum(module, "module", MODULES)
    delivery = _check_enum(delivery, "delivery", DELIVERIES)
    start = _parse_date(date_from, "date_from") if date_from is not None else None
    end = _parse_date(date_to, "date_to") if date_to is not None else None
    if start and end and start > end:
        raise InputError("date_from is after date_to.")

    found = []
    for s in sorted(data.sessions.values(), key=lambda s: s["date"]):
        day = date.fromisoformat(s["date"])
        if (s["city"] != canonical or (module and s["module"] != module)
                or (delivery and s["delivery"] != delivery)
                or (start and day < start) or (end and day > end) or day < today):
            continue
        found.append({**s, "status": _status(s, today)})

    result = {"city": canonical,
              "filters": {"module": module, "delivery": delivery, "date_from": date_from, "date_to": date_to},
              "count": len(found), "sessions": found}
    if not found:
        result["note"] = "No sessions match these filters."
    return result


# ---------------------------------------------------------------- calculate_change_fee

def _find_window(rules: list[dict], days: int) -> dict:
    for rule in rules:
        if rule["min_days"] <= days and (rule["max_days"] is None or days <= rule["max_days"]):
            return rule
    raise RuntimeError(f"No fee rule for {days} days")  # impossible: tested in test_data_files


@returns_error_json
def calculate_change_fee(session_id, action, request_date=None, *,
                         data: Data | None = None, today: date | None = None) -> dict:
    """Fee of a transfer or refund of a cancellation made on request_date (default: today)."""
    data, today = data or get_data(), today or date.today()
    session = _get_session(session_id, data)
    action = _check_enum(action, "action", ACTIONS)
    if action is None:
        raise InputError("action is required: transfer or cancel.")
    when = _parse_date(request_date, "request_date") if request_date is not None else today
    test_day = date.fromisoformat(session["date"])
    days = (test_day - when).days
    if days < 0:
        raise InputError(f"Session {session['session_id']} took place on {session['date']}, "
                         f"before the request date {when.isoformat()}.")

    rule = _find_window(data.fees[action], days)
    test_fee = data.fees["test_fee_kzt"]
    result = {"session_id": session["session_id"], "action": action, "test_date": session["date"],
              "request_date": when.isoformat(), "days_before_test": days, "rule_id": rule["rule_id"],
              "test_fee_kzt": test_fee}
    if action == "transfer":
        result |= {"allowed": rule["allowed"], "fee_kzt": rule["fee_kzt"], "policy_section": "POL-06"}
        if not rule["allowed"]:
            result["note"] = "Transfer is not possible this close to the test; medical cases are reviewed by staff (POL-08)."
    else:
        result |= {"allowed": True, "refund_percent": rule["refund_percent"],
                   "refund_kzt": test_fee * rule["refund_percent"] // 100, "policy_section": "POL-07"}
    return result


# ---------------------------------------------------------------- estimate_results_date

@returns_error_json
def estimate_results_date(session_id, *, data: Data | None = None) -> dict:
    """Date when the results of a session are available online."""
    data = data or get_data()
    session = _get_session(session_id, data)
    rule = next(r for r in data.fees["results"] if r["delivery"] == session["delivery"])
    results_day = date.fromisoformat(session["date"]) + timedelta(days=rule["days_after_test"])
    return {"session_id": session["session_id"], "test_date": session["date"],
            "delivery": session["delivery"], "results_date": results_day.isoformat(),
            "rule_id": rule["rule_id"], "policy_section": "POL-09"}


# ---------------------------------------------------------------- search_policy (BM25)

_STOPWORDS = set("a an and are as at be by can do does for from i if in is it my of on or the "
                 "to what when where which who will with".split())


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS]


def _bm25(query: list[str], docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> list[float]:
    n = len(docs)
    avg_len = sum(map(len, docs)) / n
    df = Counter(t for d in docs for t in set(d))
    scores = []
    for d in docs:
        tf = Counter(d)
        score = 0.0
        for t in query:
            if tf[t]:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg_len))
        scores.append(score)
    return scores


@returns_error_json
def search_policy(query, top_k=3, *, data: Data | None = None) -> dict:
    """Handbook sections that best match an English query (BM25 over title and text)."""
    data = data or get_data()
    if not isinstance(query, str) or not query.strip():
        raise InputError("query must be a non-empty string.")
    if len(query) > MAX_QUERY_CHARS:
        raise InputError(f"query is longer than {MAX_QUERY_CHARS} characters.", hint="Use a few key words.")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 5:
        raise InputError("top_k must be an integer from 1 to 5.")
    terms = _tokens(query)
    if not terms:
        raise InputError("query has no searchable English words.",
                         hint="Write the query in English, for example 'ID documents test day'.")

    docs = [_tokens(f"{s['title']} {s['text']}") for s in data.policy]
    ranked = sorted(zip(_bm25(terms, docs), data.policy), key=lambda x: -x[0])
    results = [{"section_id": s["section_id"], "title": s["title"], "text": s["text"], "score": round(sc, 3)}
               for sc, s in ranked[:top_k] if sc > 0]
    result = {"query": query, "results": results}
    if not results:
        result["note"] = "The handbook has no section about this."
    return result


FUNCTIONS = {
    "find_test_sessions": find_test_sessions,
    "calculate_change_fee": calculate_change_fee,
    "search_policy": search_policy,
    "estimate_results_date": estimate_results_date,
}
