"""Pause a bounded agent loop without discarding its executable state."""
from .db import connect, new_id, now
from . import conversation_control as control


async def pause_budget(agent, state, events, on_event, thread_id=None, turn_id=None,
                       current_task_id=None, provider=None, model=None):
    from .agent import _save_checkpoint, save_agent_run, _emit
    provider = provider or {}
    if not thread_id or not turn_id:
        # Non-conversation background tasks have no human interaction channel.
        # Preserve the run and report a resumable budget state, never fake success.
        save_agent_run(agent, state, "waiting", thread_id, turn_id, current_task_id)
        return {"status": "budget_exhausted", "content": "执行预算已用尽，状态已保存；需要显式继续。", "events": events, "usage": state.get("usage", {}), "sources": state.get("sources", []), "resumable": True}
    state["events"] = events
    state["budget_paused"] = True
    with connect() as db:
        message = db.execute("SELECT id FROM chat_queue_messages WHERE thread_id=? AND turn_id=? ORDER BY created_at DESC LIMIT 1", (thread_id, turn_id)).fetchone()
        # Re-entering after a process crash must reuse the same unanswered pause.
        existing = db.execute("SELECT id FROM chat_interactions WHERE thread_id=? AND turn_id=? AND kind='question' AND status IN ('pending','submitting') AND json_extract(payload,'$.resume_mode')='budget' ORDER BY created_at DESC LIMIT 1", (thread_id, turn_id)).fetchone()
    interaction = control.get_interaction(thread_id, existing["id"]) if existing else control.create_interaction(
        thread_id, turn_id, "question", "本次执行轮次预算已用尽，是否继续同一个任务？已完成的文件和操作不会重做。",
        {"resume_mode": "budget", "options": [{"id": "continue", "label": "继续执行", "description": "保留上下文，增加一段执行预算；工具审批仍然有效"}, {"id": "stop", "label": "停止任务", "description": "保留已完成操作，不继续调用模型或工具"}]},
        message["id"] if message else None, tool_call_id=new_id("budget"))
    save_agent_run(agent, state, "waiting", thread_id, turn_id, current_task_id, state.get("previous_response_id"))
    _save_checkpoint(thread_id, turn_id, agent["id"], state)
    with connect() as db:
        db.execute("UPDATE threads SET status='waiting_for_input',updated_at=? WHERE id=?", (now(), thread_id))
    await _emit(events, on_event, "interaction_required", interaction_id=interaction["id"], kind="question", resume_mode="budget", turn_id=turn_id)
    return {"status": "waiting_for_input", "content": "", "interaction_id": interaction["id"], "events": events,
            "usage": state.get("usage", {}), "sources": state.get("sources", []),
            "runtime": {"provider": provider.get("name", provider.get("type", "unknown")), "model": model, "budget_paused": True}}
