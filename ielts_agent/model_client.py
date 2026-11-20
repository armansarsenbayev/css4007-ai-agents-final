"""Model adapter: the only module that talks to the LLM provider.

complete(messages, tools) sends one request and returns a ModelReply with the text, the tool
calls requested by the model and the token usage. Every provider error is turned into a
ModelError with a short message, so the rest of the application never sees SDK exceptions.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import openai

from . import config


class ModelError(RuntimeError):
    """The model could not be called. The message is safe to show to the user."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string from the model; parsed and validated by the agent later


@dataclass
class ModelReply:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    model: str = ""

    @property
    def cost_usd(self) -> float:
        return self.input_tokens * config.PRICE_IN + self.output_tokens * config.PRICE_OUT

    def as_message(self) -> dict[str, Any]:
        """The assistant message to append to the conversation before the next round."""
        msg: dict[str, Any] = {"role": "assistant", "content": self.text}
        if self.tool_calls:
            msg["tool_calls"] = [
                {"id": c.id, "type": "function",
                 "function": {"name": c.name, "arguments": c.arguments}}
                for c in self.tool_calls
            ]
        return msg


_client = None


def _default_client(settings: config.Settings):
    global _client
    if _client is None:
        _client = openai.OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
            max_retries=config.SDK_MAX_RETRIES,
        )
    return _client


def build_request(messages: list[dict], tools: list[dict] | None,
                  settings: config.Settings, response_format: dict | None = None) -> dict[str, Any]:
    """Arguments for chat.completions.create.

    Temperature is not sent: gpt-5.6-luna only accepts the default value (1).
    """
    kwargs: dict[str, Any] = {"model": settings.model, "messages": messages}
    if settings.reasoning_effort:
        kwargs["reasoning_effort"] = settings.reasoning_effort
    if tools:
        kwargs["tools"] = tools
    if response_format:
        kwargs["response_format"] = response_format
    return kwargs


def parse_response(response: Any, model: str, seconds: float) -> ModelReply:
    if not getattr(response, "choices", None):
        raise ModelError("The model returned an empty response.")
    message = response.choices[0].message
    calls = [
        ToolCall(id=c.id, name=c.function.name, arguments=c.function.arguments or "{}")
        for c in (message.tool_calls or [])
    ]
    usage = getattr(response, "usage", None)
    return ModelReply(
        text=message.content,
        tool_calls=calls,
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        seconds=seconds,
        model=model,
    )


def complete(messages: list[dict], tools: list[dict] | None = None, *,
             response_format: dict | None = None,
             client: Any = None, settings: config.Settings | None = None) -> ModelReply:
    """Send the conversation (and optional tool definitions) to the model.

    `response_format={"type": "json_object"}` asks the model for a JSON object.
    `client` and `settings` can be injected; tests use a fake client and never call the API.
    """
    settings = settings or config.get_settings()
    if client is None:
        if not settings.api_key:
            raise ModelError("No API key: set LLM_API_KEY in .env (see .env.example).")
        client = _default_client(settings)

    kwargs = build_request(messages, tools, settings, response_format)
    start = time.perf_counter()
    try:
        response = client.chat.completions.create(**kwargs)
    except openai.AuthenticationError as e:
        raise ModelError("The API key was rejected by the provider.") from e
    except openai.RateLimitError as e:
        raise ModelError("The provider rate limit was reached. Please try again later.") from e
    except openai.APITimeoutError as e:
        raise ModelError("The model did not answer in time.") from e
    except openai.APIConnectionError as e:
        raise ModelError("Could not connect to the model provider.") from e
    except openai.BadRequestError as e:
        raise ModelError(f"The provider rejected the request: {e.message}") from e
    except openai.APIStatusError as e:
        raise ModelError(f"The provider returned an error (HTTP {e.status_code}).") from e
    return parse_response(response, settings.model, time.perf_counter() - start)
