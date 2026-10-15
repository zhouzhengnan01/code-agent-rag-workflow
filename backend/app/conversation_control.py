"""Durable session messages and user interactions, independent of HTTP connections."""
import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from contextlib import nullcontext

from fastapi import HTTPException
from .db import connect, current_tenant, ensure_tenant, new_id, now, reset_tenant, tenant_ids, use_tenant

TERMINAL_RUNS = {'completed', 'failed', 'cancelled'}
WAITING_RUNS = {'waiting_for_input', 'waiting_for_approval', 'waiting_for_project'}

def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def submission(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', value):
        raise HTTPException(400, '必须提供有效 submission_id，重试时使用同一 ID')
    return value

def decode(row):
    if not row:
        return None
    item = dict(row)
    for key in ('payload', 'response', 'result'):
        if item.get(key):
            item[key] = json.loads(item[key])
    return item

def public_message(row):
    item = decode(row) if not isinstance(row, dict) else row
    payload = item.get('payload') or {}
    return {key: item.get(key) for key in ('id','thread_id','agent_id','submission_id','content','mode','status','run_status','turn_id','error','created_at','updated_at')} | {
        'attachment_ids': payload.get('attachment_ids', []),
        'retry_of': payload.get('retry_of'), 'retried_by': payload.get('retried_by'),
        'dismissed_at': payload.get('dismissed_at'),
    }

def get_message(thread_id, message_id):
    with connect() as db:
        row = db.execute('SELECT * FROM chat_queue_messages WHERE thread_id=? AND id=?', (thread_id, message_id)).fetchone()
    if not row:
        raise HTTPException(404, '会话消息不存在')
    return decode(row)

def messages(thread_id, submission_id=None):
    with connect() as db:
        if submission_id:
            rows = db.execute('SELECT * FROM chat_queue_messages WHERE thread_id=? AND submission_id=?', (thread_id, submission_id)).fetchall()
        else:
            rows = db.execute('SELECT * FROM chat_queue_messages WHERE thread_id=? ORDER BY created_at DESC,rowid DESC LIMIT 100', (thread_id,)).fetchall()
    return [public_message(row) for row in reversed(rows)]

def dismiss_failed_message(thread_id, message_id):
    """Hide a failed banner without deleting its audit record or stopping a turn."""
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM chat_queue_messages WHERE thread_id=? AND id=?', (thread_id, message_id)).fetchone()
        if not row:
            raise HTTPException(404, '会话消息不存在')
        if row['run_status'] != 'failed' or row['status'] not in {'consumed', 'failed'}:
            raise HTTPException(409, '只能删除已执行失败的提示；运行中、等待处理或成功的任务不能隐藏')
        item = decode(row)
        payload = item.get('payload') or {}
        if payload.get('dismissed_at') is not None:
            return item, False
        timestamp = now()
        payload['dismissed_at'] = timestamp
        db.execute('UPDATE chat_queue_messages SET payload=?,updated_at=? WHERE thread_id=? AND id=?', (encode(payload), timestamp, thread_id, message_id))
        saved = decode(db.execute('SELECT * FROM chat_queue_messages WHERE thread_id=? AND id=?', (thread_id, message_id)).fetchone())
    return saved, True

def enqueue(thread_id, agent_id, content, payload, submission_id, interrupt=False, connection=None):
    submission(submission_id)
    fingerprint = hashlib.sha256(encode({'agent_id':agent_id,'content':content,'payload':payload,'interrupt':interrupt}).encode()).hexdigest()
    timestamp = now()
    with (nullcontext(connection) if connection is not None else connect()) as db:
        if connection is None: db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT * FROM chat_queue_messages WHERE thread_id=? AND submission_id=?', (thread_id, submission_id)).fetchone()
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise HTTPException(409, '同一提交 ID 不能用于不同消息')
            return decode(previous), False
        if not db.execute('SELECT 1 FROM threads WHERE id=?', (thread_id,)).fetchone():
            raise HTTPException(404, '对话不存在')
        retry_of = payload.get('retry_of')
        retry_source = None
        if retry_of:
            retry_source = db.execute('SELECT * FROM chat_queue_messages WHERE thread_id=? AND id=?', (thread_id, retry_of)).fetchone()
            if not retry_source:
                raise HTTPException(404, '原失败任务不存在于当前对话')
            retry_payload = json.loads(retry_source['payload'] or '{}')
            if retry_payload.get('retried_by'):
                raise HTTPException(409, '该任务已经重试，请刷新状态；再次失败时请重试最新任务')
            if retry_source['run_status'] not in {'failed', 'cancelled'} and retry_source['status'] != 'failed':
                raise HTTPException(409, '只有失败或已取消的任务可以重试')
            if retry_source['content'] != content or retry_source['agent_id'] != agent_id or retry_payload.get('attachment_ids', []) != payload.get('attachment_ids', []):
                raise HTTPException(400, '重试必须保留原任务内容、智能体和附件')
        item = {'id':new_id('cqm'),'thread_id':thread_id,'agent_id':agent_id,'submission_id':submission_id,'fingerprint':fingerprint,'content':content,'payload':encode(payload),'mode':'interrupt' if interrupt else 'queue','created_at':timestamp,'updated_at':timestamp}
        db.execute('INSERT INTO chat_queue_messages(id,thread_id,agent_id,submission_id,fingerprint,content,payload,mode,created_at,updated_at) VALUES(:id,:thread_id,:agent_id,:submission_id,:fingerprint,:content,:payload,:mode,:created_at,:updated_at)', item)
        if retry_source:
            retry_payload['retried_by'] = item['id']
            db.execute('UPDATE chat_queue_messages SET payload=?,updated_at=? WHERE id=?', (encode(retry_payload), timestamp, retry_of))
        saved=decode(db.execute('SELECT * FROM chat_queue_messages WHERE id=?',(item['id'],)).fetchone())
    return saved, True

def public_interaction(row):
    item = decode(row) if not isinstance(row, dict) else row
    return {key:item.get(key) for key in ('id','thread_id','turn_id','queue_message_id','kind','status','question','payload','response','submission_id','error','created_at','updated_at')}

def get_interaction(thread_id, interaction_id):
    with connect() as db:
        row = db.execute('SELECT * FROM chat_interactions WHERE thread_id=? AND id=?', (thread_id,interaction_id)).fetchone()
    if not row:
        raise HTTPException(404, '交互不存在')
    return decode(row)

def interactions(thread_id):
    sync_approvals(thread_id)
    with connect() as db:
        rows=db.execute('SELECT * FROM chat_interactions WHERE thread_id=? ORDER BY created_at,rowid', (thread_id,)).fetchall()
    return [public_interaction(row) for row in rows]

def create_interaction(thread_id, turn_id, kind, question, payload, queue_message_id=None, approval_id=None, tool_call_id=None):
    timestamp=now()
    with connect() as db:
        if approval_id:
            old=db.execute('SELECT * FROM chat_interactions WHERE approval_id=?', (approval_id,)).fetchone()
        elif tool_call_id:
            old=db.execute('SELECT * FROM chat_interactions WHERE thread_id=? AND turn_id=? AND tool_call_id=?', (thread_id,turn_id,tool_call_id)).fetchone()
        else:
            old=db.execute("SELECT * FROM chat_interactions WHERE thread_id=? AND turn_id=? AND kind=?", (thread_id,turn_id,kind)).fetchone()
        if old:
            return decode(old)
        item={'id':new_id('int'),'thread_id':thread_id,'turn_id':turn_id,'kind':kind,'question':question,'payload':encode(payload),'queue_message_id':queue_message_id,'approval_id':approval_id,'tool_call_id':tool_call_id,'created_at':timestamp,'updated_at':timestamp}
        db.execute('INSERT INTO chat_interactions(id,thread_id,turn_id,kind,question,payload,queue_message_id,approval_id,tool_call_id,created_at,updated_at) VALUES(:id,:thread_id,:turn_id,:kind,:question,:payload,:queue_message_id,:approval_id,:tool_call_id,:created_at,:updated_at)',item)
    return get_interaction(thread_id,item['id'])

def sync_approvals(thread_id):
    with connect() as db:
        rows=db.execute("SELECT a.*,q.id AS queue_message_id FROM approvals a LEFT JOIN chat_queue_messages q ON q.turn_id=a.turn_id WHERE a.thread_id=? AND a.status='pending' AND a.resumable=1 AND a.tool_call_id IS NOT NULL AND EXISTS(SELECT 1 FROM turn_checkpoints c WHERE c.turn_id=a.turn_id AND c.status='waiting')", (thread_id,)).fetchall()
    for row in rows:
        args=json.loads(row['arguments'])
        options=[{'id':f'option_{index}','label':str(option.get('label','')),'description':str(option.get('description',''))} for index,option in enumerate(args.get('options',[])[:4]) if isinstance(option,dict)]
        kind='question' if row['tool_name']=='ask_user' else 'tool_approval'
        create_interaction(thread_id,row['turn_id'],kind,args.get('question') or f"允许智能体执行 {row['tool_name']}？",{'options':options,'tool_name':row['tool_name'],'arguments':args,'resumable':bool(row['resumable'])},row['queue_message_id'],row['id'],row['tool_call_id'])
    with connect() as db:
        db.execute("UPDATE chat_interactions SET status=CASE WHEN (SELECT status FROM approvals a WHERE a.id=approval_id)='cancelled' THEN 'cancelled' ELSE 'answered' END,updated_at=? WHERE thread_id=? AND approval_id IS NOT NULL AND status='pending' AND EXISTS(SELECT 1 FROM approvals a WHERE a.id=approval_id AND a.status!='pending')",(now(),thread_id))

def claim_answer(thread_id, interaction_id, response, submission_id):
    submission(submission_id)
    serialized=encode(response)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM chat_interactions WHERE thread_id=? AND id=?',(thread_id,interaction_id)).fetchone()
        if not row: raise HTTPException(404,'交互不存在')
        if row['status']!='pending':
            if row['submission_id']==submission_id and row['response']==serialized:
                return decode(row),False
            raise HTTPException(409,'该交互已回答或失效，请刷新会话状态')
        changed=db.execute("UPDATE chat_interactions SET status='submitting',response=?,submission_id=?,runner_id=NULL,updated_at=? WHERE id=? AND status='pending'",(serialized,submission_id,now(),interaction_id)).rowcount
        if not changed: raise HTTPException(409,'回答正在处理')
    return get_interaction(thread_id,interaction_id),True

def finish_interaction(interaction_id,status='answered',error=None):
    with connect() as db:
        db.execute('UPDATE chat_interactions SET status=?,error=?,runner_id=NULL,updated_at=? WHERE id=?',(status,error,now(),interaction_id))

def finish_message(message_id,run_status,result=None,error=None):
    with connect() as db:
        db.execute("UPDATE chat_queue_messages SET status=CASE WHEN status='pending' AND ?='cancelled' THEN 'cancelled' ELSE 'consumed' END,run_status=?,result=?,error=?,runner_id=NULL,updated_at=? WHERE id=?",(run_status,run_status,encode(result) if result else None,error,now(),message_id))

def cancel_waiting(thread_id,reason='用户已停止此任务'):
    with connect() as db:
        rows=db.execute("SELECT id,turn_id FROM chat_queue_messages WHERE thread_id=? AND run_status IN ('waiting_for_input','waiting_for_approval','waiting_for_project') UNION SELECT NULL AS id,turn_id FROM turn_checkpoints WHERE thread_id=? AND status='waiting' AND turn_id NOT IN (SELECT turn_id FROM chat_queue_messages WHERE thread_id=? AND turn_id IS NOT NULL)",(thread_id,thread_id,thread_id)).fetchall()
        for row in rows:
            db.execute("UPDATE chat_queue_messages SET run_status='cancelled',error=?,updated_at=? WHERE id=?",(reason,now(),row['id']))
            db.execute("UPDATE chat_interactions SET status='cancelled',updated_at=? WHERE thread_id=? AND turn_id=? AND status IN ('pending','submitting')",(now(),thread_id,row['turn_id']))
            db.execute("UPDATE approvals SET status='cancelled',resolution=?,resolved_at=? WHERE thread_id=? AND turn_id=? AND status='pending'",(reason,now(),thread_id,row['turn_id']))
            db.execute("UPDATE turn_checkpoints SET status='cancelled',updated_at=? WHERE turn_id=? AND status IN ('waiting','resuming')",(now(),row['turn_id']))
            db.execute("UPDATE agent_runs SET status='cancelled',updated_at=? WHERE turn_id=? AND status IN ('waiting','running')",(now(),row['turn_id']))
        if rows: db.execute("UPDATE threads SET status='idle',updated_at=? WHERE id=?",(now(),thread_id))
    return bool(rows)

class ConversationRuntime:
    def __init__(self):
        self.runner_id=uuid.uuid4().hex
        self.running={}
        self.loop_task=None
        self.stopping=False
        self.wakeup=asyncio.Event()
        self.execute=None
        self.resume=None

    def tenants(self):
        return ([] if os.getenv('CODEZZN_LEGACY_OWNER_GITHUB_ID','').strip() else [None])+tenant_ids()

    async def start(self,execute,resume):
        if self.loop_task and not self.loop_task.done():
            raise RuntimeError('Conversation runtime is already running')
        self.wakeup=asyncio.Event()
        self.execute,self.resume=execute,resume
        self.stopping=False
        for tenant in self.tenants():
            token=use_tenant(tenant)
            try:
                if tenant: ensure_tenant(tenant)
                with connect() as db:
                    stranded=db.execute("SELECT id,thread_id,turn_id,payload FROM chat_queue_messages WHERE run_status='running'").fetchall()
                    for row in stranded:
                        from .agent import SIDE_EFFECT_TOOLS
                        saved=db.execute("SELECT state FROM agent_runs WHERE thread_id=? AND turn_id=? AND status IN ('running','waiting','recovering') ORDER BY updated_at DESC LIMIT 1",(row['thread_id'],row['turn_id'])).fetchone()
                        try: saved_state=json.loads(saved['state']) if saved else {}
                        except (ValueError,TypeError): saved_state={}
                        valid=isinstance(saved_state,dict) and (isinstance(saved_state.get('messages'),list) or (saved_state.get('mode')=='responses' and ('next_input' in saved_state or 'previous_response_id' in saved_state)))
                        uncertain=db.execute("SELECT tool_name FROM tool_executions WHERE turn_id=? AND status IN ('running','failed')",(row['turn_id'],)).fetchall()
                        ambiguous=any(tool['tool_name'] in SIDE_EFFECT_TOOLS for tool in uncertain)
                        if valid and not ambiguous:
                            waiting=db.execute("SELECT kind FROM chat_interactions WHERE thread_id=? AND turn_id=? AND status='pending' AND kind IN ('question','tool_approval','project_confirmation') ORDER BY created_at DESC LIMIT 1",(row['thread_id'],row['turn_id'])).fetchone()
                            if waiting:
                                run_status={'question':'waiting_for_input','tool_approval':'waiting_for_approval','project_confirmation':'waiting_for_project'}[waiting['kind']]
                                db.execute("UPDATE chat_queue_messages SET status='consumed',run_status=?,runner_id=NULL,error=NULL,updated_at=? WHERE id=?",(run_status,now(),row['id']))
                                db.execute("UPDATE threads SET status=?,updated_at=? WHERE id=?",(run_status,now(),row['thread_id']))
                            else:
                                recovered_payload=json.loads(row['payload'] or '{}')
                                recovered_payload['_recovering']=True
                                db.execute("UPDATE chat_queue_messages SET status='pending',run_status='pending',payload=?,runner_id=NULL,error=NULL,updated_at=? WHERE id=?",(encode(recovered_payload),now(),row['id']))
                                db.execute("UPDATE agent_runs SET status='recovering',updated_at=? WHERE thread_id=? AND turn_id=? AND status IN ('running','waiting')",(now(),row['thread_id'],row['turn_id']))
                                db.execute("UPDATE threads SET status='idle',updated_at=? WHERE id=?",(now(),row['thread_id']))
                            continue
                        error='服务重启中断了执行；已生成产物仍可查看，请提交新的继续任务'
                        if ambiguous: error='执行中断时存在结果不确定的副作用工具；为避免重复写入/提交，不自动重放，请先检查外部状态后再继续'
                        db.execute("UPDATE chat_queue_messages SET status='consumed',run_status='failed',runner_id=NULL,error=?,updated_at=? WHERE id=?",(error,now(),row['id']))
                        db.execute("UPDATE agent_runs SET status='failed',error=?,updated_at=? WHERE turn_id=? AND status IN ('running','recovering')",(error,now(),row['turn_id']))
                        db.execute("UPDATE threads SET status='error',updated_at=? WHERE id=? AND status='running'",(now(),row['thread_id']))
                    db.execute("UPDATE chat_interactions SET runner_id=NULL WHERE status='submitting'")
                    db.execute("UPDATE chat_interactions SET status='answered',error='回答已接收，服务重启中断了后续执行',updated_at=? WHERE status='submitting' AND approval_id IS NOT NULL AND EXISTS(SELECT 1 FROM approvals a WHERE a.id=approval_id AND a.status!='pending')",(now(),))
                    db.execute("UPDATE turn_checkpoints SET status='failed',updated_at=? WHERE status='resuming' AND turn_id IN (SELECT turn_id FROM chat_interactions WHERE status='answered' AND error IS NOT NULL)",(now(),))
            finally: reset_tenant(token)
        self.loop_task=asyncio.create_task(self._loop())

    async def close(self):
        self.stopping=True
        self.wakeup.set()
        if self.loop_task: await self.loop_task
        active=[item['task'] for item in self.running.values()]
        for task in active: task.cancel()
        await asyncio.gather(*active,return_exceptions=True)
        self.running.clear()
        self.loop_task=None

    async def cancel(self,thread_id):
        item=self.running.get((current_tenant(),thread_id))
        if item and not item['task'].done():
            item['task'].cancel()
            await asyncio.gather(item['task'],return_exceptions=True)
            return True
        return cancel_waiting(thread_id)

    def notify(self): self.wakeup.set()

    async def _run(self,tenant,thread_id,item,answer=False):
        token=use_tenant(tenant)
        try:
            await (self.resume(item) if answer else self.execute(item))
        except asyncio.CancelledError:
            if self.stopping:
                # Keep running records for restart recovery. User cancellation
                # below remains terminal and explicitly revokes pending actions.
                raise
            if answer:
                finish_interaction(item['id'],'cancelled','用户已停止后续执行')
                if item.get('queue_message_id'): finish_message(item['queue_message_id'],'cancelled')
            else: finish_message(item['id'],'cancelled',error='执行已停止；已完成的操作和文件保留')
            with connect() as db:
                db.execute("UPDATE threads SET status='idle',updated_at=? WHERE id=?",(now(),thread_id))
                turn_id=item.get('turn_id')
                if not turn_id and not answer:
                    saved=db.execute('SELECT turn_id FROM chat_queue_messages WHERE id=?',(item['id'],)).fetchone()
                    turn_id=saved['turn_id'] if saved else None
                if turn_id:
                    db.execute("UPDATE agent_runs SET status='cancelled',updated_at=? WHERE turn_id=? AND status IN ('running','waiting')",(now(),turn_id))
                    db.execute("UPDATE turn_checkpoints SET status='cancelled',updated_at=? WHERE turn_id=? AND status IN ('waiting','resuming')",(now(),turn_id))
                    db.execute("UPDATE approvals SET status='cancelled',resolution='执行已停止',resolved_at=? WHERE turn_id=? AND status='pending'",(now(),turn_id))
                    db.execute("UPDATE chat_interactions SET status='cancelled',updated_at=? WHERE turn_id=? AND status IN ('pending','submitting')",(now(),turn_id))
        except Exception as error:
            if answer:
                latest=get_interaction(thread_id,item['id'])
                if latest['status']=='pending':
                    finish_interaction(item['id'],'pending',str(error)[:1200])
                    waiting='waiting_for_approval' if item['kind']=='tool_approval' else 'waiting_for_input'
                    with connect() as db: db.execute('UPDATE threads SET status=?,updated_at=? WHERE id=?',(waiting,now(),thread_id))
                    return
                finish_interaction(item['id'],'answered',str(error)[:1200])
                if item.get('queue_message_id'): finish_message(item['queue_message_id'],'failed',error=str(error)[:1200])
            else: finish_message(item['id'],'failed',error=str(error)[:1200])
            with connect() as db: db.execute("UPDATE threads SET status='error',updated_at=? WHERE id=?",(now(),thread_id))
        finally:
            reset_tenant(token)
            self.running.pop((tenant,thread_id),None)
            self.notify()

    async def _loop(self):
        while not self.stopping:
            for tenant in self.tenants():
                token=use_tenant(tenant)
                try:
                    if tenant: ensure_tenant(tenant)
                    with connect() as db:
                        answers=db.execute("SELECT i.* FROM chat_interactions i JOIN threads t ON t.id=i.thread_id WHERE i.status='submitting' AND i.runner_id IS NULL AND t.status!='running' ORDER BY i.created_at,i.rowid").fetchall()
                        pending=db.execute("SELECT q.* FROM chat_queue_messages q JOIN threads t ON t.id=q.thread_id WHERE q.status='pending' AND t.status IN ('idle','error') ORDER BY CASE WHEN q.mode='interrupt' THEN 0 ELSE 1 END,q.created_at,q.rowid").fetchall()
                    for row,answer in [*( (row,True) for row in answers),*((row,False) for row in pending)]:
                        key=(tenant,row['thread_id'])
                        if key in self.running or len(self.running)>=8: continue
                        with connect() as db:
                            if answer:
                                claimed=db.execute("UPDATE chat_interactions SET runner_id=?,updated_at=? WHERE id=? AND status='submitting' AND runner_id IS NULL",(self.runner_id,now(),row['id'])).rowcount
                            else:
                                claimed=db.execute("UPDATE chat_queue_messages SET status='dispatching',run_status='running',runner_id=?,updated_at=? WHERE id=? AND status='pending' AND NOT EXISTS(SELECT 1 FROM chat_queue_messages a WHERE a.thread_id=? AND a.id!=? AND a.run_status IN ('running','waiting_for_input','waiting_for_approval','waiting_for_project'))",(self.runner_id,now(),row['id'],row['thread_id'],row['id'])).rowcount
                                if claimed: db.execute("UPDATE threads SET status='running',updated_at=? WHERE id=? AND status IN ('idle','error')",(now(),row['thread_id']))
                        if claimed:
                            task=asyncio.create_task(self._run(tenant,row['thread_id'],decode(row),answer))
                            self.running[key]={'task':task,'id':row['id'],'answer':answer}
                except Exception:
                    logging.getLogger(__name__).exception('Conversation dispatcher could not scan a tenant; retrying')
                finally: reset_tenant(token)
            self.wakeup.clear()
            if not self.stopping:
                try: await asyncio.wait_for(self.wakeup.wait(),timeout=.5)
                except TimeoutError: pass

conversation_runtime=ConversationRuntime()
