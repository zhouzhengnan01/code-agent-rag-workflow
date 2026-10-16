const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('retry removes the original failure banner only after the new submission is accepted', async () => {
  const app = workbench((url, options) => {
    const payload = JSON.parse(options.body);
    return { message: { id: 'new_retry', content: payload.content, agent_id: payload.agent_id,
      attachment_ids: payload.attachment_ids, retry_of: payload.retry_of, status: 'pending', run_status: 'pending' } };
  });
  app.run("state.chatQueue=[{id:'old_failure',content:'地图问题',agent_id:'a',status:'consumed',run_status:'failed',error:'旧网络错误'}];renderChatQueue();");
  assert.match(app.nodes.get('#chatQueue').innerHTML, /旧网络错误/);
  await app.context.retryQueuedChatMessage({ dataset: { messageId: 'old_failure' }, disabled: false });
  assert.equal(JSON.parse(app.calls[0].options.body).retry_of, 'old_failure');
  assert.doesNotMatch(app.nodes.get('#chatQueue').innerHTML, /旧网络错误|执行失败/);
  assert.match(app.nodes.get('#chatQueue').innerHTML, /待执行/);
  assert.equal(app.run('state.chatQueue[0].error'), '旧网络错误');
  assert.equal(app.run('state.chatQueue[0].retried_by'), 'new_retry');
  app.run("state.chatQueue[1].status='consumed';state.chatQueue[1].run_status='running';renderChatQueue();");
  assert.equal(app.nodes.get('#chatQueue').hidden, true);
  app.run("state.chatQueue[1].run_status='failed';state.chatQueue[1].error='新的错误';renderChatQueue();");
  assert.match(app.nodes.get('#chatQueue').innerHTML, /新的错误/);
  assert.doesNotMatch(app.nodes.get('#chatQueue').innerHTML, /旧网络错误/);
});

test('persisted retry links survive reload even when the retry is outside the queue window', () => {
  const app = workbench();
  app.run("state.chatQueue=[{id:'old',content:'question',status:'consumed',run_status:'failed',error:'old error',retried_by:'new'}];renderChatQueue();");
  assert.equal(app.nodes.get('#chatQueue').hidden, true);
});

test('legacy retries hide superseded failures but unrelated tasks retain their error', () => {
  const app = workbench();
  app.run("state.chatQueue=[{id:'old',content:'question',agent_id:'a',status:'consumed',run_status:'failed',error:'old error'}, {id:'new',content:'question',agent_id:'a',status:'consumed',run_status:'running'}];renderChatQueue();");
  assert.equal(app.nodes.get('#chatQueue').hidden, true);
  app.run("state.chatQueue[1].content='different question';renderChatQueue();");
  assert.match(app.nodes.get('#chatQueue').innerHTML, /old error/);
  app.run("state.chatQueue[1].content='question';state.chatQueue[1].attachment_ids=['different-file'];renderChatQueue();");
  assert.match(app.nodes.get('#chatQueue').innerHTML, /old error/);
});

test('an unconfirmed retry leaves the original failure visible', () => {
  const app = workbench();
  app.run("state.chatQueue=[{id:'old',content:'question',status:'consumed',run_status:'failed',error:'old error'}];state.chatUnknownSubmission={submission_id:'unknown',payload:{retry_of:'old'}};renderChatQueue();");
  assert.match(app.nodes.get('#chatQueue').innerHTML, /old error/);
});

function workbench(responder = () => ({})) {
  const calls = [];
  const nodes = new Map();
  for (const selector of ['#nav', '#chatInput', '#chatAgent', '#chatModel', '#sendBtn', '#attachBtn', '#chatAttachments', '#chatComposerError', '#toastRoot', '#chatHistorySubmenu', '#chatQueue', '#chatQueueHint', '#stopBtn', '#interruptBtn', '#chatInteractionDock']) {
    nodes.set(selector, { value: '', innerHTML: '', textContent: '', disabled: false, hidden: false, style: {}, setAttribute(name,value) { this[name] = value; } });
  }
  const context = vm.createContext({
    window: { addEventListener() {}, setTimeout() {} },
    document: { addEventListener() {}, querySelector: selector => nodes.get(selector), querySelectorAll: () => [], getElementById: id => nodes.get(`#${id}`) },
    localStorage: { codezznKey: 'synthetic-test-key' }, FormData, URL,
    AbortController, crypto: require('node:crypto').webcrypto, setTimeout: () => 1, clearTimeout() {},
    richText: value => String(value ?? ''),
    fetch: async (url, options = {}) => {
      calls.push({ url, options });
      return { ok: true, json: async () => responder(url, options), blob: async () => new Blob(['synthetic attachment']) };
    },
  });
  const source = fs.readFileSync(path.join(__dirname, '../web/workbench.js'), 'utf8');
  vm.runInContext(source.slice(0, source.lastIndexOf('state.page = pages.some')), context);
  vm.runInContext("state.page='chat';state.thread='thr_test';state.currentThread={id:'thr_test',model_override:{}};state.cache.agents=[{id:'a',model:'original'}];", context);
  nodes.get('#chatAgent').value = 'a';
  return { context, nodes, calls, run: code => vm.runInContext(code, context) };
}

test('sidebar names and history chevron share a single accessible button', () => {
  const app = workbench();
  app.run('nav();');
  const html = app.nodes.get('#nav').innerHTML;
  assert.match(html, /aria-label="Agent"/);
  assert.doesNotMatch(html, /概览|对话调试|nav-chat-toggle|nav-chat-row/);
  const button = html.match(/<button\b[^>]*id="chatHistoryToggle"[\s\S]*?<\/button>/)?.[0];
  assert.ok(button);
  assert.match(button, /onclick="openChatHistory\(\)"/);
  assert.match(button, /aria-controls="chatHistorySubmenu" aria-expanded="true"/);
  assert.match(button, /<span class="nav-label">历史<\/span>/);
  assert.match(button, /nav-history-chevron/);
  assert.equal((button.match(/<button\b/g) || []).length, 1);
});

test('unified history button collapses and reopens without navigating away from chat', () => {
  const app = workbench();
  app.context.openChatHistory();
  assert.equal(app.run('state.chatHistoryOpen'), false);
  assert.match(app.nodes.get('#nav').innerHTML, /aria-expanded="false"/);
  assert.match(app.nodes.get('#nav').innerHTML, /id="chatHistorySubmenu" class="chat-history-submenu" hidden/);
  app.context.openChatHistory();
  assert.equal(app.run('state.chatHistoryOpen'), true);
  assert.equal(app.run('state.page'), 'chat');
});

test('history button opens chat from another page while honoring navigation guards', () => {
  const app = workbench();
  app.run("state.page='dashboard';state.chatHistoryOpen=false;go=()=>{state.page='chat';return 'navigated';};");
  assert.equal(app.context.openChatHistory(), 'navigated');
  assert.equal(app.run('state.chatHistoryOpen'), true);
  app.run("state.page='dashboard';state.chatHistoryOpen=false;go=()=> 'blocked';");
  assert.equal(app.context.openChatHistory(), 'blocked');
  assert.equal(app.run('state.page'), 'dashboard');
  assert.equal(app.run('state.chatHistoryOpen'), false);
});

test('model choice updates this thread while leaving the Agent default untouched', async () => {
  const choice = { provider_id: 'p', model: 'chosen' };
  const app = workbench(() => ({ id: 'thr_test', model_override: choice }));
  app.run("state.chatModels=[{provider_id:'p',provider_name:'Local',model:'chosen'}];");
  await app.context.changeChatModel(encodeURIComponent(JSON.stringify(choice)));
  assert.equal(app.calls[0].url, '/api/threads/thr_test');
  assert.deepEqual(JSON.parse(app.calls[0].options.body), { model_override: choice });
  assert.equal(app.run('state.currentThread.model_override.model'), 'chosen');
  assert.equal(app.run('state.cache.agents[0].model'), 'original');
  assert.equal(app.run('state.modelSaving'), false);
});

test('disabled or removed selected model stays visible instead of appearing to revert', () => {
  const app = workbench();
  app.run("state.currentThread.model_override={provider_id:'disabled',model:'old-model'};");
  assert.match(app.context.chatModelOptions({ model: 'original' }), /selected disabled>old-model · 暂不可用/);
});

test('running composer accepts queued messages and attachments while locking model and Agent', () => {
  const app = workbench();
  app.context.updateComposerControls();
  assert.equal(app.nodes.get('#sendBtn').disabled, true);
  app.run("state.chatAttachments=[{id:'att_0123456789abcdef',status:'ready'}];");
  app.context.updateComposerControls();
  assert.equal(app.nodes.get('#sendBtn').disabled, false);
  app.run('state.activeTurn={};');
  app.context.updateComposerControls();
  assert.equal(app.nodes.get('#sendBtn').disabled, false);
  assert.equal(app.nodes.get('#chatModel').disabled, true);
  assert.equal(app.nodes.get('#attachBtn').disabled, false);
  assert.equal(app.nodes.get('#chatInput').disabled, false);
  assert.equal(app.nodes.get('#chatAgent').disabled, true);
  assert.equal(app.nodes.get('#stopBtn').hidden, false);
  assert.equal(app.nodes.get('#interruptBtn').disabled, false);
});

test('upload sends multipart with authentication and stores ready metadata in the thread draft', async () => {
  const app = workbench(() => ({ id: 'att_0123456789abcdef', name: 'notes.txt', size: 4, kind: 'document' }));
  await app.context.uploadChatAttachments([new File(['note'], 'notes.txt', { type: 'text/plain' })]);
  assert.equal(app.calls[0].url, '/api/chat/attachments');
  assert.equal(app.calls[0].options.body.get('file').name, 'notes.txt');
  assert.equal(app.calls[0].options.headers['X-Codezzn-Key'], 'synthetic-test-key');
  assert.equal(app.calls[0].options.headers['Content-Type'], undefined);
  assert.equal(app.run('state.chatDrafts.thr_test.attachments[0].status'), 'ready');
});

test('upload failure remains removable and does not enable an empty send', async () => {
  const app = workbench();
  app.context.fetch = async () => ({ ok: false, status: 415, json: async () => ({ detail: 'Unsupported format' }) });
  await app.context.uploadChatAttachments([new File(['bad'], 'unsupported.zip')]);
  assert.equal(app.run('state.chatAttachments[0].status'), 'failed');
  assert.equal(app.nodes.get('#sendBtn').disabled, true);
  app.context.removeChatAttachment(0);
  assert.equal(app.run('state.chatAttachments.length'), 0);
});

test('newly materialized thread inherits the unsent text and attachment draft', async () => {
  const app = workbench(() => ({ id: 'thr_created', name: 'New', model_override: {} }));
  app.run("state.thread=null;state.chatDrafts.new={content:'unsent',attachments:[{id:'att_0123456789abcdef'}]};");
  assert.equal(await app.context.ensureChatThread('a'), 'thr_created');
  assert.equal(app.run('state.chatDrafts.thr_created.content'), 'unsent');
  assert.equal(app.run('state.chatDrafts.thr_created.attachments[0].id'), 'att_0123456789abcdef');
  assert.equal(app.run('state.chatDrafts.new'), undefined);
});

test('private attachment fetch carries the key in a header, never a URL', async () => {
  const app = workbench();
  await app.context.fetchChatAttachment('att_0123456789abcdef');
  assert.equal(app.calls[0].url, '/api/chat/attachments/att_0123456789abcdef/download');
  assert.equal(app.calls[0].options.headers['X-Codezzn-Key'], 'synthetic-test-key');
  await assert.rejects(app.context.fetchChatAttachment('../secret'), /附件不存在/);
  assert.equal(app.calls.length, 1);
});

test('consumed approval refreshes after a failed continuation instead of inviting resubmission', async () => {
  const app = workbench();
  let posts = 0, reloads = 0;
  app.context.fetch = async (url, options = {}) => {
    if (options.method === 'POST') { posts++; return { ok: false, status: 502, json: async () => ({ detail: 'resume failed' }) }; }
    return { ok: true, json: async () => ({ status: 'approved', error: 'model request failed' }) };
  };
  app.context.loadPage = async () => { reloads++; };
  app.context.refreshSidebarThreads = () => {};
  await app.context.resolveApproval('approval_test', 'approved', '重新截图');
  assert.equal(posts, 1);
  assert.equal(reloads, 1);
  assert.equal(app.run('state.approvalPending'), false);
  assert.match(app.nodes.get('#toastRoot').innerHTML, /回答已接收/);
});

test('artifact previews use authenticated local downloads and reject arbitrary URLs', async () => {
  const app = workbench();
  const url = '/api/threads/thr_0123456789abcdef/artifacts/art_0123456789abcdef/download';
  await app.context.fetchArtifactFile(url);
  assert.equal(app.calls[0].options.headers['X-Codezzn-Key'], 'synthetic-test-key');
  await assert.rejects(app.context.fetchArtifactFile('https://example.com/file.png'), /下载地址无效/);
  assert.match(app.context.artifactOutputHtml({ name: 'capture.png', previewable: true, download_url: url }), /data-artifact-preview/);
});

test('unknown approval state keeps the old choices locked after a network failure', async () => {
  const app = workbench();
  const button = { disabled: false };
  const heading = { textContent: '选择下一步' };
  let inserted = '', requests = 0;
  app.context.document.getElementById = () => ({
    querySelectorAll: () => [button],
    querySelector: selector => selector === '.turn-content'
      ? { insertAdjacentHTML: (_position, html) => { inserted = html; } }
      : heading,
  });
  app.context.fetch = async () => { requests++; throw new Error('network disconnected'); };
  app.context.refreshSidebarThreads = () => {};
  await app.context.resolveApproval('approval_test', 'approved', '重新截图');
  assert.equal(requests, 2);
  assert.equal(button.disabled, true);
  assert.equal(heading.textContent, '提交结果尚未确认');
  assert.match(inserted, /刷新会话状态/);
  assert.equal(app.run('state.approvalPending'), false);
});

test('ordinary chat dispatches one durable queue submission without intent or HTTP streaming', async () => {
  const app = workbench((url, options) => ({ message: { id: 'queue_1', status: 'pending', run_status: 'pending', content: JSON.parse(options.body).content } }));
  app.nodes.get('#chatInput').value = '你是谁？';
  await app.context.sendMessage();
  assert.equal(app.calls.length, 1);
  assert.equal(app.calls[0].url, '/api/threads/thr_test/queue');
  const payload = JSON.parse(app.calls[0].options.body);
  assert.equal(payload.content, '你是谁？');
  assert.equal(payload.interrupt, false);
  assert.match(payload.submission_id, /^[0-9a-f-]{36}$/);
  assert.equal(app.nodes.get('#chatInput').value, '');
  assert.equal(app.run('state.chatQueue[0].id'), 'queue_1');
});

test('Enter semantics queue during execution, explicit adjustment requests an interrupt', async () => {
  const app = workbench((url, options) => ({ message: { id: 'queue_' + JSON.parse(options.body).submission_id, status: 'pending', run_status: 'pending' } }));
  app.run("state.chatQueue=[{id:'old',turn_id:'turn_old',status:'consumed',run_status:'running'}];syncActiveChatTurn();");
  app.nodes.get('#chatInput').value = '接着检查文档';
  await app.context.sendMessage();
  assert.equal(JSON.parse(app.calls[0].options.body).interrupt, false);
  app.nodes.get('#chatInput').value = '先修复这个错误';
  await app.context.sendMessage({ interrupt: true });
  assert.equal(JSON.parse(app.calls[1].options.body).interrupt, true);
  assert.equal(app.calls.some(call => call.options.method === 'DELETE'), false);
});

test('selected project defaults to save without a browser-only project confirmation', async () => {
  const app = workbench(() => ({ message: { id: 'queue_1', status: 'pending' } }));
  app.run("state.activeProjectId='project_1';");
  app.nodes.get('#chatInput').value = '写一个排序程序';
  await app.context.sendMessage();
  const payload = JSON.parse(app.calls[0].options.body);
  assert.equal(payload.project_id, 'project_1');
  assert.equal(payload.save_to_project, true);
  assert.equal(app.run('state.pendingProjectTurn'), null);
});

test('lost queue response is confirmed by submission id without executing twice', async () => {
  let submission;
  const app = workbench();
  app.context.fetch = async (url, options = {}) => {
    app.calls.push({ url, options });
    if (options.method === 'POST') { submission = JSON.parse(options.body).submission_id; throw new Error('response lost'); }
    return { ok: true, json: async () => ({ data: [{ id: 'accepted', submission_id: submission, status: 'pending' }] }) };
  };
  app.nodes.get('#chatInput').value = '整理资料';
  await app.context.sendMessage();
  assert.equal(app.calls.filter(call => call.options.method === 'POST').length, 1);
  assert.equal(app.calls[1].url, `/api/threads/thr_test/queue?submission_id=${submission}`);
  assert.equal(app.run('state.chatUnknownSubmission'), null);
  assert.equal(app.nodes.get('#chatInput').value, '');
});

test('uncertain queue submission preserves draft and locks resubmission until confirmation', async () => {
  const app = workbench();
  app.context.fetch = async (url, options = {}) => { app.calls.push({ url, options }); throw new Error('offline'); };
  app.nodes.get('#chatInput').value = '不能重复执行';
  await app.context.sendMessage();
  assert.equal(app.nodes.get('#chatInput').value, '不能重复执行');
  assert.equal(app.nodes.get('#sendBtn').disabled, true);
  await app.context.sendMessage();
  assert.equal(app.calls.filter(call => call.options.method === 'POST').length, 1);
  const submission = app.run('state.chatUnknownSubmission.submission_id');
  app.context.fetch = async () => ({ ok: true, json: async () => ({ data: [{ id: 'confirmed', submission_id: submission, status: 'pending' }] }) });
  app.nodes.get('#chatInput').value = '刷新期间新写的草稿';
  await app.context.refreshUnknownChatSubmission();
  assert.equal(app.run('state.chatUnknownSubmission'), null);
  assert.equal(app.nodes.get('#chatInput').value, '刷新期间新写的草稿');
});

test('stop is an explicit backend cancellation and failure does not claim it stopped', async () => {
  const app = workbench();
  app.context.fetch = async (url, options = {}) => { app.calls.push({ url, options }); throw new Error('offline'); };
  app.run("state.activeTurn={turn_id:'turn_1',controller:{abort(){throw Error('must not abort transport')}}};");
  await app.context.stopGeneration();
  assert.equal(app.calls[0].url, '/api/threads/thr_test/turns/active');
  assert.equal(app.calls[0].options.method, 'DELETE');
  assert.equal(app.run('state.activeTurn.turn_id'), 'turn_1');
  assert.equal(app.run('state.chatStopPending'), false);
  assert.match(app.nodes.get('#toastRoot').innerHTML, /停止失败/);
});

test('waiting cards block normal queue dispatch mode but do not disable composing', () => {
  const app = workbench();
  app.run("state.chatInteractions=[{id:'question_1',kind:'question',status:'pending',turn_id:'turn_1'}];syncActiveChatTurn();");
  app.nodes.get('#chatInput').value = '这条只排队，不充当审批回答';
  app.context.updateComposerControls();
  assert.equal(app.nodes.get('#chatInput').disabled, false);
  assert.equal(app.nodes.get('#sendBtn').disabled, false);
  assert.equal(app.nodes.get('#chatAgent').disabled, true);
  assert.match(app.nodes.get('#chatQueueHint').textContent, /Enter 排队/);
});

test('interaction answer submits once and returns immediately in submitting state', async () => {
  const app = workbench(() => ({ accepted: true, interaction: { id: 'int_1', kind: 'question', status: 'submitting', turn_id: 'turn_1' } }));
  app.run("state.chatInteractions=[{id:'int_1',kind:'question',status:'pending',payload:{options:[{id:'option_0',label:'继续'}]}}];");
  const button = { dataset: { interactionId: 'int_1', optionId: 'option_0' }, disabled: false };
  await app.context.answerChatOption(button);
  await app.context.answerChatOption(button);
  assert.equal(app.calls.length, 1);
  assert.equal(app.calls[0].url, '/api/threads/thr_test/interactions/int_1/answer');
  assert.equal(JSON.parse(app.calls[0].options.body).option_id, 'option_0');
  assert.equal(app.run('state.chatInteractions[0].status'), 'submitting');
});

test('decision cards remember individual answers while other cards stay selectable', () => {
  const app = workbench();
  const html = app.context.chatInteractionHtml({ id: 'int_1', kind: 'decision_cards', status: 'pending', payload: { cards: [{ id: 'one', kind: 'idea', title: '方案一', actions: [{ id: 'go', label: '执行一' }] }, { id: 'two', kind: 'risk', title: '风险', actions: [{ id: 'check', label: '检查' }] }] }, response: { cards: { one: { action_id: 'go' } } } });
  assert.match(html, /data-card-id="one"[^>]*disabled/);
  assert.doesNotMatch(html, /data-card-id="two"[^>]*disabled/);
  assert.match(html, /已提交/);
});

test('incremental poll preserves pending answer form and composer text', async () => {
  const interaction = { id: 'int_1', kind: 'question', status: 'pending', payload: {}, question: '选哪一个？' };
  const app = workbench(url => url.endsWith('/queue') ? { data: [] } : url.endsWith('/interactions') ? { data: [interaction] } : { id: 'thr_test', name: 'Conversation', messages: [] });
  const form = { dataset: { status: 'pending' }, outerHTML: 'original form' };
  app.nodes.set('#interaction_int_1', form);
  app.nodes.get('#chatInput').value = '未发送的草稿';
  app.run(`state.chatInteractions=${JSON.stringify([interaction])};state.chatInteractionSignatures.int_1=chatInteractionSignature(state.chatInteractions[0]);`);
  await app.context.refreshPersistentChat();
  assert.equal(form.outerHTML, 'original form');
  assert.equal(app.nodes.get('#chatInput').value, '未发送的草稿');
});

test('explicit retry of an uncertain queue submission reuses the exact submission identity', async () => {
  const submission = 'aac51271-3d73-40cf-9bb0-e986e38dd59d';
  const payload = { content: '唯一任务', agent_id: 'a', attachment_ids: [], interrupt: false, submission_id: submission };
  const app = workbench((url, options) => ({ message: { id: 'same_task', submission_id: submission, status: 'pending' } }));
  app.run(`state.chatUnknownSubmission=${JSON.stringify({ submission_id: submission, payload, retryAllowed: true })};`);
  app.nodes.get('#chatInput').value = payload.content;
  await app.context.retryUnknownChatSubmission();
  assert.deepEqual(JSON.parse(app.calls[0].options.body), payload);
  assert.equal(app.run('state.chatUnknownSubmission'), null);
  assert.equal(app.nodes.get('#chatInput').value, '');
});

test('an unknown answer stays locked and its explicit retry keeps the same answer and submission id', async () => {
  const app = workbench();
  const item = { id: 'int_1', kind: 'tool_approval', status: 'pending', payload: { tool_name: 'browser' } };
  app.run(`state.chatInteractions=${JSON.stringify([item])};`);
  const control = { disabled: false };
  app.nodes.set('#interaction_int_1', { querySelectorAll: () => [control], querySelector: () => ({ insertAdjacentHTML() {} }) });
  app.context.fetch = async (url, options = {}) => {
    app.calls.push({ url, options });
    if (options.method === 'POST') throw new Error('response lost');
    return { ok: true, json: async () => ({ data: [item] }) };
  };
  const button = { dataset: { interactionId: 'int_1' }, disabled: false };
  await app.context.answerChatInteraction(button, { decision: 'approved' });
  assert.equal(control.disabled, true);
  assert.equal(app.run('state.chatInteractionSubmissions.int_1.unknown'), true);
  const first = JSON.parse(app.calls[0].options.body);
  const refresh = { dataset: { interactionId: 'int_1' }, insertAdjacentHTML() {}, disabled: false };
  await app.context.refreshChatInteractionStatus(refresh);
  app.context.fetch = async (url, options = {}) => {
    app.calls.push({ url, options });
    return { ok: true, json: async () => ({ accepted: true, interaction: { ...item, status: 'submitting', submission_id: first.submission_id } }) };
  };
  await app.context.retryChatInteractionSubmission({ dataset: { interactionId: 'int_1' }, disabled: false });
  const posts = app.calls.filter(call => call.options.method === 'POST');
  assert.equal(posts.length, 2);
  assert.deepEqual(JSON.parse(posts[1].options.body), first);
});

test('event polling unwraps stored event data and advances the persisted sequence cursor', async () => {
  const app = workbench(() => ({ data: [{ id: 'event_1', sequence: 7, type: 'assistant_delta', data: { type: 'assistant_delta', content: '部分回答' } }] }));
  app.run("state.activeTurn={turn_id:'turn_1',status:'running'};");
  await app.context.refreshChatEvents('thr_test', 'turn_1', app.run('state.chatPollEpoch'));
  assert.equal(app.run('state.chatEvents.turn_1[0].content'), '部分回答');
  assert.equal(app.run('state.chatEventSequences.turn_1'), 7);
  await app.context.refreshChatEvents('thr_test', 'turn_1', app.run('state.chatPollEpoch'));
  assert.equal(app.run('state.chatEvents.turn_1.length'), 1);
  assert.match(app.calls[1].url, /since=7$/);
});

test('pending interaction recovery preserves a reload-time uncertain answer lock', () => {
  const app = workbench();
  app.context.localStorage.getItem = key => key.startsWith('codezzn.interactions') ? JSON.stringify({ int_1: { submission_id: 'original-id', payload: { answer: '原回答' }, pending: true } }) : null;
  app.run("state.chatInteractions=[{id:'int_1',kind:'question',status:'pending',payload:{options:[{id:'option_0',label:'执行'}]}}];");
  app.context.restoreChatInteractionSubmissions('thr_test');
  assert.equal(app.run('state.chatInteractionSubmissions.int_1.unknown'), true);
  assert.equal(app.run('state.chatInteractionSubmissions.int_1.pending'), false);
  const html = app.run('chatInteractionHtml(state.chatInteractions[0])');
  assert.match(html, /data-option-id="option_0" disabled/);
  assert.match(html, /刷新提交状态/);
});

test('confirmed answer history displays the received answer rather than an empty disabled form', () => {
  const app = workbench();
  const html = app.context.chatInteractionHtml({ id: 'int_1', kind: 'question', status: 'answered', question: '选择版本', payload: { options: [{ id: 'option_0', label: '稳定版' }] }, response: { option_id: 'option_0' } });
  assert.match(html, /interaction-response">稳定版/);
  assert.doesNotMatch(html, /<textarea/);
});

test('restored conversation places persistent questions between the corresponding messages', () => {
  const app = workbench();
  const html = app.context.persistentChatTimelineHtml([
    { id: 'before', role: 'user', content: '开始', created_at: '2026-10-12T01:00:00Z' },
    { id: 'after', role: 'assistant', content: '已经完成', created_at: '2026-10-12T01:00:02Z' },
  ], [{ id: 'question', kind: 'question', status: 'answered', question: '确认方案', created_at: '2026-10-12T01:00:01Z', response: { answer: '同意' } }]);
  assert.ok(html.indexOf('chatMessage_before') < html.indexOf('interaction_question'));
  assert.ok(html.indexOf('interaction_question') < html.indexOf('chatMessage_after'));
});

test('pending questions are docked above the composer, never duplicated in message history', () => {
  const app = workbench();
  const pending = { id: 'pending', kind: 'question', status: 'pending', question: '审批计划？', payload: { options: [{ id: 'yes', label: '批准', description: '仍需审批写入' }] } };
  assert.doesNotMatch(app.context.persistentChatTimelineHtml([], [pending]), /interaction_pending/);
  const html = app.context.chatInteractionHtml(pending);
  assert.match(html, /interaction-dock-item/);
  assert.match(html, /interaction-number[^>]*[^<]*>1</);
  assert.match(html, /用自己的话回答/);
  assert.match(html, /拒绝并关闭确认/);
  assert.doesNotMatch(html, /<textarea/);
  const template = fs.readFileSync(path.join(__dirname, '../web/workbench.js'), 'utf8');
  assert.ok(template.indexOf('id="chatInteractionDock"') < template.indexOf('<footer class="prompt-dock">'));
});

test('collapse is presentation only and never answers or cancels the interaction', () => {
  const app = workbench();
  const body = { hidden: false };
  const icon = { dataset: { collapseQuestion: 'icon' }, setAttribute(name, value) { this[name] = value; } };
  app.nodes.set('#interactionBody_question', body);
  app.nodes.set('#interaction_question', { querySelectorAll: () => [icon] });
  app.context.toggleChatInteraction({ dataset: { interactionId: 'question' } });
  assert.equal(body.hidden, true);
  assert.equal(icon['aria-expanded'], 'false');
  assert.equal(app.calls.length, 0);
  app.context.toggleChatInteraction({ dataset: { interactionId: 'question' } });
  assert.equal(body.hidden, false);
  assert.equal(icon.textContent, '−');
});

test('failure delete is confirmed by server, persisted in presentation metadata, and keeps the error', async () => {
  const app = workbench(() => ({ message: { id: 'failure', status: 'consumed', run_status: 'failed', error: 'original error', dismissed_at: 123 } }));
  app.run("state.chatQueue=[{id:'failure',status:'consumed',run_status:'failed',error:'original error'}];renderChatQueue();");
  assert.match(app.nodes.get('#chatQueue').innerHTML, /删除/);
  await app.context.dismissQueuedChatMessage({ disabled: false, dataset: { messageId: 'failure' } });
  assert.equal(app.calls[0].url, '/api/threads/thr_test/queue/failure/dismiss');
  assert.equal(app.calls[0].options.method, 'POST');
  assert.equal(app.nodes.get('#chatQueue').hidden, true);
  assert.equal(app.run('state.chatQueue[0].error'), 'original error');
  app.run('renderChatQueue()');
  assert.equal(app.nodes.get('#chatQueue').hidden, true);
});

test('failure delete does not hide unconfirmed failures or race an uncertain retry', async () => {
  const app = workbench(() => { throw new Error('network failure'); });
  app.run("state.chatQueue=[{id:'failure',status:'consumed',run_status:'failed',error:'keep me'}];renderChatQueue();");
  await app.context.dismissQueuedChatMessage({ disabled: false, dataset: { messageId: 'failure' } });
  assert.match(app.nodes.get('#chatQueue').innerHTML, /keep me/);
  assert.equal(app.run('state.chatQueue[0].dismissed_at'), undefined);
  app.run("state.chatUnknownSubmission={payload:{retry_of:'failure'}};");
  await app.context.dismissQueuedChatMessage({ disabled: false, dataset: { messageId: 'failure' } });
  assert.equal(app.calls.length, 1);
});

test('user-message actions show recorded send time, copy raw content and ignore assistant messages', async () => {
  const app = workbench();
  const text = '原始 **文字**\n第二行 <tag>';
  app.run(`state.currentThread.messages=[{id:'user',role:'user',content:${JSON.stringify(text)},meta:{sent_at:1735689600},created_at:1735693200}];`);
  let copied;
  app.context.copyTextToClipboard = async value => { copied = value; };
  await app.context.copyUserMessage({ dataset: { messageId: 'user' }, disabled: false });
  assert.equal(copied, text);
  const html = app.run('messageHtml(state.currentThread.messages[0])');
  assert.match(html, /datetime="2025-01-01T00:00:00.000Z"/);
  assert.match(html, /aria-label="复制消息"/);
  assert.match(html, /aria-label="编辑消息"/);
  assert.doesNotMatch(app.context.messageHtml({ role: 'assistant', content: 'reply' }), /user-message-actions/);
  assert.equal(app.context.userMessageTime({}).label, '时间未知');
});

test('inline message editing cancels without writes and escapes textarea contents', () => {
  const app = workbench();
  app.run("state.currentThread.messages=[{id:'user',role:'user',content:'</textarea><script>alert(1)</script>'}];");
  app.nodes.set('#chatMessage_user', { innerHTML: '' });
  app.context.startEditUserMessage({ dataset: { messageId: 'user' } });
  assert.match(app.nodes.get('#chatMessage_user').innerHTML, /&lt;\/textarea&gt;&lt;script&gt;/);
  assert.match(app.nodes.get('#chatMessage_user').innerHTML, /重新发送/);
  app.context.cancelUserMessageEdit();
  assert.equal(app.run('state.userMessageEdit'), null);
  assert.equal(app.calls.length, 0);
});

test('resending an edit preserves the original message and unrelated composer draft', async () => {
  const app = workbench((url, options) => ({ message: { id: 'edited_submission', content: JSON.parse(options.body).content, status: 'pending', run_status: 'pending' } }));
  app.run("state.currentThread.messages=[{id:'user',role:'user',content:'原消息'}];state.userMessageEdit={threadId:'thr_test',messageId:'user',content:'修改后的消息'};state.chatAttachments=[{id:'draft_file',status:'ready'}];");
  app.nodes.get('#chatInput').value = '另一个尚未发送的草稿';
  app.nodes.set('#userMessageEdit_user', { value: '修改后的消息' });
  await app.context.submitUserMessageEdit({ disabled: false });
  assert.equal(app.calls.length, 1);
  assert.equal(JSON.parse(app.calls[0].options.body).content, '修改后的消息');
  assert.equal(app.run('state.currentThread.messages[0].content'), '原消息');
  assert.equal(app.nodes.get('#chatInput').value, '另一个尚未发送的草稿');
  assert.equal(app.run('state.chatAttachments[0].id'), 'draft_file');
  assert.equal(app.run('state.userMessageEdit'), null);
});

test('confirming an uncertain edit submission still preserves the composer draft and attachments', () => {
  const app = workbench();
  app.nodes.get('#chatInput').value = '消息内容';
  app.run("state.chatAttachments=[{id:'draft_file',status:'ready'}];clearConfirmedChatDraft({preserveDraft:true,payload:{content:'消息内容',attachment_ids:['draft_file']}});");
  assert.equal(app.nodes.get('#chatInput').value, '消息内容');
  assert.equal(app.run('state.chatAttachments[0].id'), 'draft_file');
});

test('new chat uses the server default rather than inheriting a previously selected custom agent', async () => {
  const app = workbench(() => ({ id: 'new_default_thread', agent_id: 'agt_codezzn_default' }));
  app.run("loadPage=async()=>{};state.chatThreads=[];state.chatDrafts={};");
  await app.context.newThread();
  assert.equal(app.calls[0].url, '/api/threads');
  assert.equal(JSON.parse(app.calls[0].options.body).agent_id, undefined);
  assert.equal(app.run('state.thread'), 'new_default_thread');
});

test('permission selection preserves bound extensions and can restore inherited settings', async () => {
  const app = workbench((url, options) => url.startsWith('/api/chat/runtime')
    ? { permission_mode: 'plan', skill_discovery: 'auto', skills: [] }
    : { id: 'thr_test', capability_overrides: JSON.parse(options.body).capability_overrides });
  app.run("state.currentThread.capability_overrides={skill_ids:['s'],mcp_server_ids:['m']};");
  await app.context.changeChatPermissionMode('plan');
  let body = JSON.parse(app.calls[0].options.body);
  assert.deepEqual(body.capability_overrides, { skill_ids: ['s'], mcp_server_ids: ['m'], permission_mode: 'plan' });
  assert.equal(app.run('state.currentThread.capability_overrides.permission_mode'), 'plan');
  await app.context.changeChatPermissionMode('');
  body = JSON.parse(app.calls[2].options.body);
  assert.equal(body.capability_overrides.permission_mode, undefined);
  assert.deepEqual(body.capability_overrides.skill_ids, ['s']);
});

test('Skill command menu is optional, escapes content, excludes hidden skills and sends no task', () => {
  const app = workbench();
  app.nodes.set('#skillCommands', { innerHTML: '', hidden: true });
  app.run("state.chatRuntime={skills:[{id:'skill1',name:'example',command:'example',description:'<img onerror=bad>',user_invocable:true},{id:'hidden',name:'hidden',command:'hidden',user_invocable:false}]};");
  app.nodes.get('#chatInput').value = '/';
  app.context.renderSkillCommands();
  const menu = app.nodes.get('#skillCommands');
  assert.equal(menu.hidden, false);
  assert.match(menu.innerHTML, /\/example/);
  assert.doesNotMatch(menu.innerHTML, /<img|hidden/);
  assert.match(menu.innerHTML, /&lt;img/);
  app.nodes.get('#chatInput').value = 'ordinary question';
  app.context.renderSkillCommands();
  assert.equal(menu.hidden, true);
  assert.equal(app.calls.length, 0);
});
