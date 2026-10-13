import asyncio
import json
import os
import uuid
from pathlib import Path

import httpx
import pytest
from backend.app import agent, chat_sessions, conversation_control as control, db, main, projects, workspace

@pytest.fixture
def session_store(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',str(tmp_path/'sessions.sqlite'))
    monkeypatch.setattr(workspace,'BASE_WORKSPACE',tmp_path/'workspace')
    monkeypatch.setattr(os,'chown',lambda *args:None,raising=False)
    monkeypatch.setattr(os,'fchown',lambda *args:None,raising=False)
    monkeypatch.setenv('CODEZZN_AUTH_REQUIRED','false')
    monkeypatch.delenv('CODEZZN_ADMIN_KEY',raising=False)
    monkeypatch.delenv('CODEZZN_LEGACY_OWNER_GITHUB_ID',raising=False)
    db.init_db(); main.THREAD_LOCKS.clear()
    provider=db.resource_save('providers',{'name':'Mock','api_key':'test-only','base_url':'https://example.invalid','models':['text-test'],'default_model':'text-test'})
    settings=db.resource_save('agents',{'name':'Assistant','provider_id':provider['id'],'model':'text-test','sandbox_mode':'workspace-write','role_template':'coding','auto_approve':True,'memory_enabled':False})
    thread=main.create_thread({'agent_id':settings['id']})
    calls=[]
    async def fake_run(scoped,history,content,**kwargs):
        calls.append({'agent':dict(scoped),'history':history,'content':content})
        return {'status':'completed','content':'完成：'+content,'events':[],'usage':{},'runtime':{},'sources':[]}
    async def no_destination(*args,**kwargs): return {'requires_project':False,'kind':'answer'}
    monkeypatch.setattr(main,'run_agent_isolated',fake_run)
    monkeypatch.setattr(main,'classify_intent',no_destination)
    runtime=control.ConversationRuntime()
    monkeypatch.setattr(control,'conversation_runtime',runtime)
    return thread,settings,runtime,calls

def token(): return str(uuid.uuid4())

def test_retry_is_linked_atomically_and_keeps_the_original_failure(session_store):
    thread,settings,runtime,calls=session_store
    original,_=control.enqueue(thread['id'],settings['id'],'原任务',{'attachment_ids':[]},token())
    control.finish_message(original['id'],'failed',error='原网络错误')
    retry_token=token()
    payload={'attachment_ids':[],'retry_of':original['id']}
    retried,created=control.enqueue(thread['id'],settings['id'],'原任务',payload,retry_token)
    assert created
    original_after=control.get_message(thread['id'],original['id'])
    assert original_after['run_status']=='failed' and original_after['error']=='原网络错误'
    assert control.public_message(original_after)['retried_by']==retried['id']
    assert control.public_message(retried)['retry_of']==original['id']
    same,created_again=control.enqueue(thread['id'],settings['id'],'原任务',payload,retry_token)
    assert not created_again and same['id']==retried['id']
    with pytest.raises(main.HTTPException) as exc:
        control.enqueue(thread['id'],settings['id'],'原任务',payload,token())
    assert exc.value.status_code==409
    assert len(control.messages(thread['id']))==2
    control.finish_message(retried['id'],'failed',error='本次错误')
    next_retry,_=control.enqueue(thread['id'],settings['id'],'原任务',{'attachment_ids':[],'retry_of':retried['id']},token())
    assert control.public_message(control.get_message(thread['id'],retried['id']))['retried_by']==next_retry['id']

def test_retry_rejects_other_threads_and_running_tasks_without_hiding_errors(session_store):
    thread,settings,runtime,calls=session_store
    original,_=control.enqueue(thread['id'],settings['id'],'原任务',{'attachment_ids':[]},token())
    other=main.create_thread({'agent_id':settings['id']})
    with pytest.raises(main.HTTPException) as exc:
        control.enqueue(other['id'],settings['id'],'原任务',{'attachment_ids':[],'retry_of':original['id']},token())
    assert exc.value.status_code==404
    with pytest.raises(main.HTTPException) as exc:
        control.enqueue(thread['id'],settings['id'],'原任务',{'attachment_ids':[],'retry_of':original['id']},token())
    assert exc.value.status_code==409
    assert len(control.messages(thread['id']))==1
    assert not control.public_message(control.get_message(thread['id'],original['id']))['retried_by']

def test_retry_http_contract_persists_the_link(session_store):
    thread,settings,runtime,calls=session_store
    original,_=control.enqueue(thread['id'],settings['id'],'原任务',{'attachment_ids':[]},token())
    control.finish_message(original['id'],'failed',error='原错误')
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
            response=await client.post(f"/api/threads/{thread['id']}/queue",json={'content':'原任务','agent_id':settings['id'],'submission_id':token(),'retry_of':original['id']})
            assert response.status_code==200
            assert response.json()['message']['retry_of']==original['id']
            listing=(await client.get(f"/api/threads/{thread['id']}/queue")).json()['data']
            assert listing[0]['retried_by']==response.json()['message']['id']
    asyncio.run(scenario())

async def wait_message(thread_id,message_id,status='completed',timeout=3):
    deadline=asyncio.get_running_loop().time()+timeout
    while asyncio.get_running_loop().time()<deadline:
        item=control.get_message(thread_id,message_id)
        if item['run_status']==status: return item
        if item['run_status']=='failed' and status!='failed': raise AssertionError(item)
        await asyncio.sleep(.01)
    raise AssertionError(control.get_message(thread_id,message_id))

def test_submission_is_idempotent_and_cannot_be_reused_for_another_task(session_store):
    thread,settings,runtime,calls=session_store
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
            payload={'content':'你好','agent_id':settings['id'],'submission_id':token()}
            first=await client.post(f"/api/threads/{thread['id']}/queue",json=payload)
            second=await client.post(f"/api/threads/{thread['id']}/queue",json=payload)
            assert first.status_code==second.status_code==200
            assert first.json()['message']['id']==second.json()['message']['id']
            assert second.json()['deduplicated'] is True
            conflict=await client.post(f"/api/threads/{thread['id']}/queue",json={**payload,'content':'不同任务'})
            assert conflict.status_code==409
            found=await client.get(f"/api/threads/{thread['id']}/queue",params={'submission_id':payload['submission_id']})
            assert len(found.json()['data'])==1 and calls==[]
    asyncio.run(scenario())

def test_background_execution_survives_submission_return_and_saves_to_selected_project(session_store):
    thread,settings,runtime,calls=session_store
    project=projects.create_project('Selected')
    with db.connect() as c: c.execute('UPDATE threads SET active_project_id=? WHERE id=?',(project['id'],thread['id']))
    async def scenario():
        await runtime.start(chat_sessions.execute_message,chat_sessions.resume_interaction)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
                response=await client.post(f"/api/threads/{thread['id']}/queue",json={'content':'生成代码','submission_id':token()})
                item=await wait_message(thread['id'],response.json()['message']['id'])
                assert item['status']=='consumed'
                assert calls[0]['agent']['_project_id']==project['id']
                assert calls[0]['agent']['_project_save'] is True
                fresh=(await client.get(f"/api/threads/{thread['id']}")).json()
                assert len(fresh['messages'])==2 and fresh['interactions']==[]
                with db.connect() as c: choice=c.execute('SELECT project_id,save_to_project FROM turn_projects WHERE turn_id=?',(item['turn_id'],)).fetchone()
                assert choice['project_id']==project['id'] and choice['save_to_project']==1
        finally: await runtime.close()
    asyncio.run(scenario())

def test_destination_question_persists_original_task_and_resumes_once_after_refresh(session_store,monkeypatch):
    thread,settings,runtime,calls=session_store
    project=projects.create_project('Destination')
    async def needs_project(*args,**kwargs): return {'requires_project':True,'kind':'file','suggested_name':'Script'}
    monkeypatch.setattr(main,'classify_intent',needs_project)
    async def scenario():
        await runtime.start(chat_sessions.execute_message,chat_sessions.resume_interaction)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
                sent=await client.post(f"/api/threads/{thread['id']}/queue",json={'content':'请生成一个脚本','submission_id':token()})
                message=await wait_message(thread['id'],sent.json()['message']['id'],'waiting_for_project')
                await runtime.close()
                await runtime.start(chat_sessions.execute_message,chat_sessions.resume_interaction)
                refreshed=(await client.get(f"/api/threads/{thread['id']}")).json()
                assert refreshed['messages'][0]['content']=='请生成一个脚本' and calls==[]
                interaction=refreshed['interactions'][0]
                assert interaction['kind']=='project_confirmation' and interaction['status']=='pending'
                answer={'submission_id':token(),'project_id':project['id']}
                path=f"/api/threads/{thread['id']}/interactions/{interaction['id']}/answer"
                assert (await client.post(path,json=answer)).status_code==200
                assert (await client.post(path,json=answer)).json()['deduplicated'] is True
                await wait_message(thread['id'],message['id'])
                assert len(calls)==1 and calls[0]['content']=='请生成一个脚本'
                assert (await client.post(path,json=answer)).json()['deduplicated'] is True
                assert (await client.post(path,json={**answer,'project_id':'prj_0123456789abcdef'})).status_code==404
        finally: await runtime.close()
    asyncio.run(scenario())

def test_follow_up_waits_for_previous_turn_and_receives_its_history(session_store,monkeypatch):
    thread,settings,runtime,calls=session_store
    async def scenario():
        started=asyncio.Event(); release=asyncio.Event()
        async def slow(scoped,history,content,**kwargs):
            calls.append((content,history))
            if content=='第一轮': started.set(); await release.wait()
            return {'status':'completed','content':'结果：'+content,'events':[],'usage':{},'runtime':{},'sources':[]}
        monkeypatch.setattr(main,'run_agent_isolated',slow)
        await runtime.start(chat_sessions.execute_message,chat_sessions.resume_interaction)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
                first=await client.post(f"/api/threads/{thread['id']}/queue",json={'content':'第一轮','submission_id':token()})
                await asyncio.wait_for(started.wait(),2)
                second=await client.post(f"/api/threads/{thread['id']}/queue",json={'content':'补充要求','submission_id':token()})
                assert second.json()['message']['status']=='pending' and len(calls)==1
                release.set()
                await wait_message(thread['id'],first.json()['message']['id'])
                await wait_message(thread['id'],second.json()['message']['id'])
                assert len(calls)==2
                assert any(value['role']=='assistant' and value['content']=='结果：第一轮' for value in calls[1][1])
        finally: await runtime.close()
    asyncio.run(scenario())

def test_interrupt_waits_for_cancelled_execution_before_dispatching_new_instruction(session_store,monkeypatch):
    thread,settings,runtime,calls=session_store
    async def scenario():
        started=asyncio.Event(); stopped=asyncio.Event()
        async def slow(scoped,history,content,**kwargs):
            calls.append(content)
            if content=='旧任务':
                started.set()
                try: await asyncio.Event().wait()
                finally: stopped.set()
            else: assert stopped.is_set()
            return {'status':'completed','content':'新的结果','events':[],'usage':{},'runtime':{},'sources':[]}
        monkeypatch.setattr(main,'run_agent_isolated',slow)
        await runtime.start(chat_sessions.execute_message,chat_sessions.resume_interaction)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
                old=await client.post(f"/api/threads/{thread['id']}/queue",json={'content':'旧任务','submission_id':token()})
                await asyncio.wait_for(started.wait(),2)
                pending=await client.post(f"/api/threads/{thread['id']}/queue",json={'content':'原有排队消息','submission_id':token()})
                new=await client.post(f"/api/threads/{thread['id']}/queue",json={'content':'立即调整','interrupt':True,'submission_id':token()})
                await wait_message(thread['id'],old.json()['message']['id'],'cancelled')
                await wait_message(thread['id'],new.json()['message']['id'])
                await wait_message(thread['id'],pending.json()['message']['id'])
                assert calls==['旧任务','立即调整','原有排队消息']
        finally: await runtime.close()
    asyncio.run(scenario())

def test_question_answer_is_exactly_matched_and_regular_messages_cannot_approve(session_store,monkeypatch):
    thread,settings,runtime,calls=session_store
    observed=[]
    async def context(*args): return 'Test'
    async def specs(*args): return [],{'ask_user':('builtin',None),'present_cards':('builtin',None)}
    async def completion(provider,model,messages,*args,**kwargs):
        observed.append(messages)
        if len(observed)==1:
            return {'role':'assistant','content':'','tool_calls':[{'id':'question_call','type':'function','function':{'name':'ask_user','arguments':json.dumps({'question':'选哪种排序？','options':[{'label':'快速排序'},{'label':'冒泡排序'}]})}}]},{}
        if len(observed)==2:
            return {'role':'assistant','content':'','tool_calls':[{'id':'resume_cards','type':'function','function':{'name':'present_cards','arguments':json.dumps({'cards':[{'id':'next','kind':'ready','title':'运行选择的方案','actions':[{'id':'run','label':'运行'}]}]})}}]},{}
        return {'role':'assistant','content':'收到你的选择','tool_calls':[]},{}
    async def run(scoped,history,content,**kwargs):
        return await agent.run_agent(scoped,history,content,**{**kwargs,'streaming':False})
    monkeypatch.setattr(agent,'build_context',context)
    monkeypatch.setattr(agent,'tool_specs',specs)
    monkeypatch.setattr(agent,'chat_completion',completion)
    monkeypatch.setattr(main,'run_agent_isolated',run)
    async def scenario():
        await runtime.start(chat_sessions.execute_message,chat_sessions.resume_interaction)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
                sent=await client.post(f"/api/threads/{thread['id']}/queue",json={'content':'帮我选择排序方案','submission_id':token()})
                message=await wait_message(thread['id'],sent.json()['message']['id'],'waiting_for_input')
                question=(await client.get(f"/api/threads/{thread['id']}/interactions")).json()['data'][0]
                pending=await client.post(f"/api/threads/{thread['id']}/queue",json={'content':'允许','submission_id':token()})
                assert pending.json()['message']['status']=='pending' and len(observed)==1
                answer={'submission_id':token(),'option_id':'option_0'}
                path=f"/api/threads/{thread['id']}/interactions/{question['id']}/answer"
                assert (await client.post(path,json=answer)).status_code==200
                assert (await client.post(path,json=answer)).json()['deduplicated'] is True
                await wait_message(thread['id'],message['id'])
                assert any(value.get('role')=='tool' and value.get('tool_call_id')=='question_call' and '快速排序' in value.get('content','') for value in observed[1])
                assert any(value['kind']=='decision_cards' and value['payload']['cards'][0]['id']=='next' for value in control.interactions(thread['id']))
                assert (await client.post(path,json={**answer,'option_id':'option_1'})).status_code==409
                assert (await client.post(path,json=answer)).json()['deduplicated'] is True
        finally: await runtime.close()
    asyncio.run(scenario())

def test_decision_card_feedback_is_contextual_and_atomically_queues_only_once(session_store):
    thread,settings,runtime,calls=session_store
    interaction=control.create_interaction(thread['id'],'turn_cards','decision_cards','选择方案',{'cards':[{'id':'a','kind':'ready','title':'方案 A','description':'外部显示信息','actions':[{'id':'run','label':'执行方案'}]}]})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
            path=f"/api/threads/{thread['id']}/interactions/{interaction['id']}/answer"
            payload={'submission_id':token(),'card_id':'a','action_id':'run'}
            result=await client.post(path,json=payload)
            assert result.status_code==200
            duplicate=await client.post(path,json=payload)
            assert duplicate.json()['deduplicated'] is True
            assert len(control.messages(thread['id']))==1
            text=json.loads(result.json()['message']['content'])
            assert text['user_decision']['card_id']=='a'
            assert text['user_decision']['action_id']=='run'
            assert text['untrusted_display_context']['title']=='方案 A'
            assert (await client.post(path,json={**payload,'action_id':'missing'})).status_code==400
    asyncio.run(scenario())

def test_message_and_interaction_ids_are_scoped_to_their_thread(session_store):
    thread,settings,runtime,calls=session_store
    other=main.create_thread({'agent_id':settings['id']})
    message,_=control.enqueue(thread['id'],settings['id'],'Hello',{},token())
    interaction=control.create_interaction(thread['id'],'turn_scope','question','Question',{})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
            assert (await client.get(f"/api/threads/{other['id']}/queue/{message['id']}")).status_code==404
            assert (await client.post(f"/api/threads/{other['id']}/interactions/{interaction['id']}/answer",json={'submission_id':token(),'answer':'yes'})).status_code==404
    asyncio.run(scenario())

def test_selected_runtime_configuration_cannot_change_under_queued_messages(session_store):
    thread,settings,runtime,calls=session_store
    control.enqueue(thread['id'],settings['id'],'Hello',{},token())
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
            assert (await client.patch(f"/api/threads/{thread['id']}",json={'model_override':{}})).status_code==409
            assert (await client.patch(f"/api/threads/{thread['id']}",json={'agent_id':settings['id']})).status_code==409
            assert (await client.patch(f"/api/threads/{thread['id']}",json={'name':'可修改标题'})).status_code==200
    asyncio.run(scenario())

def test_retrieval_mode_is_validated_on_agent_api(session_store):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
            assert (await client.post('/api/resources/agents',json={'name':'Invalid','retrieval_mode':'sometimes'})).status_code==400
    asyncio.run(scenario())

def test_stopping_a_waiting_question_invalidates_late_answers(session_store):
    thread,settings,runtime,calls=session_store
    message,_=control.enqueue(thread['id'],settings['id'],'Paused',{},token())
    turn_id='turn_paused'
    approval_id=db.new_id('approval')
    with db.connect() as c:
        c.execute("UPDATE chat_queue_messages SET turn_id=?,status='consumed',run_status='waiting_for_input' WHERE id=?",(turn_id,message['id']))
        c.execute("UPDATE threads SET status='waiting_for_input' WHERE id=?",(thread['id'],))
        c.execute('INSERT INTO approvals(id,thread_id,turn_id,tool_name,arguments,created_at,tool_call_id,resumable) VALUES(?,?,?,?,?,?,?,1)',(approval_id,thread['id'],turn_id,'ask_user','{"question":"Continue?"}',db.now(),'paused_call'))
        c.execute("INSERT INTO turn_checkpoints(id,thread_id,turn_id,agent_id,status,state,created_at,updated_at) VALUES(?,?,?,?,'waiting','{}',?,?)",(db.new_id('checkpoint'),thread['id'],turn_id,settings['id'],db.now(),db.now()))
    question=control.interactions(thread['id'])[0]
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
            stopped=await client.delete(f"/api/threads/{thread['id']}/turns/active")
            assert stopped.json()['cancelled'] is True
            assert control.get_message(thread['id'],message['id'])['run_status']=='cancelled'
            late=await client.post(f"/api/threads/{thread['id']}/interactions/{question['id']}/answer",json={'submission_id':token(),'answer':'继续'})
            assert late.status_code==409 and calls==[]
    asyncio.run(scenario())

def test_no_project_ordinary_task_does_not_add_a_classifier_model_call(session_store,monkeypatch):
    from backend.app import intent
    thread,settings,runtime,calls=session_store
    monkeypatch.setattr(main,'classify_intent',intent.classify_intent)
    def forbidden(*args): raise AssertionError('destination preflight must not call a model')
    monkeypatch.setattr(intent,'model_candidates',forbidden)
    async def scenario():
        await runtime.start(chat_sessions.execute_message,chat_sessions.resume_interaction)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
                sent=await client.post(f"/api/threads/{thread['id']}/queue",json={'content':'帮我分析附件里的问题','submission_id':token()})
                await wait_message(thread['id'],sent.json()['message']['id'])
                assert len(calls)==1
        finally: await runtime.close()
    asyncio.run(scenario())

def test_selected_project_does_not_prevent_read_only_agent_from_answering(session_store):
    thread,settings,runtime,calls=session_store
    project=projects.create_project('Read only')
    db.resource_save('agents',{**settings,'sandbox_mode':'read-only','role_template':'general'},settings['id'])
    async def scenario():
        await runtime.start(chat_sessions.execute_message,chat_sessions.resume_interaction)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
                sent=await client.post(f"/api/threads/{thread['id']}/queue",json={'content':'解释一下项目内容','project_id':project['id'],'save_to_project':True,'submission_id':token()})
                assert sent.status_code==200
                await wait_message(thread['id'],sent.json()['message']['id'])
                assert calls[0]['agent']['sandbox_mode']=='read-only'
                assert (await agent.execute_tool('write_file',{'path':'blocked.txt','content':'x'},calls[0]['agent'],{'write_file':('builtin',None)},approved=True,thread_id=thread['id'],turn_id='turn_check'))['error']['code']=='approval_required'
                assert not (projects.project_root(project['id'])/'blocked.txt').exists()
        finally: await runtime.close()
    asyncio.run(scenario())


def test_consumed_answer_failure_cannot_replay_its_tool(session_store,monkeypatch):
    from fastapi import HTTPException
    thread,settings,runtime,calls=session_store
    queued,_=control.enqueue(thread['id'],settings['id'],'Paused',{},token())
    with db.connect() as c:
        c.execute("UPDATE chat_queue_messages SET status='consumed',run_status='waiting_for_input',turn_id='turn_failure' WHERE id=?",(queued['id'],))
        c.execute("UPDATE threads SET status='waiting_for_input' WHERE id=?",(thread['id'],))
    item=control.create_interaction(thread['id'],'turn_failure','question','Continue?',{},queued['id'],approval_id='approval_failure',tool_call_id='call_failure')
    async def fail_after_consumption(*args):
        calls.append('consumed')
        raise HTTPException(502,'downstream model failed after tool execution')
    monkeypatch.setattr(main,'continue_approval',fail_after_consumption)
    async def scenario():
        await runtime.start(chat_sessions.execute_message,chat_sessions.resume_interaction)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
                path=f"/api/threads/{thread['id']}/interactions/{item['id']}/answer"
                answer={'submission_id':token(),'answer':'Continue'}
                assert (await client.post(path,json=answer)).status_code==200
                await wait_message(thread['id'],queued['id'],'failed')
                assert (await client.post(path,json=answer)).json()['deduplicated'] is True
                assert (await client.post(path,json={**answer,'submission_id':token()})).status_code==409
                assert calls==['consumed']
                assert control.get_interaction(thread['id'],item['id'])['status']=='answered'
        finally: await runtime.close()
    asyncio.run(scenario())


def test_restart_does_not_blindly_replay_claimed_run_but_dispatches_pending_message(session_store):
    thread,settings,runtime,calls=session_store
    old,_=control.enqueue(thread['id'],settings['id'],'Possibly executed tool',{},token())
    pending,_=control.enqueue(thread['id'],settings['id'],'New continuation',{},token())
    with db.connect() as c:
        c.execute("UPDATE chat_queue_messages SET status='dispatching',run_status='running',runner_id='old-process',turn_id='turn_restart' WHERE id=?",(old['id'],))
        c.execute("UPDATE threads SET status='running' WHERE id=?",(thread['id'],))
        c.execute("INSERT INTO approvals(id,thread_id,turn_id,tool_name,arguments,status,created_at,tool_call_id,resumable) VALUES(?,?,?,'ask_user','{}','approved',?,'restart_call',1)",('approval_restart',thread['id'],'turn_restart',db.now()))
        c.execute("INSERT INTO turn_checkpoints(id,thread_id,turn_id,agent_id,status,state,created_at,updated_at) VALUES(?,?,?,?,'resuming','{}',?,?)",(db.new_id('checkpoint'),thread['id'],'turn_restart',settings['id'],db.now(),db.now()))
    question=control.create_interaction(thread['id'],'turn_restart','question','Continue?',{},old['id'],approval_id='approval_restart',tool_call_id='restart_call')
    control.claim_answer(thread['id'],question['id'],{'decision':'approved','answer':'yes'},token())
    async def scenario():
        await runtime.start(chat_sessions.execute_message,chat_sessions.resume_interaction)
        try:
            assert control.get_message(thread['id'],old['id'])['run_status']=='failed'
            restored=control.get_interaction(thread['id'],question['id'])
            assert restored['status']=='answered' and restored['error']
            with db.connect() as c:
                assert c.execute("SELECT status FROM turn_checkpoints WHERE turn_id='turn_restart'").fetchone()['status']=='failed'
            await wait_message(thread['id'],pending['id'])
            assert [value['content'] for value in calls]==['New continuation']
        finally: await runtime.close()
    asyncio.run(scenario())


def test_stopping_answer_continuation_cancels_checkpoint_and_records_running_queue(session_store,monkeypatch):
    thread,settings,runtime,calls=session_store
    queued,_=control.enqueue(thread['id'],settings['id'],'Paused',{},token())
    turn_id='turn_resuming_stop'; approval_id='approval_resuming_stop'
    with db.connect() as c:
        c.execute("UPDATE chat_queue_messages SET status='consumed',run_status='waiting_for_input',turn_id=? WHERE id=?",(turn_id,queued['id']))
        c.execute("UPDATE threads SET status='waiting_for_input' WHERE id=?",(thread['id'],))
        c.execute('INSERT INTO approvals(id,thread_id,turn_id,tool_name,arguments,created_at,tool_call_id,resumable) VALUES(?,?,?,?,?,?,?,1)',(approval_id,thread['id'],turn_id,'ask_user','{"question":"Continue?"}',db.now(),'resume_call'))
        c.execute("INSERT INTO turn_checkpoints(id,thread_id,turn_id,agent_id,status,state,created_at,updated_at) VALUES(?,?,?,?,'waiting','{}',?,?)",(db.new_id('checkpoint'),thread['id'],turn_id,settings['id'],db.now(),db.now()))
    item=control.interactions(thread['id'])[0]
    async def scenario():
        started=asyncio.Event()
        async def block(*args,**kwargs):
            started.set(); await asyncio.Event().wait()
        monkeypatch.setattr(main,'run_agent_isolated',block)
        await runtime.start(chat_sessions.execute_message,chat_sessions.resume_interaction)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
                path=f"/api/threads/{thread['id']}/interactions/{item['id']}/answer"
                answer={'submission_id':token(),'answer':'Continue'}
                assert (await client.post(path,json=answer)).status_code==200
                await asyncio.wait_for(started.wait(),2)
                assert control.get_message(thread['id'],queued['id'])['run_status']=='running'
                assert (await client.delete(f"/api/threads/{thread['id']}/turns/active")).json()['cancelled'] is True
                assert control.get_message(thread['id'],queued['id'])['run_status']=='cancelled'
                with db.connect() as c:
                    assert c.execute('SELECT status FROM turn_checkpoints WHERE turn_id=?',(turn_id,)).fetchone()['status']=='cancelled'
                    assert c.execute('SELECT status FROM threads WHERE id=?',(thread['id'],)).fetchone()['status']=='idle'
                assert (await client.post(path,json={**answer,'submission_id':token()})).status_code==409
        finally: await runtime.close()
    asyncio.run(scenario())
