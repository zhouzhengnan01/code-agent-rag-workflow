import asyncio
import json

import pytest

from backend.app import intent


@pytest.mark.parametrize("content", ["截图是什么？", "帮我看看这张截图为什么模糊", "请帮我展示一下这个截图", "如何保存截图", "分析附件内容，不要保存文件"])
def test_existing_images_and_explanations_are_not_explicit_artifact_requests(content):
    assert not (intent._obvious_intent(content) or {}).get("requires_project")


@pytest.mark.parametrize("content,kind", [
    ("打开https://github.com/krahets/hello-algo这个网站并截图", "browser_artifact"),
    ("查看这段代码，并把分析结果保存为报告", "file"),
    ("分析这张截图，然后生成一份报告", "file"),
    ("创建一个工作流", "workflow"),
])
def test_explicit_outcomes_in_all_clauses_are_kept(content, kind):
    result = intent._obvious_intent(content)
    assert result["requires_project"] is True and result["kind"] == kind


def test_model_sees_history_and_attachment_summary(monkeypatch):
    monkeypatch.setattr(intent, "model_candidates", lambda *_: [({"api_mode": "chat_completions"}, "model")])
    async def completion(provider, model, messages, **kwargs):
        data = json.loads(messages[-1]["content"])
        assert data["recent_messages"][0]["content"] == "报告已分析"
        assert data["attachments"][0]["name"] == "existing.png"
        assert "api_key" not in data["attachments"][0]
        return {"content": '{"requires_project":false,"kind":"answer"}'}, {}
    monkeypatch.setattr(intent, "chat_completion", completion)
    result = asyncio.run(intent.classify_intent({}, "看看它有什么问题", [{"role": "assistant", "content": "报告已分析"}], attachments=[{"name": "existing.png", "kind": "image", "api_key": "should-not-pass"}]))
    assert result["requires_project"] is False


@pytest.mark.parametrize("mode", ["missing", "invalid", "error"])
def test_classifier_unavailable_defers_to_main_agent_without_authorizing_writes(monkeypatch, mode):
    monkeypatch.setattr(intent, "model_candidates", lambda *_: [] if mode == "missing" else [({}, "model")])
    async def completion(*args, **kwargs):
        if mode == "error":
            raise RuntimeError("provider unavailable")
        return {"content": '{"requires_project":"yes"}'}, {}
    monkeypatch.setattr(intent, "chat_completion", completion)
    result = asyncio.run(intent.classify_intent({}, "把它处理好"))
    assert result["deferred"] is True and result["requires_project"] is False


def test_unknown_project_destination_survives_deferred_classification(monkeypatch):
    monkeypatch.setattr(intent, "model_candidates", lambda *_: [])
    result = asyncio.run(intent.classify_intent({}, "切换到不存在的项目，并继续处理上面的问题", projects=[]))
    assert result["unresolved_target"] is True and result["target_project_id"] is None

