"""Consistency checks of the mock data. The tools (weeks 12-13) will rely on these properties."""
import json
from datetime import date, timedelta

import pytest

from ielts_agent.config import DATA_DIR

SESSIONS = json.loads((DATA_DIR / "sessions.json").read_text(encoding="utf-8"))["sessions"]
FEES = json.loads((DATA_DIR / "fees.json").read_text(encoding="utf-8"))
CITIES = json.loads((DATA_DIR / "cities.json").read_text(encoding="utf-8"))["aliases"]
POLICY = [json.loads(line) for line in (DATA_DIR / "policy.jsonl").read_text(encoding="utf-8").splitlines()
          if line.strip()]

SESSION_KEYS = {"session_id", "city", "date", "module", "delivery", "seats_left", "registration_deadline"}
DELIVERY_CODE = {"computer": "CD", "paper": "PB"}
CITY_CODE = {"Almaty": "ALA", "Astana": "AST", "Shymkent": "SHY"}  # airport-style codes
# Mock registration rule: computer-delivered closes 5 days before the test, paper-based 14 days before.
DEADLINE_DAYS = {"computer": 5, "paper": 14}


def test_sessions_have_valid_fields_and_unique_ids():
    ids = [s["session_id"] for s in SESSIONS]
    assert len(ids) == len(set(ids))
    for s in SESSIONS:
        assert set(s) == SESSION_KEYS, s["session_id"]
        assert s["module"] in {"academic", "general"}
        assert s["delivery"] in DELIVERY_CODE
        assert isinstance(s["seats_left"], int) and s["seats_left"] >= 0
        test_day = date.fromisoformat(s["date"])
        # the id encodes city, month-day and delivery, e.g. ALA-1212-CD
        assert s["session_id"] == f"{CITY_CODE[s['city']]}-{test_day:%m%d}-{DELIVERY_CODE[s['delivery']]}"
        deadline = date.fromisoformat(s["registration_deadline"])
        assert test_day - deadline == timedelta(days=DEADLINE_DAYS[s["delivery"]])


def test_every_session_city_has_aliases_in_three_languages():
    assert {s["city"] for s in SESSIONS} == set(CITIES)
    all_aliases = [a for aliases in CITIES.values() for a in aliases]
    assert len(all_aliases) == len(set(all_aliases)), "an alias must point to exactly one city"
    for city, aliases in CITIES.items():
        assert city.lower() in aliases
        assert any(any("а" <= ch <= "я" or ch in "әғқңөұүһі" for ch in a) for a in aliases), city
        assert all(a == a.lower() for a in aliases)


@pytest.mark.parametrize("action", ["transfer", "cancel"])
def test_fee_windows_cover_every_day_exactly_once(action):
    rules = FEES[action]
    for days in range(0, 400):
        matching = [r for r in rules
                    if r["min_days"] <= days and (r["max_days"] is None or days <= r["max_days"])]
        assert len(matching) == 1, f"{action}: {days} days matches {[r['rule_id'] for r in matching]}"


def test_results_rules_exist_for_both_delivery_formats():
    assert {r["delivery"] for r in FEES["results"]} == set(DELIVERY_CODE)


def test_policy_sections_are_unique_and_not_empty():
    ids = [p["section_id"] for p in POLICY]
    assert len(ids) == len(set(ids)) >= 10
    for p in POLICY:
        assert p["title"].strip() and len(p["text"].split()) >= 20, p["section_id"]
