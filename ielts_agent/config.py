"""Settings read from environment variables (and a local .env file).

The API key is only read here and passed to the OpenAI client. It is never printed or logged.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

DEFAULT_MODEL = "gpt-5.6-luna"
# Prices of gpt-5.6-luna in USD per token (used only to report the cost of a request).
PRICE_IN = 0.20 / 1e6
PRICE_OUT = 1.20 / 1e6

REQUEST_TIMEOUT_SECONDS = 60
SDK_MAX_RETRIES = 3  # the OpenAI SDK retries timeouts, 429 and 5xx with exponential back-off


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    model: str
    base_url: str | None
    reasoning_effort: str | None


def get_settings() -> Settings:
    """Read the settings at call time, so tests can change the environment."""
    load_dotenv(os.getenv("ENV_FILE", ROOT / ".env"))
    return Settings(
        api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or None,
        model=os.getenv("LLM_MODEL") or DEFAULT_MODEL,
        base_url=os.getenv("LLM_BASE_URL") or None,
        reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "none") or None,
    )
