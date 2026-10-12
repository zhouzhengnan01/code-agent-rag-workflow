import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from backend.app import agent, conversation_artifacts, db, intent, main, workspace


@pytest.fixture
def platform(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'db.sqlite'))
    monkeypatch.setattr(workspace, 'BASE_WORKSPACE', tmp_path / 'workspace')
    workspace.BASE_WORKSPACE.mkdir()
    monkeypatch.setenv('CODEZZN_AUTH_REQUIRED', 'false')
    monkeypatch.delenv('CODEZZN_ADMIN_KEY', raising=False)
    db.init_db(); main.THREAD_LOCKS.clear()
    provider = db.resource_save('providers', {'name': 'Test', 'api_key': 'test-only', 'base_url': 'https://example.invalid/v1', 'models': ['text-model'], 'default_model': 'text-model'})
    settings = db.resource_save('agents', {'provider_id': provider['id'], 'model': 'text-model', 'allow_browser': True, 'auto_approve': True, 'sandbox_mode': 'workspace-write'})
    client = TestClient(main.app)
    thread = client.post('/api/threads', json={'agent_id': settings['id']}).json()
    return client, thread, settings


@pytest.mark.parametrize('tool,args', [('screenshot', {'path': 'capture.png'}), ('browser', {'action': 'screenshot', 'path': 'capture.png'})])
def test_browser_output_without_project_is_visible_and_downloadable(platform, monkeypatch, tool, args):
    client, thread, settings = platform
    async def capture(name, session, **values):
        target = workspace.current_workspace() / values['path']
        Image.new('RGB', (10, 10), 'purple').save(target)
        return {'path': values['path'], 'size_bytes': target.stat().st_size, 'url': 'https://example.com'}
    monkeypatch.setattr(agent.browser_manager, 'execute', capture)
    routes = {tool: ('browser_use', None) if tool == 'screenshot' else ('builtin', None)}
    result = asyncio.run(agent.execute_tool(tool, args, settings, routes, thread_id=thread['id'], turn_id='turn_capture'))
    assert result['storage'] == 'conversation'
    output = client.get(f"/api/threads/{thread['id']}").json()['conversation_artifacts'][0]
    assert output['previewable'] is True and output['name'] == 'capture.png'
    assert client.get(output['download_url']).content.startswith(b'\x89PNG')
    assert client.get(output['download_url'].replace(thread['id'], 'thr_wrong')).status_code == 404


def test_vision_observation_is_disabled_for_a_text_model(platform, monkeypatch):
    _, thread, settings = platform
    calls = []
    async def observe(name, session, **values):
        calls.append(values)
        return {'screenshot_available': False, 'content': 'Page DOM'}
    monkeypatch.setattr(agent.browser_manager, 'execute', observe)
    result = asyncio.run(agent.execute_tool('browser_get_state', {'include_screenshot': True}, {**settings, '_supports_browser_vision': False}, {'browser_get_state': ('browser_use', None)}, thread_id=thread['id']))
    assert calls == [{'include_screenshot': False}]
    assert '_vision_image' not in result


def test_declining_save_still_blocks_browser_files(platform, monkeypatch):
    _, thread, settings = platform
    async def forbidden(*args, **kwargs): raise AssertionError('must not run browser')
    monkeypatch.setattr(agent.browser_manager, 'execute', forbidden)
    result = asyncio.run(agent.execute_tool('screenshot', {}, {**settings, '_project_save': False}, {'screenshot': ('browser_use', None)}, thread_id=thread['id']))
    assert result['error']['code'] == 'project_write_declined'


@pytest.mark.parametrize('tool,args', [('screenshot', {'path': 'capture.png'}), ('browser', {'action': 'screenshot', 'path': 'capture.png'})])
def test_confirmed_screenshot_is_written_and_registered_in_selected_project(platform, monkeypatch, tool, args):
    client, thread, settings = platform
    from backend.app import projects
    pid = db.new_id('prj'); directory = projects.project_root(pid); directory.mkdir(parents=True)
    with db.connect() as c:
        c.execute('INSERT INTO projects(id,name,description,created_at,updated_at) VALUES(?,?,?,?,?)', (pid, 'Selected', '', db.now(), db.now()))
    async def capture(name, session, **values):
        target = workspace.current_workspace() / values['path']
        Image.new('RGB', (10, 10), 'purple').save(target)
        return {'path': values['path'], 'size_bytes': target.stat().st_size}
    monkeypatch.setattr(agent.browser_manager, 'execute', capture)
    routes = {tool: ('browser_use', None) if tool == 'screenshot' else ('builtin', None)}
    result = asyncio.run(agent.execute_tool(tool, args, {**settings, '_project_save': True, '_project_id': pid}, routes, thread_id=thread['id'], turn_id='turn_project_capture'))
    assert result['project_id'] == pid and (directory / 'capture.png').exists()
    assert not (workspace.tenant_workspace() / 'capture.png').exists()
    artifact = client.get(f'/api/projects/{pid}/artifacts').json()['data'][0]
    assert artifact['kind'] == 'screenshot' and artifact['path'] == 'capture.png'
    assert client.get(f"/api/threads/{thread['id']}").json()['conversation_artifacts'] == []


def test_artifacts_do_not_cross_tenants_or_symlinks(platform):
    _, thread, _ = platform
    source = workspace.tenant_workspace() / 'capture.png'; source.write_bytes(b'synthetic')
    output = conversation_artifacts.record(thread['id'], 'turn', source, 'screenshot')
    token = db.use_tenant('usr_0123456789abcdef')
    try:
        db.init_db()
        with pytest.raises(FileNotFoundError): conversation_artifacts.get(thread['id'], output['id'])
    finally: db.reset_tenant(token)
    with pytest.raises(ValueError): conversation_artifacts.safe_file('../outside.png')


def test_screenshot_intent_does_not_depend_on_model_guessing():
    assert intent._obvious_intent('打开https://github.com/krahets/hello-algo这个网站并截图')['requires_project'] is True
    assert not (intent._obvious_intent('展示一下这个截图') or {}).get('requires_project')
    assert not (intent._obvious_intent('请展示一下这个截图') or {}).get('requires_project')


def test_failed_checkpoint_is_not_queued_as_interrupted_on_restart(platform):
    _, thread, settings = platform
    state = {'messages': [], 'user_message': '展示截图'}
    agent.save_agent_run(settings, state, thread_id=thread['id'], turn_id='failed_turn')
    agent._save_checkpoint(thread['id'], 'failed_turn', settings['id'], state)
    with db.connect() as c: c.execute("UPDATE turn_checkpoints SET status='failed' WHERE turn_id='failed_turn'")
    assert main.reconcile_failed_checkpoints() == 1
    with db.connect() as c:
        row = c.execute("SELECT status,error FROM agent_runs WHERE turn_id='failed_turn'").fetchone()
    assert row['status'] == 'failed' and '已接收' in row['error']


def test_failed_resume_keeps_approval_consumed_and_persists_failure(platform, monkeypatch):
    client, thread, settings = platform
    count = []
    async def context(*args): return 'QA'
    async def specs(*args): return [], {}
    call = {'id': 'ask_call', 'type': 'function', 'function': {'name': 'ask_user', 'arguments': '{"question":"Continue?"}'}}
    async def complete(*args):
        count.append(1)
        if len(count) == 1: return {'role': 'assistant', 'content': '', 'tool_calls': [call]}, {}
        raise agent.ModelError('Synthetic model request failed after answer')
    async def isolated(settings, history, content, **kwargs): return await agent.run_agent(settings, history, content, **kwargs)
    monkeypatch.setattr(agent, 'build_context', context); monkeypatch.setattr(agent, 'tool_specs', specs)
    monkeypatch.setattr(agent, 'chat_completion', complete); monkeypatch.setattr(main, 'run_agent_isolated', isolated)
    # Supply a real tool route for the actual ask_user approval state machine.
    async def specs(*args): return [], {'ask_user': ('builtin', None)}
    monkeypatch.setattr(agent, 'tool_specs', specs)
    paused = client.post(f"/api/threads/{thread['id']}/turns", json={'content': 'Continue'}).json()
    approval_id = paused['approval_id']
    failed = client.post(f'/api/approvals/{approval_id}', json={'decision': 'approved', 'reason': '重新截图'})
    assert failed.status_code == 502
    state = client.get(f'/api/approvals/{approval_id}').json()
    assert state['status'] == 'approved' and state['thread_status'] == 'error'
    assert 'Synthetic' in state['error']
    messages = client.get(f"/api/threads/{thread['id']}").json()['messages']
    assert messages[-1]['meta']['approval_processed'] is True
    assert client.post(f'/api/approvals/{approval_id}', json={'decision': 'approved', 'reason': 'again'}).status_code == 409
    assert len(count) == 2
