"""Integration contracts on temporary tenant data; no paid models or host tool fallback."""
import asyncio
import json
from pathlib import Path

import pytest

from backend.app import agent, coding_context, coding_workspace as cw, db, engineering, main, projects, terminal_tools, workspace


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'store.sqlite'))
    monkeypatch.setattr(workspace, 'BASE_WORKSPACE', tmp_path / 'workspace')
    monkeypatch.setenv('CODEZZN_AUTH_REQUIRED', 'false')
    root = workspace.tenant_workspace()
    root.mkdir(parents=True)
    tenant_token = db.use_tenant(None)
    workspace_token = workspace.use_workspace(root)
    coding_token = cw.use_coding_workspace(None)
    db.init_db()
    provider = db.resource_save('providers', {'name':'Mock', 'type':'openai-compatible', 'enabled':True, 'default_model':'mock'})
    settings = db.resource_save('agents', {'name':'Coding', 'role_template':'coding', 'provider_id':provider['id'], 'model':'mock', 'sandbox_mode':'workspace-write', 'auto_approve':True, 'allow_shell':True, 'max_tool_rounds':0})
    thread = main.create_thread({'agent_id':settings['id']})
    project = projects.create_project('Integration')
    async def no_git(*args, **kwargs): return {'exit_code':128, 'output':'no repository'}
    monkeypatch.setattr(cw, 'run_command', no_git)
    async def context(*args, **kwargs): return 'Test instructions'
    monkeypatch.setattr(agent, 'build_context', context)
    monkeypatch.setattr(agent, 'automatic_retrieval', lambda *a: False)
    yield root, settings, thread, project
    cw.reset_coding_workspace(coding_token)
    workspace.reset_workspace(workspace_token)
    db.reset_tenant(tenant_token)


def test_coding_tools_registered_and_mcp_schemas_load_on_demand(store):
    _, settings, _, _ = store
    tools, routes = asyncio.run(agent.tool_specs(settings))
    names = {item['function']['name'] for item in tools}
    assert {'engineering_review','quality_run','plan_manage','task_rewind','terminal_start','code_index','github_ci_logs','github_ci_rerun','tool_search'} <= names
    specs = [{'type':'function','function':{'name':'read_file','description':'read'}}, {'type':'function','function':{'name':'mcp__test__lookup','description':'latest documents'}}]
    visible, route = coding_context.defer_tools(specs, {}, settings)
    assert 'mcp__test__lookup' not in [s['function']['name'] for s in visible]
    result = coding_context.discover('documents', route['tool_search'][1])
    assert result['tools'][0]['function']['name'] == 'mcp__test__lookup'
    assert 'mcp__test__lookup' in [s['function']['name'] for s in visible]


def test_file_read_search_and_git_share_isolated_execution_root(store, monkeypatch):
    root, settings, thread, project = store
    scoped = {**settings, '_project_id':project['id'], '_project_save':True}
    commands = []
    async def command(text, mode, cwd, **kwargs):
        commands.append((text, mode, cwd))
        return {'exit_code':0,'output':'ok'}
    monkeypatch.setattr(agent, 'run_command', command)
    async def run(scoped, history, prompt, **kwargs):
        target_root = agent._workspace_root()
        assert target_root != projects.project_root(project['id'])
        assert target_root == cw.execution_project_root(project['id'])
        result = await agent.execute_tool('write_file', {'path':'sort.py','content':'print(42)\n','expected_hash':None}, scoped, {'write_file':('builtin',)}, thread_id=thread['id'], turn_id='turn_files')
        read = await agent.execute_tool('read_file', {'path':'sort.py','offset':1,'limit':1}, scoped, {'read_file':('builtin',)})
        assert read['content'] == 'print(42)\n' and len(read['sha256']) == 64
        with pytest.raises(ValueError, match='file_version_conflict'):
            await agent.execute_tool('write_file', {'path':'sort.py','content':'bad','expected_hash':'stale'}, scoped, {'write_file':('builtin',)})
        await agent.execute_tool('search_code', {'query':'print'}, scoped, {'search_code':('builtin',)})
        await agent.execute_tool('git_status', {}, scoped, {'git_status':('builtin',)})
        assert {c[2] for c in commands} == {target_root.relative_to(root).as_posix()}
        return result
    monkeypatch.setattr(main, 'run_agent', run)
    result = asyncio.run(main.run_agent_isolated(scoped, [], 'write', thread_id=thread['id'], turn_id='turn_files'))
    assert result['written'] == 'sort.py'
    assert (projects.project_root(project['id'])/'sort.py').read_bytes() == b'print(42)\n'
    assert projects.list_artifacts(project['id'])[0]['path'] == 'sort.py'
    assert cw.current_coding_workspace() is None


def test_engineering_state_and_checkpoints_survive_new_turn_without_cross_project_access(store):
    _, settings, thread, project = store
    async def run():
        first = await cw.prepare_coding_workspace(turn_id='turn_one', thread_id=thread['id'], project_id=project['id'])
        r1 = cw.workspace_path(first)
        await engineering.execute('plan_manage', {'action':'create','steps':[{'content':'Implement'}]}, settings, r1, thread['id'])
        checkpoint = await engineering.execute('task_checkpoint', {'paths':['sort.py']}, settings, r1, thread['id'])
        second = await cw.prepare_coding_workspace(turn_id='turn_two', thread_id=thread['id'], project_id=project['id'])
        r2 = cw.workspace_path(second)
        assert r1 != r2
        assert engineering.state(r2, thread['id'])['plan']['status'] == 'proposed'
        (r2/'sort.py').write_text('new', encoding='utf-8')
        diff = await engineering.execute('task_diff', checkpoint, settings, r2, thread['id'])
        assert diff['changes'][0]['path'] == 'sort.py'
        other = projects.create_project('Other')
        third = await cw.prepare_coding_workspace(turn_id='turn_three', thread_id=thread['id'], project_id=other['id'])
        with pytest.raises(ValueError, match='快照不存在'):
            await engineering.execute('task_diff', checkpoint, settings, cw.workspace_path(third), thread['id'])
    asyncio.run(run())


@pytest.mark.parametrize('responses', [False, True])
def test_budget_resume_calls_model_again_and_reuses_outputs(store, monkeypatch, responses):
    _, settings, thread, _ = store
    calls = []
    def response():
        calls.append(1)
        if len(calls) == 1:
            return {'role':'assistant','content':'','tool_calls':[{'id':'call_read','type':'function','function':{'name':'todo_read','arguments':'{}'}}]}
        return {'role':'assistant','content':'Finished','tool_calls':[]}
    async def completion(*a, **k): return response(), {}
    async def completion_responses(*a, **k): return response(), {}, 'resp_'+str(len(calls)), {}
    monkeypatch.setattr(agent, 'chat_completion', completion)
    monkeypatch.setattr(agent, 'response_completion', completion_responses)
    monkeypatch.setattr(agent, 'uses_responses', lambda p: responses)
    async def run():
        paused = await agent.run_agent(settings, [], 'Task', thread_id=thread['id'], turn_id='turn_budget')
        assert paused['status'] == 'waiting_for_input'
        with db.connect() as connection:
            saved = json.loads(connection.execute('SELECT state FROM turn_checkpoints WHERE turn_id=?', ('turn_budget',)).fetchone()[0])
        saved['round'] = 0
        result = await agent.run_agent(settings, [], '', thread_id=thread['id'], turn_id='turn_budget', resume_state=saved)
        assert result['status'] == 'completed' and result['content'] == 'Finished'
        assert len(calls) == 2
    asyncio.run(run())


@pytest.mark.parametrize('streaming', [False, True])
def test_plan_gate_retry_omits_empty_tool_calls_and_still_requires_approval(store, monkeypatch, streaming):
    root, settings, thread, _ = store
    settings = {**settings, 'auto_approve': False, 'max_tool_rounds': 5}
    plan = asyncio.run(engineering.execute('plan_manage', {
        'action': 'create', 'steps': [{'content': 'Write sort.py and tests/test_sort.py'}],
        'required_checks': ['test'],
    }, settings, root, thread['id']))
    requests = []

    def reply(messages):
        requests.append(json.loads(json.dumps(messages)))
        assert not any('tool_calls' in m and not m['tool_calls'] for m in messages)
        if len(requests) == 1:
            return {'role': 'assistant', 'content': 'Plan ready, waiting for approval', 'tool_calls': []}
        assert 'plan_not_approved' in messages[-1]['content']
        assert 'required_check_not_passed:test' in messages[-1]['content']
        return {'role': 'assistant', 'content': '', 'tool_calls': [{
            'id': 'approve-plan', 'type': 'function', 'function': {'name': 'plan_manage',
            'arguments': json.dumps({'action': 'approve', 'expected_revision': plan['revision']})},
        }]}

    async def completion(_provider, _model, messages, *args):
        return reply(messages), {}

    async def stream(_provider, _model, messages, *args):
        response = reply(messages)
        if response['content']:
            yield {'type': 'assistant_delta', 'content': response['content']}
        yield {'type': 'finish', 'finish_reason': 'tool_calls' if response['tool_calls'] else 'stop',
               'tool_calls': response['tool_calls'], 'usage': {}}

    monkeypatch.setattr(agent, 'chat_completion', completion)
    monkeypatch.setattr(agent, 'stream_chat_completion', stream)
    result = asyncio.run(agent.run_agent(settings, [], 'Create the coding acceptance project',
        thread_id=thread['id'], turn_id='turn_plan_empty_calls', streaming=streaming))
    assert result['status'] == 'waiting_for_approval'
    assert len(requests) == 2
    with db.connect() as connection:
        approval = connection.execute('SELECT * FROM approvals WHERE id=?', (result['approval_id'],)).fetchone()
        state = json.loads(connection.execute('SELECT state FROM turn_checkpoints WHERE turn_id=?', ('turn_plan_empty_calls',)).fetchone()[0])
    assert approval['tool_name'] == 'plan_manage' and approval['status'] == 'pending'
    assert json.loads(approval['arguments']) == {'action': 'approve', 'expected_revision': plan['revision']}
    assert engineering.state(root, thread['id'])['plan']['status'] == 'proposed'
    assert not (root / 'sort.py').exists()
    assert all('tool_calls' not in m or m['tool_calls'] for m in state['messages'])


def test_parent_and_child_run_identity_never_aliases(store):
    _, settings, thread, _ = store
    parent = agent.save_agent_run(settings, {'messages':[]}, thread_id=thread['id'], turn_id='shared')
    child = agent.save_agent_run(settings, {'messages':[]}, thread_id=thread['id'], turn_id='shared', task_id='task_child')
    assert parent != child
    assert agent.load_agent_run(turn_id='shared')['id'] == parent
    assert agent.load_agent_run(task_id='task_child', turn_id='shared')['id'] == child
    assert agent.load_agent_run(task_id='task_other', turn_id='shared') is None


def test_pre_tool_block_does_not_leave_an_ambiguous_side_effect(store):
    root, settings, thread, _ = store
    asyncio.run(engineering.execute('plan_manage', {'action':'create','steps':[{'content':'Plan'}]}, settings, root, thread['id']))
    result = asyncio.run(agent.execute_tool_once('blocked_write','write_file',{'path':'no.txt','content':'x'},settings,{'write_file':('builtin',)},thread_id=thread['id'],turn_id='turn_blocked'))
    assert result['error']['code'] == 'plan_not_approved'
    with db.connect() as connection:
        assert connection.execute('SELECT 1 FROM tool_executions WHERE call_id=?', ('blocked_write',)).fetchone() is None
    assert not (root/'no.txt').exists()


def test_compaction_keeps_trust_boundary_and_complete_tool_pair():
    messages = [{'role':'system','content':'trusted'}, {'role':'user','content':'old '*3000}, {'role':'assistant','tool_calls':[{'id':'x'}],'content':None}, {'role':'tool','tool_call_id':'x','content':'evidence'}, {'role':'user','content':'latest'}]
    compacted = coding_context.compact(messages, 8000, 3)
    assert compacted[0]['content'] == 'trusted'
    assert compacted[1]['role'] == 'user'
    assert compacted[-3:] == messages[-3:]


def test_background_command_handle_is_readable_across_turns_of_same_project(store, monkeypatch):
    _, settings, thread, project = store
    async def start(*args, **kwargs): return {'status':'running'}
    async def status(*args, **kwargs): return {'status':'completed','output':'done'}
    monkeypatch.setattr(terminal_tools,'start_command',start)
    monkeypatch.setattr(terminal_tools,'command_task',status)
    async def run():
        first = await cw.prepare_coding_workspace(turn_id='term_first', thread_id=thread['id'], project_id=project['id'])
        handle = await terminal_tools.execute_terminal('terminal_start',{'command':'python test.py'},settings,cw.workspace_path(first))
        second = await cw.prepare_coding_workspace(turn_id='term_second', thread_id=thread['id'], project_id=project['id'])
        result = await terminal_tools.execute_terminal('terminal_logs',{'task_id':handle['task_id']},settings,cw.workspace_path(second))
        assert result['output'] == 'done'
    asyncio.run(run())


def test_rewind_new_file_removes_current_files_but_keeps_version_history(store):
    _, settings, thread, project = store
    async def run():
        item = await cw.prepare_coding_workspace(thread_id=thread['id'], turn_id='rewind_turn', project_id=project['id'])
        root = cw.workspace_path(item)
        wt = workspace.use_workspace(root)
        ct = cw.use_coding_workspace(item)
        scoped = {**settings, '_project_id':project['id'], '_project_save':True}
        try:
            checkpoint = await engineering.execute('task_checkpoint', {'paths':['new.py']}, scoped, root, thread['id'])
            await agent.execute_tool('write_file', {'path':'new.py','content':'print(1)'}, scoped, {'write_file':('builtin',)}, thread_id=thread['id'], turn_id='rewind_turn')
            artifact = projects.list_artifacts(project['id'])[0]
            diff = await engineering.execute('task_diff', checkpoint, scoped, root, thread['id'])
            result = await agent.execute_tool('task_rewind', {**checkpoint,'expected_hashes':diff['expected_hashes']}, scoped, {'task_rewind':('builtin',)}, approved=True, thread_id=thread['id'], turn_id='rewind_turn')
            assert result['status'] == 'restored'
            assert not (projects.project_root(project['id'])/'new.py').exists()
            assert projects.list_artifacts(project['id']) == []
            assert not agent._has_turn_artifact('rewind_turn')
            assert projects.get_artifact_version_content(project['id'],artifact['id'],1) == b'print(1)'
        finally:
            cw.reset_coding_workspace(ct)
            workspace.reset_workspace(wt)
    asyncio.run(run())


def test_background_budget_continue_preserves_identity_and_is_single_claim(store):
    _, settings, _, project = store
    from fastapi import HTTPException
    task = main.enqueue_agent_task({'agent_id':settings['id'], 'prompt':'Task', 'project_id':project['id']})
    saved = {'messages':[{'role':'user','content':'Task'}], 'round':9, 'user_message':'Task'}
    agent.save_agent_run(settings, saved, 'waiting', task_id=task['id'])
    with db.connect() as connection:
        connection.execute("UPDATE tasks SET status='waiting',result=? WHERE id=?", (json.dumps({'status':'budget_exhausted'}), task['id']))
    result = main.continue_task_budget(task['id'])
    assert result['same_task'] is True
    assert agent.load_agent_run(task_id=task['id'])['state']['round'] == 0
    assert main.get_task(task['id'])['payload']['project_id'] == project['id']
    with pytest.raises(HTTPException) as error:
        main.continue_task_budget(task['id'])
    assert error.value.status_code == 409
