"""Loading of the mock data (schedule, fee rules, policy handbook, city aliases).

The files are read once and checked. A broken data file raises DataError at start-up instead of
producing wrong answers later.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from . import config


class DataError(RuntimeError):
    """A data file is missing or does not have the expected structure."""


@dataclass(frozen=True)
class Data:
    sessions: dict[str, dict]          # session_id -> session
    fees: dict
    policy: list[dict]                 # handbook sections in file order
    city_aliases: dict[str, str]       # lower-case alias -> canonical city name

    @property
    def cities(self) -> list[str]:
        return sorted(set(self.city_aliases.values()))


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise DataError(f"Missing data file: {path.name}") from e
    except json.JSONDecodeError as e:
        raise DataError(f"Invalid JSON in {path.name}: {e}") from e


def _check_sessions(raw: list[dict]) -> dict[str, dict]:
    sessions = {}
    for s in raw:
        sid = s.get("session_id")
        if not sid or sid in sessions:
            raise DataError(f"Missing or duplicate session_id: {sid!r}")
        for key in ("date", "registration_deadline"):
            try:
                date.fromisoformat(s[key])
            except (KeyError, ValueError) as e:
                raise DataError(f"{sid}: bad {key}") from e
        if s.get("module") not in {"academic", "general"} or s.get("delivery") not in {"computer", "paper"}:
            raise DataError(f"{sid}: bad module or delivery")
        sessions[sid] = s
    return sessions


def load_data(data_dir: Path | None = None) -> Data:
    data_dir = Path(data_dir or config.DATA_DIR)
    sessions = _check_sessions(_read_json(data_dir / "sessions.json").get("sessions", []))
    fees = _read_json(data_dir / "fees.json")
    for key in ("test_fee_kzt", "transfer", "cancel", "results"):
        if key not in fees:
            raise DataError(f"fees.json: missing '{key}'")

    policy = []
    try:
        lines = (data_dir / "policy.jsonl").read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as e:
        raise DataError("Missing data file: policy.jsonl") from e
    for n, line in enumerate(lines, 1):
        if line.strip():
            try:
                section = json.loads(line)
            except json.JSONDecodeError as e:
                raise DataError(f"policy.jsonl line {n}: invalid JSON") from e
            if not {"section_id", "title", "text"} <= set(section):
                raise DataError(f"policy.jsonl line {n}: missing fields")
            policy.append(section)

    aliases = {}
    for city, names in _read_json(data_dir / "cities.json").get("aliases", {}).items():
        for name in [city, *names]:
            aliases[name.lower()] = city
    return Data(sessions=sessions, fees=fees, policy=policy, city_aliases=aliases)


@lru_cache(maxsize=1)
def get_data() -> Data:
    """The default data set, loaded once per process."""
    return load_data()
