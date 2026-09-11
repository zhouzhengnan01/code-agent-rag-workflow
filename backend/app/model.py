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
    message, usage = await chat_completion(
        provider,
        selected_model,
        [{"role": "user", "content": "只回复 OK"}],
        temperature=0,
    )
    return {
        "ok": True,
        "provider_type": provider.get("type"),
        "base_url": provider.get("base_url"),
        "model": normalize_qwen_model(selected_model) if is_bailian(provider) else selected_model,
        "response": message.get("content", ""),
        "usage": usage,
    }
