"""Direct-chat defaults and Skill discovery never bypass runtime permissions."""
import asyncio
import json

import pytest
import httpx
from fastapi import HTTPException

from backend.app import agent, chat_sessions, coding_workspace, db, main, projects, runtime_config as runtime, workspace


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'runtime.sqlite'))
    monkeypatch.setattr(workspace, 'BASE_WORKSPACE', tmp_path / 'workspace')
    monkeypatch.setenv('CODEZZN_AUTH_REQUIRED', 'false')
    monkeypatch.setattr(__import__('os'), 'chown', lambda *args: None, raising=False)
    root = tmp_path / 'workspace'; root.mkdir()
    monkeypatch.setattr(agent, '_workspace_root', lambda: root)
    token = db.use_tenant(None); work = workspace.use_workspace(root); coding = coding_workspace.use_coding_workspace(None)
    db.init_db()
    provider = db.resource_save('providers', {'name': 'Configured', 'api_key': 'fake-not-a-real-secret', 'default_model': 'mock', 'enabled': True})
    try:
        yield root, provider
    finally:
        coding_workspace.reset_coding_workspace(coding); workspace.reset_workspace(work); db.reset_tenant(token)


def skill(name='example', **extra):
    return db.resource_save('skills', {'name': name, 'description': 'Only a description', 'content': 'UNIQUE_FULL_INSTRUCTIONS', **extra})


def test_direct_chat_needs_no_agent_or_capability_assembly(store):
    _, provider = store
    old = db.resource_save('agents', {'name': 'Legacy', 'sandbox_mode': 'read-only', 'allow_shell': False})
    thread = main.create_thread({})
    default = chat_sessions.current_agent(thread)
    assert default['id'] == runtime.DEFAULT_AGENT_ID
    assert default['provider_id'] == provider['id'] and default['model'] == 'mock'
    assert default['sandbox_mode'] == 'workspace-write' and default['auto_approve'] is False
    assert db.resource_get('agents', old['id']) == old
    tools, _ = asyncio.run(agent.tool_specs(default))
    assert {'read_file', 'write_file', 'run_shell'} <= {tool['function']['name'] for tool in tools}
    assert main.create_thread({})['agent_id'] == thread['agent_id']


def test_settings_layers_and_old_profiles_are_not_silently_broadened(store):
    old = db.resource_save('agents', {'name': 'Read only', 'sandbox_mode': 'read-only', 'allow_shell': False})
    project = projects.create_project('settings test')
    runtime.save_settings({'permission_mode': 'acceptEdits', 'skill_discovery': 'off'})
    runtime.save_settings({'permission_mode': 'plan'}, project['id'])
    thread = main.create_thread({})
    main.update_thread(thread['id'], {'active_project_id': project['id']})
    with db.connect() as connection: row = connection.execute('SELECT * FROM threads WHERE id=?', (thread['id'],)).fetchone()
    scoped = main._agent_for_thread(runtime.ensure_default_agent(), row)
    assert scoped['permission_mode'] == 'plan' and scoped['sandbox_mode'] == 'read-only'
    assert scoped['skill_discovery'] == 'off'
    main.update_thread(thread['id'], {'capability_overrides': {'permission_mode': 'default'}})
    assert main.chat_runtime(thread['id'])['permission_mode'] == 'default'
    legacy = runtime.resolve_settings(old)
    assert legacy['sandbox_mode'] == 'read-only' and not legacy['allow_shell']
    assert 'skill_discovery' not in legacy


@pytest.mark.parametrize('value', [
    {'auto_approve': True}, {'sandbox_mode': 'danger-full-access'}, {'permission_mode': 'bypassPermissions'},
    {'permission_mode': []}, {'skill_discovery': []}, {'provider_id': []}, {'disabled_skill_ids': 'all'},
])
def test_settings_reject_permission_bypass_or_invalid_types(store, value):
    with pytest.raises(HTTPException) as error: runtime.save_settings(value)
    assert error.value.status_code == 400


def test_skills_are_discovered_lazily_and_explicit_command_loads_real_body(store):
    installed = skill()
    default = runtime.ensure_default_agent()
    context = asyncio.run(agent.build_context(default, user_message='你好'))
    assert installed['id'] in context and 'Only a description' in context
    assert 'UNIQUE_FULL_INSTRUCTIONS' not in context
    context = asyncio.run(agent.build_context(default, user_message='/example audit this'))
    assert 'UNIQUE_FULL_INSTRUCTIONS' in context and 'audit this' in context
    assert runtime.resolve_invocation(default, '/skill example audit this')['skill_id'] == installed['id']
    specs, routes = asyncio.run(agent.tool_specs(default))
    assert 'skill_read_file' in routes and 'skill_run_script' in routes
    loaded = asyncio.run(agent.execute_tool('skill_read_file', {'skill_id': installed['id'], 'path': 'SKILL.md'}, default, routes))
    assert loaded['content'] == installed['content']


def test_manual_only_hidden_disabled_and_ambiguous_skills_fail_closed(store):
    manual = skill('manual', content='---\nname: manual\ndisable-model-invocation: true\n---\nMANUAL_ONLY_BODY')
    hidden = skill('hidden', **{'user-invocable': False})
    disabled = skill('disabled', enabled=False)
    default = runtime.ensure_default_agent()
    context = asyncio.run(agent.build_context(default, user_message='hello'))
    assert manual['id'] not in context
    assert not runtime.skill_authorized(default, manual['id'])
    assert 'MANUAL_ONLY_BODY' in asyncio.run(agent.build_context(default, user_message='/manual test'))
    for name in ('hidden', 'disabled', 'missing'):
        with pytest.raises(HTTPException): runtime.resolve_invocation(default, '/' + name)
    assert runtime.skill_authorized(default, hidden['id'])
    skill('manual')
    with pytest.raises(HTTPException): runtime.resolve_invocation(default, '/manual test')
    assert runtime.resolve_invocation(default, '/' + manual['id'])['skill_id'] == manual['id']
    assert not runtime.skill_authorized(default, disabled['id'])


def test_project_skills_and_disabled_ids_do_not_leak_into_other_projects(store):
    first, second = projects.create_project('first'), projects.create_project('second')
    scoped = skill('scoped', project_id=first['id'])
    common = skill('common')
    default = runtime.ensure_default_agent()
    assert scoped['id'] not in {s['id'] for s in runtime.available_skills(default)}
    assert runtime.skill_authorized({**default, '_project_id': first['id']}, scoped['id'])
    assert not runtime.skill_authorized({**default, '_project_id': second['id']}, scoped['id'])
    assert not runtime.skill_authorized({**default, 'disabled_skill_ids': [common['id']]}, common['id'])
    assert not runtime.skill_authorized({'skill_ids': []}, common['id'])


def test_tool_permission_modes_preserve_approval_and_hard_denies(store, monkeypatch):
    root, _ = store
    default = runtime.ensure_default_agent()
    routes = {'write_file': ('builtin', None), 'read_file': ('builtin', None), 'run_shell': ('builtin', None)}
    args = {'path': 'sort.py', 'content': 'print(1)'}
    assert asyncio.run(agent.execute_tool('write_file', args, default, routes))['error']['code'] == 'approval_required'
    assert not (root / 'sort.py').exists()
    edits = {**default, 'permission_mode': 'acceptEdits'}
    assert asyncio.run(agent.execute_tool('write_file', args, edits, routes))['written'] == 'sort.py'
    assert (root / 'sort.py').read_text() == 'print(1)'
    assert asyncio.run(agent.execute_tool('run_shell', {'command': 'python sort.py'}, edits, routes))['error']['code'] == 'approval_required'
    assert asyncio.run(agent.execute_tool('run_shell', {'command': 'python sort.py'}, {**default, 'auto_approve': True}, routes))['error']['code'] == 'approval_required'
    deny = {**edits, 'tool_policy': {'tools': {'write_file': 'deny'}}}
    with pytest.raises(PermissionError): asyncio.run(agent.execute_tool('write_file', args, deny, routes, approved=True))
    ask = {**edits, 'auto_approve': True, 'tool_policy': {'tools': {'write_file': 'ask'}}}
    assert asyncio.run(agent.execute_tool('write_file', args, ask, routes))['error']['code'] == 'approval_required'
    plan = {**edits, 'permission_mode': 'plan'}
    with pytest.raises(PermissionError): asyncio.run(agent.execute_tool('write_file', args, plan, routes, approved=True))
    assert asyncio.run(agent.execute_tool('read_file', {'path': 'sort.py'}, plan, routes))['content'] == 'print(1)'
    old = {**edits, 'sandbox_mode': 'read-only'}
    assert asyncio.run(agent.execute_tool('write_file', args, old, routes))['error']['code'] == 'approval_required'
    with pytest.raises(PermissionError): asyncio.run(agent.execute_tool('run_shell', {'command': 'true'}, {**edits, 'allow_shell': False}, routes, approved=True))


def test_skill_script_still_requires_approval_and_shell_capability(store):
    installed = skill()
    default = runtime.ensure_default_agent()
    routes = {'skill_run_script': ('builtin', None)}
    args = {'skill_id': installed['id'], 'path': 'scripts/test.py'}
    assert asyncio.run(agent.execute_tool('skill_run_script', args, {**default, 'permission_mode': 'acceptEdits'}, routes))['error']['code'] == 'approval_required'
    with pytest.raises(PermissionError): asyncio.run(agent.execute_tool('skill_run_script', args, {**default, 'allow_shell': False}, routes, approved=True))


def test_tenant_defaults_and_skills_remain_private(store):
    runtime.save_settings({'permission_mode': 'acceptEdits'})
    private = skill('private')
    user = db.new_id('usr'); db.ensure_tenant(user); token = db.use_tenant(user)
    try:
        assert runtime.settings() == {}
        assert not runtime.skill_authorized(runtime.ensure_default_agent(), private['id'])
    finally: db.reset_tenant(token)


def test_running_task_rejects_permission_switch(store):
    thread = main.create_thread({})
    with db.connect() as connection: connection.execute("UPDATE threads SET status='running' WHERE id=?", (thread['id'],))
    with pytest.raises(HTTPException) as error:
        main.update_thread(thread['id'], {'capability_overrides': {'permission_mode': 'acceptEdits'}})
    assert error.value.status_code == 409


def test_project_tool_reapplies_target_permissions_and_skill_scope(store):
    first, second = projects.create_project('first'), projects.create_project('second')
    scoped = skill('second-skill', project_id=second['id'])
    runtime.save_settings({'permission_mode': 'acceptEdits'}, first['id'])
    runtime.save_settings({'permission_mode': 'plan'}, second['id'])
    current = runtime.resolve_settings({**runtime.ensure_default_agent(), '_project_id': first['id'], '_project_save': False})
    assert current['permission_mode'] == 'acceptEdits'
    result = asyncio.run(agent.execute_tool('project_select', {'project_id': second['id']}, current, {'project_select': ('builtin', None)}, approved=True))
    assert result['id'] == second['id']
    assert current['permission_mode'] == 'plan' and current['sandbox_mode'] == 'read-only'
    assert scoped['id'] in {s['id'] for s in result['available_skills']}


def test_manual_skill_and_file_approval_resume_as_the_same_durable_turn(store, monkeypatch):
    root, _ = store
    manual = skill('manual', **{'disable-model-invocation': True})
    thread = main.create_thread({})
    default = {**runtime.ensure_default_agent(), '_project_save': True}
    calls = []
    async def model(provider, model_name, messages, *args, **kwargs):
        calls.append(messages)
        if len(calls) == 1:
            return {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'manual_write_call', 'type': 'function', 'function': {'name': 'write_file', 'arguments': json.dumps({'path': 'manual.py', 'content': 'print(42)'})}}]}, {}
        return {'role': 'assistant', 'content': '已写入并等待后续验证。'}, {}
    monkeypatch.setattr(agent, 'chat_completion', model)
    result = asyncio.run(agent.run_agent(default, [], '/manual create a file', thread_id=thread['id'], turn_id='manual_turn'))
    assert result['status'] == 'waiting_for_approval'
    assert not (root / 'manual.py').exists()
    with db.connect() as connection:
        saved = json.loads(connection.execute('SELECT state FROM turn_checkpoints WHERE turn_id=?', ('manual_turn',)).fetchone()['state'])
    assert saved['skill_invocation']['skill_id'] == manual['id']
    result = asyncio.run(agent.run_agent(default, [], '', thread_id=thread['id'], turn_id='manual_turn', resume_state=saved,
                                        approval_decision={'tool_call_id': 'manual_write_call', 'decision': 'approved'}))
    assert result['status'] == 'completed'
    assert (root / 'manual.py').read_text() == 'print(42)'
    assert 'UNIQUE_FULL_INSTRUCTIONS' in calls[0][0]['content']


def test_http_default_chat_and_manual_command_contract(store):
    installed = skill('http-skill')
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
            response = await client.post('/api/threads', json={})
            assert response.status_code == 200
            thread_id = response.json()['id']
            response = await client.get('/api/chat/runtime', params={'thread_id': thread_id})
            assert response.status_code == 200
            assert 'fake-not-a-real-secret' not in response.text and 'api_key' not in response.json()
            response = await client.post(f'/api/threads/{thread_id}/queue', json={'content': '/http-skill inspect', 'submission_id': '12345678-1234-4123-8123-123456789abc'})
            assert response.status_code == 200
            with db.connect() as connection:
                row = connection.execute('SELECT payload FROM chat_queue_messages WHERE thread_id=?', (thread_id,)).fetchone()
            assert json.loads(row['payload'])['skill_invocation'] == {'skill_id': installed['id'], 'arguments': 'inspect'}
            invalid = await client.post(f'/api/threads/{thread_id}/queue', json={'content': '/missing task'})
            assert invalid.status_code == 400
            assert (await client.patch('/api/chat/runtime/settings', json={'auto_approve': True})).status_code == 400
            assert (await client.patch('/api/projects/not-valid/runtime-settings', json={'permission_mode': 'plan'})).status_code == 404
    asyncio.run(run())


def test_runtime_configuration_endpoints_require_authentication(store, monkeypatch):
    monkeypatch.setenv('CODEZZN_AUTH_REQUIRED', 'true')
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
            assert (await client.get('/api/chat/runtime')).status_code == 401
            assert (await client.patch('/api/chat/runtime/settings', json={'permission_mode': 'acceptEdits'})).status_code == 401
    asyncio.run(run())
