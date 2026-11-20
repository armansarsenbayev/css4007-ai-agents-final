"""Unit tests of the core functions (no API). `today` is fixed so the results do not change."""
from datetime import date

import pytest

from ielts_agent.core import (calculate_change_fee, estimate_results_date, find_test_sessions,
                              normalize_city, search_policy)
from ielts_agent.data import DataError, get_data, load_data

TODAY = date(2026, 11, 20)


# ---------------------------------------------------------------- data loading

def test_load_data_reads_all_files():
    data = get_data()
    assert len(data.sessions) == 12 and len(data.policy) == 12
    assert data.cities == ["Almaty", "Astana", "Shymkent"]


def test_load_data_reports_broken_files(tmp_path):
    with pytest.raises(DataError, match="Missing data file"):
        load_data(tmp_path)
    (tmp_path / "sessions.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(DataError, match="Invalid JSON"):
        load_data(tmp_path)


# ---------------------------------------------------------------- normalize_city

@pytest.mark.parametrize("name, city", [
    ("Almaty", "Almaty"), ("  ALMATY ", "Almaty"), ("Алматы", "Almaty"), ("Алма-Ата", "Almaty"),
    ("алма – ата", "Almaty"), ("Алматыда", "Almaty"),
    ("Astana", "Astana"), ("Нур-Султан", "Astana"), ("Нур-Султане", "Astana"), ("Нұр-Сұлтан", "Astana"),
    ("Ақмола", "Astana"), ("Астанаға", "Astana"),
    ("Шымкент", "Shymkent"), ("Chimkent", "Shymkent"), ("Шымкентте", "Shymkent"),
])
def test_normalize_city_accepts_all_known_spellings(name, city):
    assert normalize_city(name) == (city, [])


def test_normalize_city_does_not_guess():
    assert normalize_city("Almatu") == (None, ["Almaty"])   # typo: suggestion only
    assert normalize_city("Taraz") == (None, [])            # no sessions there
    assert normalize_city("") == (None, [])
    assert normalize_city(None) == (None, [])


# ---------------------------------------------------------------- find_test_sessions

def test_find_sessions_filters_and_sorts():
    r = find_test_sessions("Алматы", module="academic", delivery="computer",
                           date_from="2026-12-01", date_to="2026-12-31", today=TODAY)
    assert r["city"] == "Almaty" and r["count"] == 1
    s = r["sessions"][0]
    assert (s["session_id"], s["seats_left"], s["status"]) == ("ALA-1212-CD", 4, "open")
    all_almaty = find_test_sessions("Almaty", today=TODAY)["sessions"]
    assert [s["date"] for s in all_almaty] == sorted(s["date"] for s in all_almaty)


def test_find_sessions_marks_full_and_closed_sessions():
    r = find_test_sessions("Astana", date_to="2026-12-31", today=TODAY)
    assert {s["session_id"]: s["status"] for s in r["sessions"]} == {"AST-1205-CD": "full", "AST-1219-PB": "open"}
    # on 2026-11-25 the registration for ALA-1205-PB (deadline 2026-11-21) is closed
    r = find_test_sessions("Almaty", delivery="paper", date_to="2026-12-31", today=date(2026, 11, 25))
    assert r["sessions"][0]["status"] == "registration_closed"


def test_find_sessions_hides_past_sessions_and_reports_empty_result():
    assert find_test_sessions("Shymkent", today=date(2027, 1, 1))["count"] == 2
    r = find_test_sessions("Shymkent", module="general", date_to="2026-12-31", today=TODAY)
    assert r["count"] == 0 and "note" in r


def test_find_sessions_unknown_city_returns_error_with_cities():
    r = find_test_sessions("Taraz", today=TODAY)
    assert "error" in r and r["available_cities"] == ["Almaty", "Astana", "Shymkent"]


@pytest.mark.parametrize("kwargs, message", [
    ({"module": "ielts"}, "module must be one of"),
    ({"delivery": "online"}, "delivery must be one of"),
    ({"date_from": "12/01/2026"}, "not a valid date"),
    ({"date_from": "2026-12-31", "date_to": "2026-12-01"}, "after date_to"),
    ({"date_to": 20261231}, "must be a string"),
])
def test_find_sessions_rejects_invalid_input(kwargs, message):
    r = find_test_sessions("Almaty", today=TODAY, **kwargs)
    assert message in r["error"]


# ---------------------------------------------------------------- calculate_change_fee

@pytest.mark.parametrize("request_date, rule, allowed, fee", [
    ("2026-11-07", "TR-1", True, 30000),   # 35 days before 2026-12-12: cheapest window
    ("2026-11-08", "TR-2", True, 60000),   # 34 days
    ("2026-11-28", "TR-2", True, 60000),   # 14 days: last day of transfer
    ("2026-11-29", "TR-3", False, None),   # 13 days: no transfer
    ("2026-12-12", "TR-3", False, None),   # test day
])
def test_transfer_fee_at_window_boundaries(request_date, rule, allowed, fee):
    r = calculate_change_fee("ALA-1212-CD", "transfer", request_date)
    assert (r["rule_id"], r["allowed"], r["fee_kzt"]) == (rule, allowed, fee)


@pytest.mark.parametrize("request_date, percent, refund", [
    ("2026-11-07", 75, 96000), ("2026-11-28", 25, 32000), ("2026-11-29", 0, 0),
])
def test_cancel_refund(request_date, percent, refund):
    r = calculate_change_fee("ALA-1212-CD", "cancel", request_date)
    assert (r["refund_percent"], r["refund_kzt"]) == (percent, refund)


def test_change_fee_defaults_to_today_and_normalizes_id():
    r = calculate_change_fee(" ala-1212-cd ", "Transfer", today=TODAY)
    assert (r["session_id"], r["request_date"], r["days_before_test"]) == ("ALA-1212-CD", "2026-11-20", 22)


@pytest.mark.parametrize("args, message", [
    (("ALA-1299-CD", "transfer", "2026-11-20"), "does not exist"),
    (("ALA-1212-CD", "refund", "2026-11-20"), "action must be one of"),
    (("ALA-1212-CD", None, "2026-11-20"), "action is required"),
    (("ALA-1212-CD", "cancel", "2026-12-13"), "took place"),
    (("", "cancel", "2026-11-20"), "non-empty"),
])
def test_change_fee_rejects_invalid_input(args, message):
    assert message in calculate_change_fee(*args)["error"]


def test_unknown_session_suggests_similar_ids():
    r = calculate_change_fee("ALA-1213-CD", "transfer", "2026-11-20")
    assert "ALA-1212-CD" in r["similar_sessions"]


# ---------------------------------------------------------------- estimate_results_date

def test_results_date_for_computer_and_paper():
    assert estimate_results_date("ALA-1212-CD")["results_date"] == "2026-12-15"   # +3 days
    r = estimate_results_date("AST-1219-PB")                                       # +13 days, new year
    assert (r["results_date"], r["rule_id"]) == ("2027-01-01", "RE-PB")
    assert "error" in estimate_results_date("XXX")


# ---------------------------------------------------------------- search_policy

@pytest.mark.parametrize("query, section", [
    ("ID documents passport photo copy", "POL-01"),
    ("prohibited items phone watch", "POL-02"),
    ("late arrival listening", "POL-03"),
    ("re-mark enquiry on results fee", "POL-04"),
    ("retake one skill", "POL-05"),
    ("medical certificate illness refund", "POL-08"),
    ("hearing impairment extra time", "POL-11"),
])
def test_search_policy_finds_the_right_section(query, section):
    assert search_policy(query)["results"][0]["section_id"] == section


def test_search_policy_validates_input():
    assert "non-empty" in search_policy("  ")["error"]
    assert "top_k" in search_policy("passport", top_k=9)["error"]
    assert "top_k" in search_policy("passport", top_k=True)["error"]
    assert "English" in search_policy("құжаттар қандай")["error"]     # non-English query is rejected
    assert len(search_policy("passport", top_k=1)["results"]) == 1
    assert search_policy("xylophone")["results"] == []
