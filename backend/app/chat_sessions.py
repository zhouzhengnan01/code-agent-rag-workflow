"""HTTP contracts and background execution for Codezzn conversation sessions."""
import asyncio
import json
from fastapi import APIRouter, Body, HTTPException
from . import chat_inputs, conversation_control as control
from .db import connect, new_id, now, resource_get
from .projects import create_project, get_project, list_projects

router=APIRouter()
handlers={}

def install(app,namespace):
    global handlers
    handlers=namespace
    app.include_router(router)

def thread_row(thread_id):
    with connect() as db: row=db.execute('SELECT * FROM threads WHERE id=?',(thread_id,)).fetchone()
    if not row: raise HTTPException(404,'对话不存在')
    return row

def current_agent(thread,agent_id=None,model_override=None):
    agent=resource_get('agents',agent_id or thread['agent_id'])
    if not agent or agent.get('enabled') is False: raise HTTPException(400,'请选择有效的智能体')
    scoped=handlers['_agent_for_thread'](agent,thread)
    if model_override is not None: scoped=chat_inputs.apply_override(scoped,model_override)
    return scoped

def message_event(thread_id,turn_id,event):
    with connect() as db:
        sequence=db.execute('SELECT COALESCE(MAX(sequence),0)+1 AS n FROM turn_events WHERE turn_id=?',(turn_id,)).fetchone()['n']
    handlers['persist_event'](event,thread_id,turn_id,sequence)

def persist_cards(thread_id,turn_id,event,message_id=None):
    if event.get('type')=='interaction_cards':
        control.create_interaction(thread_id,turn_id,'decision_cards','选择下一步或补充你的要求',{'cards':event['cards']},message_id,tool_call_id=event.get('tool_call_id'))

def append_assistant(thread_id,turn_id,content,meta=None):
    with connect() as db:
        existing=db.execute("SELECT 1 FROM messages WHERE thread_id=? AND turn_id=? AND role='assistant'",(thread_id,turn_id)).fetchone()
        if not existing:
            db.execute('INSERT INTO messages(id,thread_id,turn_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?,?)',(new_id('msg'),thread_id,turn_id,'assistant',content,control.encode(meta or {}),now()))

def finalize_result(item,result):
    thread_id,turn_id=item['thread_id'],item['turn_id']
    if result.get('status')=='waiting_for_input':
        control.finish_message(item['id'],'waiting_for_input',result)
        with connect() as db: db.execute("UPDATE threads SET status='waiting_for_input',updated_at=? WHERE id=?",(now(),thread_id))
    elif result.get('status')=='waiting_for_approval':
        control.sync_approvals(thread_id)
        with connect() as db:
            approval=db.execute('SELECT tool_name FROM approvals WHERE id=?',(result.get('approval_id'),)).fetchone()
        status='waiting_for_input' if approval and approval['tool_name']=='ask_user' else 'waiting_for_approval'
        control.finish_message(item['id'],status,result)
        with connect() as db: db.execute('UPDATE threads SET status=?,updated_at=? WHERE id=?',(status,now(),thread_id))
    else:
        append_assistant(thread_id,turn_id,result.get('content',''),{key:result.get(key) for key in ('events','usage','runtime','sources')})
        control.finish_message(item['id'],'completed',result)
        with connect() as db: db.execute("UPDATE threads SET status='idle',updated_at=? WHERE id=?",(now(),thread_id))

async def execute_message(item):
    thread_id=item['thread_id']
    lock=await handlers['thread_lock'](thread_id)
    async with lock:
        thread=thread_row(thread_id)
        payload=item.get('payload') or {}
        agent=current_agent(thread,item['agent_id'],payload.get('model_override'))
        if payload.get('_recovering'): agent['_recovering']=True
        attachments=chat_inputs.resolve_ids(payload.get('attachment_ids',[]))
        with connect() as db:
            history=[dict(row) for row in db.execute('SELECT role,content,meta FROM messages WHERE thread_id=? ORDER BY created_at,rowid',(thread_id,))]
        history=chat_inputs.history_inputs(history)
        chat_inputs.validate_model_inputs(agent,item['content'],attachments,history)
        turn_id=item.get('turn_id') or new_id('turn')
        item={**item,'turn_id':turn_id}
        with connect() as db:
            db.execute("UPDATE chat_queue_messages SET status='consumed',turn_id=?,updated_at=? WHERE id=?",(turn_id,now(),item['id']))
            db.execute('UPDATE threads SET agent_id=?,updated_at=? WHERE id=?',(item['agent_id'],now(),thread_id))
            exists=db.execute("SELECT 1 FROM messages WHERE thread_id=? AND turn_id=? AND role='user'",(thread_id,turn_id)).fetchone()
            if not exists: db.execute('INSERT INTO messages(id,thread_id,turn_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?,?)',(new_id('msg'),thread_id,turn_id,'user',item['content'],control.encode({'attachments':[chat_inputs.public(value) for value in attachments],'queue_message_id':item['id']}),now()))
        message_event(thread_id,turn_id,{'id':new_id('evt'),'type':'turn_accepted','queue_message_id':item['id']})
        try:
            directive=None if payload.get('destination_confirmed') else handlers['parse_project_directive'](item['content'],list_projects())
            if directive:
                if directive.get('project_id'):
                    payload={**payload,'project_id':directive['project_id'],'save_to_project':True}
                    if not directive.get('remaining_task'):
                        with connect() as db:
                            db.execute('UPDATE threads SET active_project_id=?,updated_at=? WHERE id=?',(directive['project_id'],now(),thread_id))
                            db.execute('INSERT OR IGNORE INTO thread_projects(thread_id,project_id,created_at) VALUES(?,?,?)',(thread_id,directive['project_id'],now()))
                        finalize_result(item,{'status':'completed','content':f"已切换到项目：{directive['project_name']}",'events':[],'usage':{},'runtime':{},'sources':[]})
                        return
                else:
                    interaction=control.create_interaction(thread_id,turn_id,'project_confirmation',f"项目“{directive['project_name']}”不存在，请选择去向",{'projects':[{'id':p['id'],'name':p['name']} for p in list_projects()],'allow_create':True,'suggested_name':directive['project_name'][:32],'intent_kind':'file'},item['id'])
                    control.finish_message(item['id'],'waiting_for_project',{'interaction_id':interaction['id']})
                    with connect() as db: db.execute("UPDATE threads SET status='waiting_for_project',updated_at=? WHERE id=?",(now(),thread_id))
                    return
            # Destination classification is only needed when no workspace is selected.
            # The full request and attachments have already been persisted before asking.
            if not agent.get('_project_id') and not payload.get('project_id'):
                intent=await handlers['classify_intent'](agent,item['content'][:8000],history,projects=list_projects(),attachments=attachments,allow_model=False)
                if intent.get('project_switch_only'):
                    project_id=intent.get('target_project_id')
                    if not project_id: raise ValueError('指定项目不存在，请选择现有项目或创建新项目')
                    with connect() as db: db.execute('UPDATE threads SET active_project_id=?,updated_at=? WHERE id=?',(project_id,now(),thread_id))
                    finalize_result(item,{'status':'completed','content':f"已切换到项目：{intent['target_project_name']}",'events':[],'usage':{},'runtime':{},'sources':[]})
                    return
                if intent.get('target_project_id'):
                    payload={**payload,'project_id':intent['target_project_id'],'save_to_project':True,'intent_kind':intent.get('kind','file')}
                elif intent.get('requires_project'):
                    if not handlers['_agent_can_save_project_files'](agent,intent.get('kind','file')):
                        raise PermissionError('当前智能体没有执行该产物任务的写入能力，请检查工具策略和沙箱模式')
                    projects=[{'id':project['id'],'name':project['name']} for project in list_projects()]
                    interaction=control.create_interaction(thread_id,turn_id,'project_confirmation','这个任务会生成文件，要保存到哪个项目？',{'projects':projects,'allow_create':True,'suggested_name':intent.get('suggested_name','')[:32],'intent_kind':intent.get('kind','file')},item['id'])
                    control.finish_message(item['id'],'waiting_for_project',{'interaction_id':interaction['id']})
                    with connect() as db: db.execute("UPDATE threads SET status='waiting_for_project',updated_at=? WHERE id=?",(now(),thread_id))
                    message_event(thread_id,turn_id,{'id':new_id('evt'),'type':'interaction_required','interaction_id':interaction['id'],'kind':'project_confirmation'})
                    return
            project_id=payload.get('project_id') or thread['active_project_id']
            if project_id:
                if not get_project(project_id): raise ValueError('目标项目不存在')
                save=payload.get('save_to_project',True)
                with connect() as db:
                    db.execute('INSERT OR REPLACE INTO turn_projects(turn_id,thread_id,project_id,save_to_project,created_at) VALUES(?,?,?,?,?)',(turn_id,thread_id,project_id,int(save),now()))
                    db.execute('INSERT OR IGNORE INTO thread_projects(thread_id,project_id,created_at) VALUES(?,?,?)',(thread_id,project_id,now()))
                    db.execute('UPDATE threads SET active_project_id=?,agent_id=?,status=\'running\',updated_at=? WHERE id=?',(project_id,item['agent_id'],now(),thread_id))
                agent['_project_id']=project_id
                agent['_project_save']=save
                agent['memory_project_id']=project_id
            agent['_turn_attachments']=attachments
            if payload.get('destination_confirmed') and project_id:
                agent['system_prompt']=agent.get('system_prompt','You are a helpful assistant.')+'\n用户已为当前请求明确选择保存项目 '+project_id+'。以此项目为准，不再根据原请求中的未解析项目名重复询问或创建其他项目。'
            async def emit(event):
                message_event(thread_id,turn_id,event)
                persist_cards(thread_id,turn_id,event,item['id'])
                if event.get('type')=='approval_required': control.sync_approvals(thread_id)
            result=await handlers['run_agent_isolated'](agent,history,item['content'],on_event=emit,streaming=True,thread_id=thread_id,turn_id=turn_id)
            finalize_result(item,result)
        except asyncio.CancelledError:
            if control.conversation_runtime.stopping:
                # Process shutdown is not a user's stop request. Keep the existing
                # checkpoint, queue ID and turn for safe restart recovery.
                message_event(thread_id,turn_id,{'id':new_id('evt'),'type':'turn_suspended','turn_id':turn_id,'reason':'service_shutdown'})
                raise
            message_event(thread_id,turn_id,{'id':new_id('evt'),'type':'turn_cancelled','turn_id':turn_id})
            append_assistant(thread_id,turn_id,'任务已停止。已完成的操作和生成的文件保留，可继续补充要求。',{'cancelled':True})
            with connect() as db: db.execute("UPDATE agent_runs SET status='cancelled',updated_at=? WHERE turn_id=? AND status IN ('running','waiting')",(now(),turn_id))
            raise
        except Exception as error:
            message_event(thread_id,turn_id,{'id':new_id('evt'),'type':'turn_error','message':str(error)[:1200]})
            append_assistant(thread_id,turn_id,'任务执行失败：'+str(error)[:1200],{'error':True})
            with connect() as db: db.execute("UPDATE agent_runs SET status='failed',error=?,updated_at=? WHERE turn_id=? AND status IN ('running','waiting')",(str(error)[:4000],now(),turn_id))
            raise

async def resume_interaction(item):
    thread_id=item['thread_id']
    response=item.get('response') or {}
    if item.get('payload',{}).get('resume_mode')=='budget':
        return await resume_budget_interaction(item)
    if item['kind']=='question' and response.get('decision')=='denied':
        control.cancel_waiting(thread_id,'用户已取消此任务')
        control.finish_interaction(item['id'],'cancelled')
        append_assistant(thread_id,item['turn_id'],'已取消本次任务。已完成的操作和产物保留。',{'cancelled':True})
        return
    if item['kind']=='project_confirmation':
        if response.get('decision')=='denied':
            control.finish_interaction(item['id'],'cancelled')
            control.finish_message(item['queue_message_id'],'cancelled')
            append_assistant(thread_id,item['turn_id'],'已取消本次产物任务。',{'cancelled':True})
            with connect() as db: db.execute("UPDATE threads SET status='idle',updated_at=? WHERE id=?",(now(),thread_id))
            return
        project_id=response.get('project_id')
        if not project_id:
            project_id=create_project(response['new_project_name'])['id']
        if not get_project(project_id): raise ValueError('选择的项目不存在')
        message=control.get_message(thread_id,item['queue_message_id'])
        payload={**message['payload'],'project_id':project_id,'save_to_project':True,'intent_kind':item['payload'].get('intent_kind','file'),'destination_confirmed':True}
        with connect() as db:
            db.execute('UPDATE chat_queue_messages SET payload=?,run_status=\'running\',updated_at=? WHERE id=?',(control.encode(payload),now(),message['id']))
            db.execute('UPDATE threads SET active_project_id=?,status=\'running\',updated_at=? WHERE id=?',(project_id,now(),thread_id))
        control.finish_interaction(item['id'])
        await execute_message({**message,'payload':payload})
        return
    previous_status=None
    if item.get('queue_message_id'):
        previous_status=control.get_message(thread_id,item['queue_message_id'])['run_status']
        with connect() as db:
            db.execute("UPDATE chat_queue_messages SET run_status='running',updated_at=? WHERE id=?",(now(),item['queue_message_id']))
    try:
        result=await handlers['continue_approval'](item['approval_id'],response['decision'],response.get('answer') or response['decision'])
        control.finish_interaction(item['id'])
        if item.get('queue_message_id'):
            message=control.get_message(thread_id,item['queue_message_id'])
            finalize_result(message,result)
    except HTTPException as error:
        with connect() as db: approval=db.execute('SELECT status FROM approvals WHERE id=?',(item['approval_id'],)).fetchone()
        if approval and approval['status']=='pending':
            # The answer was accepted but execution prerequisites failed before consumption.
            # Keep the user's answer available for an explicit retry after repair.
            control.finish_interaction(item['id'],'pending',str(error.detail)[:1200])
            if previous_status:
                with connect() as db:
                    db.execute('UPDATE chat_queue_messages SET run_status=?,updated_at=? WHERE id=?',(previous_status,now(),item['queue_message_id']))
            raise
        control.finish_interaction(item['id'],'answered',str(error.detail)[:1200])
        if item.get('queue_message_id'): control.finish_message(item['queue_message_id'],'failed',error=str(error.detail)[:1200])


async def resume_budget_interaction(item):
    """Continue the same persisted turn, never synthesize a second user message."""
    from .agent import save_agent_run
    from .tasks import get_task, cancel_task, finish_waiting_task
    thread_id,turn_id=item['thread_id'],item['turn_id']
    response=item.get('response') or {}
    stop=response.get('decision')=='denied' or response.get('option_id')=='stop' or response.get('answer') in {'停止任务','stop'}
    if not stop and response.get('option_id')!='continue' and response.get('answer') not in {'继续执行','continue'}:
        raise HTTPException(400,'请选择继续执行或停止任务；普通文本不自动授予新执行预算')
    lock=await handlers['thread_lock'](thread_id)
    async with lock:
        latest=control.get_interaction(thread_id,item['id'])
        if latest['status']!='submitting':
            return  # Answer replay after completion is a no-op.
        if stop:
            with connect() as db:
                saved = db.execute('SELECT state FROM turn_checkpoints WHERE turn_id=?', (turn_id,)).fetchone()
                task_id = json.loads(saved['state'] or '{}').get('task_id') if saved else None
                db.execute("UPDATE agent_runs SET status='cancelled',updated_at=? WHERE thread_id=? AND turn_id=? AND status IN ('running','waiting','recovering')",(now(),thread_id,turn_id))
                db.execute("UPDATE turn_checkpoints SET status='cancelled',updated_at=? WHERE thread_id=? AND turn_id=?",(now(),thread_id,turn_id))
                db.execute("UPDATE threads SET status='idle',updated_at=? WHERE id=?",(now(),thread_id))
            if item.get('queue_message_id'): control.finish_message(item['queue_message_id'],'cancelled',error='用户选择停止预算续跑')
            if task_id: cancel_task(task_id)
            control.finish_interaction(item['id'],'cancelled')
            append_assistant(thread_id,turn_id,'任务已停止。已完成的操作和文件保留。',{'cancelled':True,'budget_paused':True})
            return
        with connect() as db:
            checkpoint=db.execute("SELECT * FROM turn_checkpoints WHERE thread_id=? AND turn_id=? AND status IN ('waiting','resuming')",(thread_id,turn_id)).fetchone()
        if not checkpoint: raise HTTPException(409,'执行检查点已不存在或任务已结束，不能继续旧预算')
        state=json.loads(checkpoint['state'] or '{}')
        task_id = state.get('task_id')
        if task_id and (get_task(task_id) or {}).get('status') == 'cancelled':
            raise HTTPException(409, '后台任务已取消，不能继续旧预算')
        if not state.get('budget_paused'): raise HTTPException(409,'此检查点不是等待执行预算的任务')
        thread=thread_row(thread_id)
        scoped=current_agent(thread,checkpoint['agent_id'])
        state['round']=0
        state['budget_paused']=False
        state['budget_resumptions']=int(state.get('budget_resumptions',0))+1
        # Preserve original provider/model, while re-evaluating current tool rights.
        if state.get('provider_id') and state.get('model'):
            scoped=chat_inputs.apply_override(scoped,{'provider_id':state['provider_id'],'model':state['model']})
        save_agent_run(scoped,state,'running',thread_id,turn_id,task_id,response_id=state.get('previous_response_id'))
        with connect() as db:
            db.execute("UPDATE turn_checkpoints SET status='resuming',state=?,updated_at=? WHERE turn_id=?",(control.encode(state),now(),turn_id))
            db.execute("UPDATE threads SET status='running',updated_at=? WHERE id=?",(now(),thread_id))
            if item.get('queue_message_id'): db.execute("UPDATE chat_queue_messages SET run_status='running',updated_at=? WHERE id=?",(now(),item['queue_message_id']))
            history=[dict(row) for row in db.execute('SELECT role,content,meta FROM messages WHERE thread_id=? ORDER BY created_at,rowid',(thread_id,))]
        control.finish_interaction(item['id'])
        async def emit(event):
            message_event(thread_id,turn_id,event)
            persist_cards(thread_id,turn_id,event,item.get('queue_message_id'))
            if event.get('type')=='approval_required': control.sync_approvals(thread_id)
        result=await handlers['run_agent_isolated'](scoped,chat_inputs.history_inputs(history),state.get('user_message',''),on_event=emit,streaming=True,thread_id=thread_id,turn_id=turn_id,resume_state=state,**({'task_id':task_id} if task_id else {}))
        finish_waiting_task(task_id, result)
        if item.get('queue_message_id'):
            finalize_result(control.get_message(thread_id,item['queue_message_id']),result)
        if result.get('status')=='completed':
            with connect() as db: db.execute("UPDATE turn_checkpoints SET status='completed',updated_at=? WHERE turn_id=?",(now(),turn_id))

@router.post('/api/threads/{thread_id}/queue')
async def submit_message(thread_id:str,payload:dict=Body(...)):
    thread=thread_row(thread_id)
    content=payload.get('content',payload.get('text',''))
    if not isinstance(content,str) or len(content)>32000: raise HTTPException(400,'消息必须为不超过 32000 字符的文本')
    attachments=chat_inputs.resolve_ids(payload.get('attachment_ids',[]))
    content=content.strip() or ('请分析附件内容。' if attachments else '')
    if not content: raise HTTPException(400,'请输入任务或添加附件')
    interrupt=payload.get('interrupt',False)
    if type(interrupt) is not bool: raise HTTPException(400,'interrupt 必须为布尔值')
    agent=current_agent(thread,payload.get('agent_id'))
    chat_inputs.validate_model_inputs(agent,content,attachments,[])
    saved={'attachment_ids':[item['id'] for item in attachments],'model_override':json.loads(thread['model_override'] or '{}')}
    if 'retry_of' in payload:
        if not isinstance(payload['retry_of'], str) or not 1 <= len(payload['retry_of']) <= 100:
            raise HTTPException(400, 'retry_of 必须为有效的原任务 ID')
        saved['retry_of'] = payload['retry_of']
    if 'project_id' in payload or 'save_to_project' in payload:
        # A destination is not permission to execute a writing tool. Read-only
        # Agents can still answer in selected projects; actual tools enforce policy.
        with connect() as db: handlers['_validate_turn_project_choice'](db,payload)
        saved.update({key:payload[key] for key in ('project_id','save_to_project','intent_kind') if key in payload})
    item,created=control.enqueue(thread_id,agent['id'],content,saved,payload.get('submission_id'),interrupt)
    if created and interrupt:
        active=handlers['ACTIVE_TURNS'].get(thread_id)
        if active and not active['task'].done():
            active['task'].cancel()
            await asyncio.gather(active['task'],return_exceptions=True)
        await control.conversation_runtime.cancel(thread_id)
    control.conversation_runtime.notify()
    return {'message':control.public_message(control.get_message(thread_id,item['id'])),'accepted':True,'deduplicated':not created}

@router.get('/api/threads/{thread_id}/queue')
def list_messages(thread_id:str,submission_id:str=''):
    thread_row(thread_id)
    return {'data':control.messages(thread_id,submission_id or None)}

@router.get('/api/threads/{thread_id}/queue/{message_id}')
def read_message(thread_id:str,message_id:str):
    return {'message':control.public_message(control.get_message(thread_id,message_id))}

@router.delete('/api/threads/{thread_id}/queue/{message_id}')
async def cancel_message(thread_id:str,message_id:str):
    item=control.get_message(thread_id,message_id)
    if item['status']=='pending': control.finish_message(message_id,'cancelled')
    elif item['run_status'] not in control.TERMINAL_RUNS:
        await control.conversation_runtime.cancel(thread_id)
    control.conversation_runtime.notify()
    return {'message':control.public_message(control.get_message(thread_id,message_id))}

@router.post('/api/threads/{thread_id}/queue/{message_id}/dismiss')
def dismiss_message(thread_id:str,message_id:str):
    thread_row(thread_id)
    item,changed=control.dismiss_failed_message(thread_id,message_id)
    return {'message':control.public_message(item),'dismissed':True,'deduplicated':not changed}

@router.get('/api/threads/{thread_id}/interactions')
def list_interactions(thread_id:str):
    thread_row(thread_id)
    return {'data':control.interactions(thread_id)}

@router.post('/api/threads/{thread_id}/interactions/{interaction_id}/answer')
async def answer_interaction(thread_id:str,interaction_id:str,payload:dict=Body(...)):
    thread_row(thread_id)
    item=control.get_interaction(thread_id,interaction_id)
    if item['kind']=='decision_cards': return await answer_card(item,payload)
    submission_id=control.submission(payload.get('submission_id'))
    decision=payload.get('decision','approved')
    if decision not in {'approved','denied'}: raise HTTPException(400,'decision 必须为 approved 或 denied')
    response={'decision':decision}
    if item['kind']=='project_confirmation' and decision!='denied':
        project_id=payload.get('project_id')
        name=payload.get('new_project_name')
        if project_id:
            if not isinstance(project_id,str) or not get_project(project_id): raise HTTPException(404,'项目不存在')
            response['project_id']=project_id
        elif isinstance(name,str) and 1<=len(name.strip())<=80:
            response['new_project_name']=name.strip()
        else: raise HTTPException(400,'请选择项目或填写新项目名称')
    elif item['kind']=='question':
        answer=payload.get('answer','')
        if payload.get('option_id'):
            option=next((value for value in item['payload'].get('options',[]) if value['id']==payload['option_id']),None)
            if not option: raise HTTPException(400,'选项不存在')
            answer=option['label']
            response['option_id']=option['id']
        if decision=='denied': answer='用户取消本次提问'
        if not isinstance(answer,str) or not answer.strip() or len(answer)>4000: raise HTTPException(400,'请填写不超过 4000 字符的回答')
        response['answer']=answer.strip()
    elif item['kind']=='tool_approval':
        if 'decision' not in payload: raise HTTPException(400,'工具授权必须明确允许或拒绝')
        response['answer']=str(payload.get('answer') or decision)[:4000]
    updated,created=control.claim_answer(thread_id,interaction_id,response,submission_id)
    control.conversation_runtime.notify()
    return {'interaction':control.public_interaction(updated),'accepted':True,'deduplicated':not created}

async def answer_card(item,payload):
    submission_id=control.submission(payload.get('submission_id'))
    card=next((card for card in item['payload'].get('cards',[]) if card['id']==payload.get('card_id')),None)
    if not card: raise HTTPException(400,'决策卡片不存在')
    action_id=payload.get('action_id')
    action=next((action for action in card['actions'] if action['id']==action_id),None) if action_id else None
    if action_id and not action: raise HTTPException(400,'卡片选项不存在')
    answer=payload.get('answer','')
    if not action and (not isinstance(answer,str) or not answer.strip() or len(answer)>4000): raise HTTPException(400,'请选择选项或填写回答')
    response={'submission_id':submission_id,**({'action_id':action_id} if action else {'answer':answer.strip()})}
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM chat_interactions WHERE id=? AND thread_id=?',(item['id'],item['thread_id'])).fetchone()
        if not row or row['status'] in {'cancelled','superseded'}: raise HTTPException(409,'卡片已失效')
        previous=json.loads(row['response'] or '{}')
        responses=previous.setdefault('cards',{})
        if card['id'] in responses:
            old=responses[card['id']]
            if all(old.get(key)==value for key,value in response.items()):
                return {'interaction':control.public_interaction(control.decode(row)),'accepted':True,'deduplicated':True}
            raise HTTPException(409,'此卡片已经回答')
        thread=db.execute('SELECT * FROM threads WHERE id=?',(item['thread_id'],)).fetchone()
        content=control.encode({'user_decision':{'interaction_id':item['id'],'card_id':card['id'],**({'action_id':action['id'],'label':action['label']} if action else {'answer':answer.strip()})},'untrusted_display_context':{'title':card['title'],'description':card.get('description','')}})
        agent=current_agent(thread)
        queued,created=control.enqueue(item['thread_id'],agent['id'],content,{'attachment_ids':[],'model_override':json.loads(thread['model_override'] or '{}')},submission_id,connection=db)
        response['queue_message_id']=queued['id']
        responses[card['id']]=response
        status='answered' if len(responses)==len(item['payload']['cards']) else 'pending'
        db.execute('UPDATE chat_interactions SET response=?,status=?,updated_at=? WHERE id=?',(control.encode(previous),status,now(),item['id']))
    control.conversation_runtime.notify()
    return {'interaction':control.public_interaction(control.get_interaction(item['thread_id'],item['id'])),'message':control.public_message(queued),'accepted':True,'deduplicated':not created}
