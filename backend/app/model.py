import copy
import json
import re

import httpx


class ModelError(RuntimeError):
    pass


BAILIAN_PRESETS = [
    {
        "id": "bailian-beijing",
        "name": "阿里云百炼 · 华北2（北京）",
        "type": "bailian",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen3.7-plus", "qwen3.7-max", "qwen3.7-flash", "qwen-plus", "qwen-max", "qwen-turbo"],
        "default_model": "qwen3.7-plus",
    },
    {
        "id": "bailian-singapore",
        "name": "阿里云百炼 · 新加坡",
        "type": "bailian",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen3.7-plus", "qwen3.7-max", "qwen3.7-flash", "qwen-plus", "qwen-max", "qwen-turbo"],
        "default_model": "qwen3.7-plus",
    },
    {
        "id": "bailian-us",
        "name": "阿里云百炼 · 美国（弗吉尼亚）",
        "type": "bailian",
        "base_url": "https://dashscope-us.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen3.7-plus", "qwen3.7-max", "qwen3.7-flash"],
        "default_model": "qwen3.7-plus",
    },
]


def is_bailian(provider):
    provider_type = str(provider.get("type", "")).lower()
    base_url = str(provider.get("base_url", "")).lower()
    return provider_type in {"bailian", "qwen", "dashscope", "aliyun"} or "aliyuncs.com" in base_url or "dashscope" in base_url


def normalize_qwen_model(model):
    """Convert common Qwen model ID typos to Bailian's documented form."""
    value = str(model or "").strip().lower()
    match = re.fullmatch(r"qwen[-_](\d+(?:\.\d+)?)[-_]?(plus|max|flash|turbo)", value)
    if match:
        version, tier = match.groups()
        return f"qwen{version}-{tier}"
    return value


def normalize_provider(provider):
    normalized = copy.deepcopy(provider)
    if not is_bailian(normalized):
        return normalized
    normalized["type"] = "bailian"
    base_url = str(normalized.get("base_url") or BAILIAN_PRESETS[0]["base_url"]).strip().rstrip("/")
    if base_url.endswith("/api/v1/services"):
        base_url = base_url[:-len("/api/v1/services")] + "/compatible-mode/v1"
    elif base_url.endswith("/api/v1"):
        base_url = base_url[:-len("/api/v1")] + "/compatible-mode/v1"
    elif "/compatible-mode/v1" not in base_url and not base_url.endswith("/v1"):
        base_url += "/compatible-mode/v1"
    normalized["base_url"] = base_url
    normalized["models"] = [normalize_qwen_model(model) for model in normalized.get("models", []) if str(model).strip()]
    default_model = normalized.get("default_model") or (normalized["models"][0] if normalized["models"] else "qwen3.7-plus")
    normalized["default_model"] = normalize_qwen_model(default_model)
    if normalized["default_model"] not in normalized["models"]:
        normalized["models"].insert(0, normalized["default_model"])
    return normalized


def public_provider(provider):
    value = copy.deepcopy(provider)
    api_key = str(value.get("api_key") or "")
    value["api_key_configured"] = bool(api_key)
    # Never send credential material back to a browser, including partial masks.
    value["api_key"] = ""
    return value


async def chat_completion(provider, model, messages, tools=None, temperature=0.2):
    provider = normalize_provider(provider)
    model = normalize_qwen_model(model) if is_bailian(provider) else model
    api_key = provider.get("api_key") or ""
    if not api_key:
        raise ModelError("模型提供方尚未配置 API Key")
    headers = {"Content-Type": "application/json", **provider.get("headers", {})}
    headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    url = provider.get("base_url", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=provider.get("timeout", 120)) as client:
            response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            detail = response.text[:1200]
            if response.status_code == 401:
                detail = "API Key 无效、已过期，或与 Base URL 的地域/计费方案不匹配"
            elif response.status_code == 404:
                detail = "接口路径或模型 ID 不正确，请使用百炼 OpenAI 兼容地址 /compatible-mode/v1"
            raise ModelError(f"模型服务返回 {response.status_code}: {detail}")
        data = response.json()
        if not data.get("choices"):
            raise ModelError(f"模型服务响应缺少 choices: {str(data)[:800]}")
        return data["choices"][0]["message"], data.get("usage", {})
    except httpx.HTTPError as exc:
        raise ModelError(f"无法连接模型服务 {url}: {exc}") from exc


async def stream_chat_completion(provider, model, messages, tools=None, temperature=0.2):
    """Yield safe OpenAI-compatible streaming events: visible content, tool calls, usage, and errors."""
    provider = normalize_provider(provider)
    model = normalize_qwen_model(model) if is_bailian(provider) else model
    api_key = provider.get("api_key") or ""
    if not api_key:
        raise ModelError("模型提供方尚未配置 API Key")
    headers = {"Content-Type": "application/json", **provider.get("headers", {})}
    headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model, "messages": messages, "temperature": temperature, "stream": True, "stream_options": {"include_usage": True}}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    url = provider.get("base_url", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    tool_calls = {}
    usage = {}
    try:
        async with httpx.AsyncClient(timeout=provider.get("timeout", 120)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code >= 400:
                    detail = (await response.aread()).decode(errors="replace")[:1200]
                    raise ModelError(f"模型服务返回 {response.status_code}: {detail}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("usage"):
                        usage.update(chunk["usage"])
                        yield {"type": "usage", "usage": usage}
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            yield {"type": "assistant_delta", "content": delta["content"]}
                        for call in delta.get("tool_calls") or []:
                            index = call.get("index", 0)
                            item = tool_calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            if call.get("id"): item["id"] += call["id"]
                            if call.get("type"): item["type"] = call["type"]
                            function = call.get("function") or {}
                            item["function"]["name"] += function.get("name", "")
                            item["function"]["arguments"] += function.get("arguments", "")
                        if choice.get("finish_reason"):
                            yield {"type": "finish", "finish_reason": choice["finish_reason"], "tool_calls": list(tool_calls.values()), "usage": usage}
    except httpx.HTTPError as exc:
        raise ModelError(f"无法连接模型服务 {url}: {exc}") from exc


async def test_provider(provider, model=None):
    provider = normalize_provider(provider)
    selected_model = model or provider.get("default_model")
    if uses_responses(provider):
        message, usage, response_id, _ = await response_completion(
            provider, selected_model, [{"role": "user", "content": "只回复 OK"}], instructions="Return only OK."
        )
    else:
        message, usage = await chat_completion(
            provider,
            selected_model,
            [{"role": "user", "content": "只回复 OK"}],
            temperature=0,
        )
        response_id = None
    return {
        "ok": True,
        "provider_type": provider.get("type"),
        "base_url": provider.get("base_url"),
        "model": normalize_qwen_model(selected_model) if is_bailian(provider) else selected_model,
        "response": message.get("content", ""),
        "usage": usage,
        "response_id": response_id,
    }


def uses_responses(provider):
    return str(provider.get("api_mode") or "chat_completions") == "responses"


def response_tools(tools, async_tools=False):
    result = []
    for item in tools or []:
        function = item.get("function") or item
        value = {"type":"function", "name":function["name"], "description":function.get("description", ""), "parameters":function.get("parameters", {"type":"object","properties":{}}), "strict":False}
        if async_tools: value["async"] = True
        result.append(value)
    return result


def _response_result(data):
    text, calls = [], []
    for item in data.get("output") or []:
        if item.get("type") == "message":
            for content in item.get("content") or []:
                if content.get("type") in ("output_text", "text") and content.get("text"): text.append(content["text"])
        elif item.get("type") == "function_call":
            calls.append({"id":item.get("call_id") or item.get("id"),"type":"function","function":{"name":item.get("name", ""),"arguments":item.get("arguments", "{}")}})
    return {"role":"assistant","content":"".join(text),"tool_calls":calls}, data.get("usage") or {}, data.get("id"), data.get("output") or []


def _responses_payload(provider, model, input_items, tools, instructions, previous_response_id=None, reasoning_effort=None, stream=False):
    payload = {
        "model": model, "input": input_items, "instructions": instructions, "store": True,
        "stream": stream, "parallel_tool_calls": True, "tools": response_tools(tools, provider.get("async_tools") is True),
        "reasoning": {"effort": reasoning_effort or provider.get("reasoning_effort", "medium")},
    }
    if previous_response_id: payload["previous_response_id"] = previous_response_id
    if provider.get("context_compaction", True):
        payload["context_management"] = [{"type":"compaction", "compact_threshold":int(provider.get("compact_threshold", 120000))}]
    if provider.get("prompt_cache_key"): payload["prompt_cache_key"] = str(provider["prompt_cache_key"])[:64]
    if not tools: payload.pop("tools")
    return payload


async def response_completion(provider, model, input_items, tools=None, instructions="", previous_response_id=None, reasoning_effort=None):
    provider = normalize_provider(provider); api_key = provider.get("api_key") or ""
    if not api_key: raise ModelError("模型提供方尚未配置 API Key")
    url = provider.get("base_url", "https://api.openai.com/v1").rstrip("/") + "/responses"
    headers = {"Content-Type":"application/json", **provider.get("headers", {}), "Authorization":f"Bearer {api_key}"}
    payload = _responses_payload(provider, model, input_items, tools, instructions, previous_response_id, reasoning_effort)
    try:
        async with httpx.AsyncClient(timeout=provider.get("timeout", 180)) as client: response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400: raise ModelError(f"Responses API 返回 {response.status_code}: {response.text[:1200]}")
        return _response_result(response.json())
    except httpx.HTTPError as exc: raise ModelError(f"无法连接 Responses API {url}: {exc}") from exc


async def stream_response_completion(provider, model, input_items, tools=None, instructions="", previous_response_id=None, reasoning_effort=None):
    provider = normalize_provider(provider); api_key = provider.get("api_key") or ""
    if not api_key: raise ModelError("模型提供方尚未配置 API Key")
    url = provider.get("base_url", "https://api.openai.com/v1").rstrip("/") + "/responses"
    headers = {"Content-Type":"application/json", **provider.get("headers", {}), "Authorization":f"Bearer {api_key}"}
    payload = _responses_payload(provider, model, input_items, tools, instructions, previous_response_id, reasoning_effort, True)
    try:
        async with httpx.AsyncClient(timeout=provider.get("timeout", 180)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code >= 400: raise ModelError(f"Responses API 返回 {response.status_code}: {(await response.aread()).decode(errors='replace')[:1200]}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"): continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]": continue
                    try: event = json.loads(raw)
                    except json.JSONDecodeError: continue
                    kind = event.get("type")
                    if kind == "response.output_text.delta": yield {"type":"assistant_delta","content":event.get("delta", "")}
                    elif kind == "response.completed":
                        message, usage, response_id, output = _response_result(event.get("response") or {})
                        yield {"type":"finish","response":message,"usage":usage,"response_id":response_id,"output":output}
                    elif kind in ("response.failed", "response.incomplete"):
                        raise ModelError(str((event.get("response") or {}).get("error") or kind))
    except httpx.HTTPError as exc: raise ModelError(f"无法连接 Responses API {url}: {exc}") from exc


async def compact_response(provider, model, previous_response_id, instructions=""):
    provider = normalize_provider(provider); api_key = provider.get("api_key") or ""
    if not api_key: raise ModelError("模型提供方尚未配置 API Key")
    url = provider.get("base_url", "https://api.openai.com/v1").rstrip("/") + "/responses/compact"
    headers = {"Content-Type":"application/json", **provider.get("headers", {}), "Authorization":f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=provider.get("timeout", 180)) as client:
        response = await client.post(url, headers=headers, json={"model":model,"previous_response_id":previous_response_id,"instructions":instructions})
    if response.status_code >= 400: raise ModelError(f"上下文压缩失败 {response.status_code}: {response.text[:1000]}")
    return response.json()
