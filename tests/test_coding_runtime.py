import asyncio
import json
import os
import uuid

import pytest

from backend.app import agent, chat_sessions, coding_runtime, conversation_control as control, db, main, workspace


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'runtime.sqlite'))
    monkeypatch.setattr(workspace, 'BASE_WORKSPACE', tmp_path / 'workspace')
    monkeypatch.setattr(os, 'chown', lambda *args: None, raising=False)
    monkeypatch.setattr(os, 'fchown', lambda *args: None, raising=False)
    monkeypatch.delenv('CODEZZN_LEGACY_OWNER_GITHUB_ID', raising=False)
    monkeypatch.setenv('CODEZZN_AUTH_REQUIRED', 'false')
    db.init_db()
    main.THREAD_LOCKS.clear()
    provider = db.resource_save('providers', {'name': 'Mock', 'api_key': 'test', 'base_url': 'https://example.invalid', 'models': ['text-test'], 'default_model': 'text-test'})
    settings = db.resource_save('agents', {'name': 'Coding', 'provider_id': provider['id'], 'model': 'text-test', 'auto_approve': False, 'memory_enabled': False})
    thread = main.create_thread({'agent_id': settings['id']})
    runtime = control.ConversationRuntime()
    monkeypatch.setattr(control, 'conversation_runtime', runtime)
    async def no_destination(*args, **kwargs): return {'requires_project': False, 'kind': 'answer'}
    monkeypatch.setattr(main, 'classify_intent', no_destination)
    item, _ = control.enqueue(thread['id'], settings['id'], 'Original task', {}, str(uuid.uuid4()))
    with db.connect() as conn:
        conn.execute("UPDATE chat_queue_messages SET status='consumed',run_status='running',turn_id='turn_saved' WHERE id=?", (item['id'],))
        conn.execute("UPDATE threads SET status='running' WHERE id=?", (thread['id'],))
    item = control.get_message(thread['id'], item['id'])
    state = {'messages': [{'role': 'user', 'content': 'Original task'}], 'pending_tool_calls': [], 'round': 2, 'user_message': 'Original task', 'provider_id': provider['id'], 'model': 'text-test'}
    return thread, settings, provider, runtime, item, state


def test_budget_pause_persists_question_and_continues_same_turn_once(store, monkeypatch):
    thread, settings, provider, runtime, item, state = store
    calls = []
    async def fake_run(scoped, history, content, **kwargs):
        calls.append((scoped, content, kwargs))
        return {'status': 'completed', 'content': 'Finished', 'events': [], 'usage': {}, 'sources': []}
    monkeypatch.setattr(main, 'run_agent_isolated', fake_run)
    async def scenario():
        result = await coding_runtime.pause_budget(settings, state, [], None, thread['id'], item['turn_id'], provider=provider, model='text-test')
        assert result['status'] == 'waiting_for_input'
        chat_sessions.finalize_result(item, result)
        assert control.get_message(thread['id'], item['id'])['run_status'] == 'waiting_for_input'
        same = await coding_runtime.pause_budget(settings, state, [], None, thread['id'], item['turn_id'])
        assert same['interaction_id'] == result['interaction_id']
        interaction = control.get_interaction(thread['id'], result['interaction_id'])
        assert [o['id'] for o in interaction['payload']['options']] == ['continue', 'stop']
        response = {'decision': 'approved', 'option_id': 'continue', 'answer': '继续执行'}
        resumed, created = control.claim_answer(thread['id'], interaction['id'], response, str(uuid.uuid4()))
        assert created
        await chat_sessions.resume_interaction(resumed)
        await chat_sessions.resume_interaction(resumed)  # Same accepted answer is not executed twice.
        assert len(calls) == 1
        assert calls[0][2]['turn_id'] == item['turn_id']
        assert calls[0][2]['resume_state']['round'] == 0
        assert calls[0][2]['resume_state']['budget_resumptions'] == 1
        assert control.get_message(thread['id'], item['id'])['run_status'] == 'completed'
    asyncio.run(scenario())


def test_budget_stop_preserves_files_and_never_calls_model(store, monkeypatch):
    thread, settings, provider, runtime, item, state = store
    async def forbidden(*args, **kwargs): raise AssertionError('Model must not run')
    monkeypatch.setattr(main, 'run_agent_isolated', forbidden)
    async def scenario():
        result = await coding_runtime.pause_budget(settings, state, [], None, thread['id'], item['turn_id'])
        chat_sessions.finalize_result(item, result)
        response = {'decision': 'approved', 'option_id': 'stop', 'answer': '停止任务'}
        answer, _ = control.claim_answer(thread['id'], result['interaction_id'], response, str(uuid.uuid4()))
        await chat_sessions.resume_interaction(answer)
        assert control.get_message(thread['id'], item['id'])['run_status'] == 'cancelled'
        with db.connect() as conn:
            assert conn.execute('SELECT status FROM turn_checkpoints WHERE turn_id=?', (item['turn_id'],)).fetchone()['status'] == 'cancelled'
    asyncio.run(scenario())


async def wait_status(thread_id, message_id, wanted):
    for _ in range(100):
        message = control.get_message(thread_id, message_id)
        if message['run_status'] == wanted: return message
        await asyncio.sleep(.01)
    raise AssertionError(message)


def test_restart_requeues_checkpointed_turn_without_duplicate_user_message(store, monkeypatch):
    thread, settings, provider, runtime, item, state = store
    agent.save_agent_run(settings, state, 'running', thread['id'], item['turn_id'])
    with db.connect() as conn:
        conn.execute("INSERT INTO messages(id,thread_id,turn_id,role,content,meta,created_at) VALUES(?,?,?,'user',?,'{}',?)", (db.new_id('msg'), thread['id'], item['turn_id'], item['content'], db.now()))
    seen = []
    async def fake_run(scoped, history, content, **kwargs):
        seen.append((scoped, kwargs))
        return {'status': 'completed', 'content': 'Recovered', 'events': [], 'usage': {}, 'sources': []}
    monkeypatch.setattr(main, 'run_agent_isolated', fake_run)
    async def scenario():
        await runtime.start(chat_sessions.execute_message, chat_sessions.resume_interaction)
        try:
            await wait_status(thread['id'], item['id'], 'completed')
            assert len(seen) == 1 and seen[0][0]['_recovering'] is True
            assert seen[0][1]['turn_id'] == item['turn_id']
            with db.connect() as conn:
                assert conn.execute("SELECT count(*) FROM messages WHERE turn_id=? AND role='user'", (item['turn_id'],)).fetchone()[0] == 1
                assert conn.execute('SELECT count(*) FROM chat_queue_messages WHERE thread_id=?', (thread['id'],)).fetchone()[0] == 1
        finally: await runtime.close()
    asyncio.run(scenario())


def test_restart_with_uncertain_external_side_effect_requires_manual_check(store, monkeypatch):
    thread, settings, provider, runtime, item, state = store
    agent.save_agent_run(settings, state, 'running', thread['id'], item['turn_id'])
    with db.connect() as conn:
        conn.execute("INSERT INTO tool_executions VALUES(?,?,?,'{}','running',NULL,NULL,?,?)", ('call_uncertain', item['turn_id'], 'git_push', db.now(), db.now()))
    async def forbidden(*args, **kwargs): raise AssertionError('Never replay uncertain side effect')
    async def scenario():
        await runtime.start(forbidden, forbidden)
        try:
            message = await wait_status(thread['id'], item['id'], 'failed')
            assert '不自动重放' in message['error']
        finally: await runtime.close()
    asyncio.run(scenario())


def test_service_shutdown_is_not_user_cancellation_and_restart_resumes(store, monkeypatch):
    thread, settings, provider, runtime, item, state = store
    started = asyncio.Event()
    async def long_run(scoped, history, content, **kwargs):
        agent.save_agent_run(scoped, state, 'running', thread['id'], kwargs['turn_id'])
        started.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(main, 'run_agent_isolated', long_run)
    # Start with a genuine pending queue so runtime creates its execution task.
    with db.connect() as conn:
        conn.execute("UPDATE chat_queue_messages SET status='pending',run_status='pending' WHERE id=?", (item['id'],))
        conn.execute("UPDATE threads SET status='idle' WHERE id=?", (thread['id'],))
    async def scenario():
        await runtime.start(chat_sessions.execute_message, chat_sessions.resume_interaction)
        await asyncio.wait_for(started.wait(), 2)
        await runtime.close()
        assert control.get_message(thread['id'], item['id'])['run_status'] == 'running'
        with db.connect() as conn:
            assert conn.execute("SELECT count(*) FROM messages WHERE turn_id=? AND role='assistant'", (item['turn_id'],)).fetchone()[0] == 0
            assert conn.execute("SELECT count(*) FROM agent_runs WHERE turn_id=? AND status='cancelled'", (item['turn_id'],)).fetchone()[0] == 0
    asyncio.run(scenario())


def test_completed_tool_result_is_reused_without_repeating_effect(store, monkeypatch):
    thread, settings, provider, runtime, item, state = store
    effects = []
    async def effect(*args, **kwargs):
        effects.append(args)
        return {'pushed': True}
    monkeypatch.setattr(agent, 'execute_tool', effect)
    async def scenario():
        first = await agent.execute_tool_once('durable_call', 'git_push', {}, settings, {}, thread_id=thread['id'], turn_id=item['turn_id'])
        second = await agent.execute_tool_once('durable_call', 'git_push', {}, settings, {}, thread_id=thread['id'], turn_id=item['turn_id'])
        assert first == second == {'pushed': True}
        assert len(effects) == 1
    asyncio.run(scenario())
