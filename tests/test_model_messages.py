"""Provider request contracts: no paid model calls or production data."""
import asyncio
import copy
import json

import httpx
import pytest

from backend.app import model


@pytest.mark.parametrize("provider_type", ["bailian", "openai-compatible"])
@pytest.mark.parametrize("streaming", [False, True])
def test_requests_omit_empty_calls_and_preserve_actual_exchanges(monkeypatch, provider_type, streaming):
    call = {"id": "read-1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"sort.py"}'}}
    messages = [
        {"role": "system", "content": "Test instructions"},
        {"role": "user", "content": [{"type": "text", "text": "Task"}]},
        {"role": "assistant", "content": "An ordinary answer"},
        {"role": "assistant", "content": "Waiting for plan approval", "tool_calls": []},
        {"role": "user", "content": "Completion blocked by engineering state"},
        {"role": "assistant", "content": "Legacy checkpoint", "tool_calls": None},
        {"role": "user", "content": "Continue"},
        {"role": "assistant", "content": None, "tool_calls": [call]},
        {"role": "tool", "tool_call_id": "read-1", "content": "file bytes"},
    ]
    original = copy.deepcopy(messages)
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        # Reproduce the real provider's rejection, not just a helper assertion.
        if any("tool_calls" in m and not m["tool_calls"] for m in payload["messages"]):
            return httpx.Response(400, json={"error": {"message": "Empty tool_calls is not supported in message."}})
        assert payload["messages"] == model.normalize_chat_messages(original)
        assert payload["messages"][-2]["tool_calls"] == [call]
        assert payload["messages"][-1]["tool_call_id"] == "read-1"
        if streaming:
            chunks = [
                {"choices": [{"delta": {"content": "OK"}, "finish_reason": None}]},
                {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            ]
            body = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n"
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "OK"}}]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(model.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    provider = {"type": provider_type, "api_key": "test-only", "base_url": "https://example.invalid/v1"}

    async def run():
        if streaming:
            events = [event async for event in model.stream_chat_completion(provider, "test-model", messages)]
            assert "".join(event.get("content", "") for event in events) == "OK"
        else:
            response, _ = await model.chat_completion(provider, "test-model", messages)
            assert response["content"] == "OK"

    asyncio.run(run())
    assert len(requests) == 1
    assert messages == original


def test_normalization_does_not_share_nested_state():
    messages = [{"role": "assistant", "content": None, "tool_calls": [
        {"id": "call-1", "function": {"name": "read_file", "arguments": "{}"}}
    ]}]
    normalized = model.normalize_chat_messages(messages)
    normalized[0]["tool_calls"].pop()
    assert len(messages[0]["tool_calls"]) == 1
