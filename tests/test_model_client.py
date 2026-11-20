"""Tests of the model adapter. A fake client is injected, so no API key or network is used."""
from types import SimpleNamespace

import openai

try:  # openai 3.x uses httpx2, older versions use httpx
    import httpx2 as httpx
except ImportError:
    import httpx
import pytest

from ielts_agent import config
from ielts_agent.__main__ import main
from ielts_agent.model_client import ModelError, build_request, complete

SETTINGS = config.Settings(api_key="test-key", model="gpt-5.6-luna", base_url=None,
                           reasoning_effort="none")


def fake_response(content=None, tool_calls=None, prompt_tokens=100, completion_tokens=20):
    calls = [
        SimpleNamespace(id=f"call_{i}", type="function",
                        function=SimpleNamespace(name=name, arguments=args))
        for i, (name, args) in enumerate(tool_calls or [])
    ]
    message = SimpleNamespace(content=content, tool_calls=calls or None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


class FakeClient:
    """Mimics client.chat.completions.create; records the request it receives."""

    def __init__(self, response=None, error=None):
        self.response, self.error, self.requests = response, error, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def test_text_reply_is_parsed_with_usage_and_cost():
    client = FakeClient(fake_response("Сәлеметсіз бе!", prompt_tokens=1000, completion_tokens=500))
    reply = complete([{"role": "user", "content": "Сәлем"}], client=client, settings=SETTINGS)
    assert reply.text == "Сәлеметсіз бе!"
    assert reply.tool_calls == []
    assert (reply.input_tokens, reply.output_tokens) == (1000, 500)
    assert reply.cost_usd == pytest.approx(1000 * 0.20e-6 + 500 * 1.20e-6)
    assert reply.as_message() == {"role": "assistant", "content": "Сәлеметсіз бе!"}


def test_tool_call_reply_is_parsed_and_can_be_sent_back():
    args = '{"city": "Almaty", "module": "academic"}'
    client = FakeClient(fake_response(None, [("find_test_sessions", args)]))
    reply = complete([{"role": "user", "content": "tests in Almaty?"}], tools=[{"type": "function"}],
                     client=client, settings=SETTINGS)
    assert len(reply.tool_calls) == 1
    call = reply.tool_calls[0]
    assert (call.name, call.arguments) == ("find_test_sessions", args)
    msg = reply.as_message()
    assert msg["tool_calls"][0]["function"] == {"name": "find_test_sessions", "arguments": args}


def test_request_sends_reasoning_effort_and_tools_but_never_temperature():
    client = FakeClient(fake_response("ok"))
    tools = [{"type": "function", "function": {"name": "x", "parameters": {"type": "object"}}}]
    complete([{"role": "user", "content": "hi"}], tools=tools, client=client, settings=SETTINGS)
    sent = client.requests[0]
    assert sent["model"] == "gpt-5.6-luna"
    assert sent["reasoning_effort"] == "none"
    assert sent["tools"] == tools
    assert "temperature" not in sent
    # without tools and without reasoning effort, neither key is sent
    no_effort = config.Settings("k", "other-model", None, None)
    assert set(build_request([], None, no_effort)) == {"model", "messages"}


def test_missing_api_key_gives_clear_error_without_network(monkeypatch):
    no_key = config.Settings(api_key=None, model="m", base_url=None, reasoning_effort=None)
    with pytest.raises(ModelError, match="LLM_API_KEY"):
        complete([{"role": "user", "content": "hi"}], settings=no_key)


@pytest.mark.parametrize("error, expected", [
    (openai.APITimeoutError(request=httpx.Request("POST", "https://x")), "did not answer in time"),
    (openai.APIConnectionError(request=httpx.Request("POST", "https://x")), "Could not connect"),
    (openai.RateLimitError("slow down", response=httpx.Response(429, request=httpx.Request("POST", "https://x")), body=None), "rate limit"),
    (openai.InternalServerError("boom", response=httpx.Response(500, request=httpx.Request("POST", "https://x")), body=None), "HTTP 500"),
])
def test_provider_errors_become_model_errors(error, expected):
    client = FakeClient(error=error)
    with pytest.raises(ModelError, match=expected):
        complete([{"role": "user", "content": "hi"}], client=client, settings=SETTINGS)


def test_empty_response_is_rejected():
    client = FakeClient(SimpleNamespace(choices=[], usage=None))
    with pytest.raises(ModelError, match="empty"):
        complete([{"role": "user", "content": "hi"}], client=client, settings=SETTINGS)


def test_cli_rejects_empty_question_and_reports_errors(monkeypatch, capsys):
    assert main(["   "]) == 2
    monkeypatch.setattr("ielts_agent.__main__.complete",
                        lambda *a, **k: (_ for _ in ()).throw(ModelError("No API key")))
    assert main(["hello"]) == 1
    assert "No API key" in capsys.readouterr().err


def test_ask_requests_json_and_validates_the_answer():
    import json as _json
    from ielts_agent.__main__ import ask
    good = {"language": "kk", "answer": "Кестені әзірге көре алмаймын.", "facts": [], "sources": [],
            "tools_used": [], "needs_human": True}
    client = FakeClient(fake_response(_json.dumps(good)))
    reply, check = ask("Алматыда тест бар ма?", client=client, settings=SETTINGS)
    assert client.requests[0]["response_format"] == {"type": "json_object"}
    assert check.ok and check.answer == good
    # an invented date without tool results is replaced by the fallback answer
    bad = {**good, "facts": [{"label": "test date", "value": "2026-12-12"}]}
    _, check = ask("Алматыда тест бар ма?", client=FakeClient(fake_response(_json.dumps(bad))), settings=SETTINGS)
    assert not check.ok and check.answer["needs_human"] and check.answer["language"] == "kk"


def test_cli_call_runs_core_functions_and_rejects_bad_input(capsys):
    assert main(["--call", "estimate_results_date", '{"session_id": "ALA-1212-CD"}']) == 0
    assert '"results_date": "2026-12-15"' in capsys.readouterr().out
    assert main(["--call", "delete_everything", "{}"]) == 1
    assert main(["--call", "search_policy", "{bad json"]) == 1
    assert main(["--call", "search_policy", '{"query": "id", "today": "2026-01-01"}']) == 1
    assert main(["--call", "search_policy", '{"text": "id"}']) == 1
    assert "Wrong arguments" in capsys.readouterr().out
