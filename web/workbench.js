const pages = [
  { id: 'dashboard', label: '概览', short: 'HOME' },
  { id: 'chat', label: '对话调试', short: 'CHAT' },
  { id: 'tasks', label: '任务', short: 'TASK' },
  { id: 'agents', label: '智能体', short: 'AGENT' },
  { id: 'agent_teams', label: '智能体团队', short: 'TEAM' },
  { id: 'providers', label: '模型接入', short: 'MODEL' },
  { id: 'skills', label: '技能', short: 'SKILL' },
  { id: 'mcp_servers', label: 'MCP 服务', short: 'MCP' },
  { id: 'lsp_servers', label: 'LSP 服务', short: 'LSP' },
  { id: 'knowledge', label: '知识库', short: 'RAG' },
  { id: 'memories', label: '记忆', short: 'MEM' },
  { id: 'workflows', label: '工作流', short: 'FLOW' },
];

const navGroups = [
  ['工作区', ['dashboard', 'chat', 'tasks']],
  ['构建', ['agents', 'agent_teams', 'providers', 'skills', 'mcp_servers', 'lsp_servers', 'knowledge', 'memories']],
  ['编排', ['workflows']],
];

const navIcons = {
  dashboard: '<path d="M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z"/>',
  chat: '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.5 9 9 0 0 1-4-.9L3 21l1.9-5A9 9 0 1 1 21 11.5Z"/>',
  tasks: '<path d="M8 4h11a2 2 0 0 1 2 2v14H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h1m1-2h7v4H7zM8 11h9M8 15h6"/>',
  agents: '<rect x="4" y="7" width="16" height="13" rx="3"/><path d="M12 3v4M9 3h6M8 13h.01M16 13h.01M9 17h6"/>',
  agent_teams: '<circle cx="8" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M2 20v-2a6 6 0 0 1 12 0v2zM15 15a5 5 0 0 1 7 4v1h-5"/>',
  providers: '<path d="m12 2-8 11h7l-1 9 10-12h-7l1-8z"/>',
  skills: '<path d="m12 2 2.7 6.3L21 11l-6.3 2.7L12 20l-2.7-6.3L3 11l6.3-2.7z"/>',
  mcp_servers: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="8.5" y="14" width="7" height="7" rx="1"/><path d="M6.5 10v2h12v-2M12 12v2"/>',
  lsp_servers: '<path d="m8 5-6 7 6 7M16 5l6 7-6 7M14 3l-4 18"/>',
  knowledge: '<path d="M12 6a8 8 0 0 0-9-2v15a8 8 0 0 1 9 2 8 8 0 0 1 9-2V4a8 8 0 0 0-9 2ZM12 6v15"/>',
  memories: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  workflows: '<circle cx="5" cy="5" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="12" cy="19" r="2"/><path d="M6.7 6.1 11 17M17.3 6.1 13 17M7 5h10"/>',
};

const labels = {
  agents: ['智能体', '将模型、提示词、知识与工具组合成可运行的智能体。'],
  agent_teams: ['智能体团队', '配置协调智能体、团队成员和并行委派边界。'],
  providers: ['模型接入', '管理 OpenAI-compatible 推理端点和模型凭据。'],
  skills: ['技能', '维护可插拔的 SKILL.md 指令包。'],
  mcp_servers: ['MCP 服务', '连接外部工具、服务和数据源。'],
  lsp_servers: ['LSP 服务', '连接 pyright、typescript-language-server、gopls、rust-analyzer 等语言服务器。'],
  knowledge: ['知识库', '上传文档，构建可检索的 RAG 上下文。'],
  workflows: ['工作流', '把智能体和工具编排成可重复运行的流程。'],
};

const resourceKinds = Object.keys(labels);
let state = {
  page: 'dashboard', cache: {}, thread: null, threadScope: 'active', chatThreads: [],
  chatCapabilities: { skill_ids: [], mcp_server_ids: [] }, activeTurn: null,
};

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));

function headers(json = true) {
  const result = {};
  if (json) result['Content-Type'] = 'application/json';
  const key = localStorage.codezznKey;
  if (key) result['X-Codezzn-Key'] = key;
  return result;
}

async function api(path, options = {}) {
  options.headers = { ...headers(!(options.body instanceof FormData)), ...(options.headers || {}) };
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  return data;
}

function toast(message, error = false) {
  $('#toastRoot').innerHTML = `
    <div class="toast ${error ? 'toast-error' : ''}" role="${error ? 'alert' : 'status'}">
      <span class="toast-mark" aria-hidden="true">${error ? '!' : 'OK'}</span>
      <span>${esc(message)}</span>
    </div>`;
  window.setTimeout(() => { $('#toastRoot').innerHTML = ''; }, 3400);
}

function modal(title, body, onSave, wide = false, saveLabel = '保存') {
  $('#modalRoot').innerHTML = `
    <div class="drawer-layer" onclick="if(event.target===this)closeModal()">
      <section class="drawer ${wide ? 'drawer-wide' : ''}" role="dialog" aria-modal="true" aria-labelledby="drawerTitle">
        <header class="drawer-header">
          <div><span>配置检查器</span><h2 id="drawerTitle">${esc(title)}</h2></div>
          <button class="icon-button" type="button" onclick="closeModal()" aria-label="关闭对话框">关闭</button>
        </header>
        <div class="drawer-body">${body}</div>
        <footer class="drawer-footer">
          <button class="button button-quiet" type="button" onclick="closeModal()">取消</button>
          ${onSave ? `<button class="button button-primary" type="button" id="modalSave">${esc(saveLabel)}</button>` : ''}
        </footer>
      </section>
    </div>`;
  if (onSave) $('#modalSave').onclick = onSave;
  window.setTimeout(() => $('#modalRoot input, #modalRoot select, #modalRoot textarea, #modalRoot button')?.focus(), 0);
}

function closeModal() { $('#modalRoot').innerHTML = ''; }

function field(label, name, value = '', type = 'text', full = false, help = '') {
  const id = `field_${name}`;
  const input = type === 'textarea'
    ? `<textarea class="control-input" id="${id}" name="${name}">${esc(value)}</textarea>`
    : `<input class="control-input" id="${id}" type="${type}" name="${name}" value="${esc(value)}">`;
  return `
    <div class="control ${full ? 'control-full' : ''}">
      <label class="control-label" for="${id}">${esc(label)}</label>
      ${input}
      ${help ? `<small class="control-help">${esc(help)}</small>` : ''}
    </div>`;
}

function selectField(label, name, options, full = false, help = '', id = '') {
  const inputId = id || `field_${name}`;
  return `
    <div class="control ${full ? 'control-full' : ''}">
      <label class="control-label" for="${inputId}">${esc(label)}</label>
      <div class="select-shell"><select class="control-input" id="${inputId}" name="${name}">${options}</select></div>
      ${help ? `<small class="control-help">${esc(help)}</small>` : ''}
    </div>`;
}

function toggleField(label, name, checked = true, full = false) {
  return `
    <label class="toggle-control ${full ? 'control-full' : ''}">
      <input type="checkbox" name="${name}" ${checked ? 'checked' : ''}>
      <span class="toggle-track" aria-hidden="true"><span></span></span>
      <span>${esc(label)}</span>
    </label>`;
}

function formData(form) { return Object.fromEntries(new FormData(form).entries()); }

function toggleRail(open) { document.body.classList.toggle('rail-open', open); }

function toggleRailExpanded() {
  const expanded = document.body.classList.toggle('rail-expanded');
  try { localStorage.codezznRailExpanded = expanded ? 'true' : 'false'; } catch (_) {}
  syncRailState();
}

function syncRailState() {
  const expanded = document.body.classList.contains('rail-expanded');
  const toggle = $('#railToggle');
  if (toggle) {
    toggle.setAttribute('aria-expanded', String(expanded));
    toggle.setAttribute('aria-label', expanded ? '收起导航' : '展开导航');
    toggle.title = expanded ? '收起导航' : '展开导航';
  }
}

function setupRailBehavior() {
  const rail = $('#workspaceRail');
  if (!rail) return;
  try { document.body.classList.toggle('rail-expanded', localStorage.codezznRailExpanded === 'true'); } catch (_) {}
  syncRailState();
  rail.addEventListener('mouseenter', () => {
    if (matchMedia('(min-width: 701px)').matches) document.body.classList.add('rail-hover');
  });
  rail.addEventListener('mouseleave', () => document.body.classList.remove('rail-hover'));
  rail.addEventListener('focusin', () => {
    if (matchMedia('(min-width: 701px)').matches) document.body.classList.add('rail-hover');
  });
  rail.addEventListener('focusout', event => {
    if (!rail.contains(event.relatedTarget)) document.body.classList.remove('rail-hover');
  });
}

async function loadSession() {
  try {
    const result = await fetch('/api/auth/me', { credentials: 'same-origin' }).then(async response => {
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      return data;
    });
    if (!result.authenticated || !result.user) return;
    const user = result.user;
    const label = user.name || 'Codezzn 用户';
    $('#sessionName').textContent = label;
    $('#sessionProvider').textContent = user.provider === 'github' ? 'GitHub 账号' : '邮箱账号';
    $('#sessionAvatar').textContent = label.trim().charAt(0).toUpperCase() || 'U';
    $('#sessionLogout').hidden = false;
  } catch (_) {
    // The workbench remains available when authentication is optional.
  }
}

async function logoutSession() {
  const button = $('#sessionLogout');
  if (button) { button.disabled = true; button.textContent = '…'; }
  try {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
  } finally {
    location.assign('/login');
  }
}

function nav() {
  const byId = Object.fromEntries(pages.map(page => [page.id, page]));
  $('#nav').innerHTML = navGroups.map(([group, ids]) => `
    <section class="nav-group" aria-label="${esc(group)}">
      <div class="nav-group-label">${esc(group)}</div>
      ${ids.map(id => {
        const page = byId[id];
        const active = state.page === id;
        return `
          <button class="nav-item ${active ? 'is-active' : ''}" type="button" onclick="go('${id}')" aria-label="${esc(page.label)}" title="${esc(page.label)}" ${active ? 'aria-current="page"' : ''}>
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${navIcons[id]}</svg>
            <span class="nav-label">${page.label}</span><span class="nav-short">${page.short}</span>
          </button>`;
      }).join('')}
    </section>`).join('');
}

function go(page) {
  state.page = page;
  toggleRail(false);
  document.body.classList.toggle('page-dashboard', page === 'dashboard');
  if (location.hash !== `#${page}`) history.replaceState(null, '', `#${page}`);
  nav();
  $('#pageTitle').textContent = pages.find(item => item.id === page)?.label || page;
  loadPage();
}

function quickCreate() {
  if (state.page === 'chat') return newThread();
  if (state.page === 'tasks') return createAgentTask();
  if (state.page === 'memories') return createMemory();
  if (resourceKinds.includes(state.page)) return editResource(state.page);
  go('agents');
  window.setTimeout(() => editResource('agents'), 120);
}

async function load(kind) {
  const result = await api(`/api/resources/${kind}`);
  state.cache[kind] = result.data;
  return result.data;
}

function loading() {
  return `
    <div class="page-loading" aria-label="正在加载">
      <div class="skeleton-title"></div>
      <div class="skeleton-subtitle"></div>
      <div class="skeleton-layout"><div></div><div></div><div></div></div>
    </div>`;
}

async function loadPage() {
  const content = $('#content');
  document.body.classList.toggle('page-dashboard', state.page === 'dashboard');
  content.classList.toggle('viewport-chat', state.page === 'chat');
  content.innerHTML = loading();
  try {
    if (state.page === 'dashboard') return dashboard();
    if (state.page === 'chat') return chat();
    if (state.page === 'tasks') return tasksPage();
    if (state.page === 'memories') return memoriesPage();
    return resources(state.page);
  } catch (error) {
    toast(error.message, true);
    content.innerHTML = `
      <div class="state-page state-error">
        <span class="state-code">加载失败</span>
        <h2>当前页面暂时不可用</h2>
        <p>${esc(error.message)}</p>
        <button class="button button-primary" type="button" onclick="loadPage()">重新加载</button>
      </div>`;
  }
}

async function dashboard() {
  const recent = await api('/api/threads');
  const setup = [
    ['连接模型', '配置百炼或其他兼容模型', 'providers', 'MODEL'],
    ['装配智能体', '选择模型、技能、知识和工具', 'agents', 'AGENT'],
    ['导入知识', '上传资料并验证检索结果', 'knowledge', 'RAG'],
    ['编排流程', '组合节点并运行自动化任务', 'workflows', 'FLOW'],
  ];

  $('#content').innerHTML = `
    <div class="rf-dashboard page-enter">
      <section class="rf-hero">
        <div class="rf-hero-inner">
          <h1>今天想构建什么？</h1>
          <div class="rf-composer">
            <textarea class="rf-composer-input" id="dashboardInput" aria-label="输入构建任务" placeholder="描述你想构建的智能体或任务…" rows="2" oninput="updateDashboardSend()" onkeydown="dashboardComposerKeydown(event)"></textarea>
            <div class="rf-composer-toolbar">
              <div class="rf-composer-tools">
                <button type="button" onclick="go('agents')" aria-label="查看智能体"><span aria-hidden="true">✧</span> 智能体</button>
                <button type="button" onclick="go('chat')" aria-label="查看对话历史"><span aria-hidden="true">◷</span> 历史</button>
              </div>
              <button class="rf-composer-send" id="dashboardSend" type="button" onclick="sendDashboardPrompt()" aria-label="发送任务" disabled><span aria-hidden="true">↑</span></button>
            </div>
          </div>
          <div class="rf-suggestions" aria-label="快速开始">
            <button class="rf-suggestion" type="button" onclick="go('agents')">创建智能体</button>
            <button class="rf-suggestion" type="button" onclick="go('providers')">接入模型</button>
            <button class="rf-suggestion" type="button" onclick="go('workflows')">编排工作流</button>
            <button class="rf-suggestion" type="button" onclick="go('knowledge')">打开知识库</button>
          </div>
          <button class="rf-connect" type="button" onclick="go('agents')">配置编码智能体 <span aria-hidden="true">→</span></button>
        </div>
      </section>
      <div class="rf-home-panel">
        <div class="rf-home-tabs" role="tablist" aria-label="首页内容">
          <button class="rf-home-tab is-active" type="button" role="tab" aria-selected="true" onclick="switchDashboardTab('recent')" data-home-tab="recent">最近</button>
          <button class="rf-home-tab" type="button" role="tab" aria-selected="false" onclick="switchDashboardTab('examples')" data-home-tab="examples">示例</button>
        </div>
        <section class="rf-home-section rf-examples" data-home-section="examples">
          <header><h2>从这里开始</h2><p>选一条路径，把想法变成可运行的智能体。</p></header>
          <div class="rf-example-grid">
            ${setup.slice(0, 3).map(([name, note, page, code]) => `
              <button class="rf-example-card" type="button" onclick="go('${page}')">
                <span class="rf-example-icon" aria-hidden="true">${code.slice(0, 1)}</span><strong>${name}</strong><small>${note}</small><span class="rf-example-arrow" aria-hidden="true">→</span>
              </button>`).join('')}
          </div>
        </section>
        <section class="rf-home-section rf-recent is-active" data-home-section="recent">
          <header><div><h2>最近对话</h2><p>${recent.data.length} 个活跃会话</p></div><button class="text-action" type="button" onclick="go('chat')">查看全部 →</button></header>
          ${recent.data.length ? `
            <div class="rf-recent-list">
              ${recent.data.slice(0, 5).map(thread => `
                <button class="rf-recent-card" type="button" onclick="openDashboardThread('${esc(thread.id)}')" aria-label="打开会话 ${esc(thread.name)}">
                  <span class="rf-recent-icon" aria-hidden="true">◷</span><span><strong>${esc(thread.name)}</strong><small>${esc(threadStatus(thread.status))}</small></span><b aria-hidden="true">→</b>
                </button>`).join('')}
            </div>` : `<div class="state-inline"><p>还没有对话记录。</p><button class="text-action" type="button" onclick="go('chat')">开始第一段对话 →</button></div>`}
        </section>
      </div>
    </div>`;
}

function updateDashboardSend() {
  const button = $('#dashboardSend');
  if (button) button.disabled = !$('#dashboardInput')?.value.trim();
}

function dashboardComposerKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    sendDashboardPrompt();
  }
}

function sendDashboardPrompt() {
  const prompt = $('#dashboardInput')?.value.trim();
  if (!prompt) return;
  state.pendingDashboardPrompt = prompt;
  state.threadScope = 'active';
  state.thread = null;
  go('chat');
}

function openDashboardThread(threadId) {
  state.pendingDashboardPrompt = null;
  state.threadScope = 'active';
  state.thread = threadId;
  go('chat');
}

function switchDashboardTab(tab) {
  $$('.rf-home-tab').forEach(button => {
    const active = button.dataset.homeTab === tab;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-selected', String(active));
  });
  $$('.rf-home-section').forEach(section => section.classList.toggle('is-active', section.dataset.homeSection === tab));
}

function timeText(value) {
  return value ? new Date(Number(value) * 1000).toLocaleString() : '—';
}

async function tasksPage() {
  const [tasks, subagents] = await Promise.all([api('/api/tasks'), api('/api/subagents')]);
  const running = tasks.data.filter(task => ['queued', 'running'].includes(task.status)).length;
  $('#content').innerHTML = `
    <div class="collection-page page-enter">
      <header class="collection-header"><div><span class="overline">持久执行队列</span><h1>任务</h1><p>后台运行智能体与工作流；服务重启后自动恢复未完成任务。</p></div><div class="header-actions"><button class="button button-quiet" type="button" onclick="loadPage()">刷新</button><button class="button button-primary" type="button" onclick="createAgentTask()">新建任务</button></div></header>
      <div class="collection-toolbar"><div class="collection-count"><strong>${tasks.data.length}</strong><span>最近任务</span><span class="count-divider"></span><strong>${running}</strong><span>等待/运行</span><span class="count-divider"></span><strong>${subagents.data.length}</strong><span>子智能体记录</span></div></div>
      ${tasks.data.length ? `<div class="resource-list">${tasks.data.map(task => `
        <article class="resource-record">
          <div class="record-identity"><span class="state-badge ${['failed','cancelled'].includes(task.status) ? 'is-off' : ''}">${esc(task.status)}</span><div><h2>${esc(task.name)}</h2><p>${esc(task.kind)} · 尝试 ${task.attempts}/${task.max_attempts} · ${timeText(task.created_at)}</p></div></div>
          <div class="record-facts"><span>${esc(task.id)}</span>${task.error ? `<span>${esc(task.error.slice(0, 100))}</span>` : ''}</div>
          <div class="record-actions"><button class="button button-quiet button-small" type="button" onclick="showTask('${task.id}')">详情</button>${['queued','running'].includes(task.status) ? `<button class="button button-danger button-small" type="button" onclick="cancelPersistentTask('${task.id}')">取消</button>` : ''}</div>
        </article>`).join('')}</div>` : '<div class="state-page"><span class="state-code">后台队列</span><h2>还没有任务</h2><p>创建一个智能体任务，或从工作流页面选择后台运行。</p></div>'}
    </div>`;
}

async function createAgentTask() {
  const agents = await load('agents');
  modal('新建后台任务', `<form id="taskForm" class="form-layout">
    ${field('任务名称', 'name', '')}
    ${selectField('智能体', 'agent_id', agents.map(agent => `<option value="${agent.id}">${esc(agent.name)}</option>`).join(''))}
    ${field('任务内容', 'prompt', '', 'textarea', true)}
    ${field('最大尝试次数', 'max_attempts', 3, 'number')}
  </form>`, async () => {
    const data = formData($('#taskForm'));
    data.max_attempts = Number(data.max_attempts);
    try { await api('/api/agent-tasks', { method: 'POST', body: JSON.stringify(data) }); closeModal(); toast('任务已进入持久队列'); if (state.page === 'tasks') loadPage(); }
    catch (error) { toast(error.message, true); }
  }, false, '创建任务');
}

async function showTask(id) {
  try {
    const task = await api(`/api/tasks/${id}`);
    modal('任务详情', `<div class="result-grid"><div><span>状态</span><strong>${esc(task.status)}</strong></div><div><span>尝试次数</span><strong>${task.attempts}/${task.max_attempts}</strong></div></div>
      ${task.error ? `<div class="result-block"><span>错误</span><pre class="code-output">${esc(task.error)}</pre></div>` : ''}
      <div class="result-block"><span>结果</span><pre class="code-output">${esc(JSON.stringify(task.result, null, 2))}</pre></div>
      <div class="result-block"><span>事件</span><pre class="code-output">${esc(JSON.stringify(task.events, null, 2))}</pre></div>`, null, true);
  } catch (error) { toast(error.message, true); }
}

async function cancelPersistentTask(id) {
  try { await api(`/api/tasks/${id}`, { method: 'DELETE' }); toast('任务已取消'); loadPage(); }
  catch (error) { toast(error.message, true); }
}

async function memoriesPage() {
  const result = await api('/api/memories');
  $('#content').innerHTML = `
    <div class="collection-page page-enter">
      <header class="collection-header"><div><span class="overline">长期上下文</span><h1>记忆</h1><p>管理跨会话的用户偏好、项目事实和任务经验。</p></div><button class="button button-primary" type="button" onclick="createMemory()">新增记忆</button></header>
      <div class="collection-toolbar"><div class="collection-count"><strong>${result.data.length}</strong><span>记忆条目</span></div><label class="filter-control"><span>筛选</span><input type="search" oninput="filterResources(this.value)" placeholder="搜索内容或范围"></label></div>
      ${result.data.length ? `<div class="resource-list" id="resourceList">${result.data.map(memory => `
        <article class="resource-record" data-search="${esc(`${memory.scope} ${memory.scope_id} ${memory.kind} ${memory.content}`.toLowerCase())}">
          <div class="record-identity"><span class="state-badge ${memory.status !== 'confirmed' ? 'is-off' : ''}">${esc(memory.status || memory.scope)}</span><div><h2>${esc(memory.kind)}</h2><p>${esc(memory.content)}</p></div></div>
          <div class="record-facts"><span>${esc(memory.scope)}/${esc(memory.scope_id)}</span><span>重要度 ${Number(memory.importance).toFixed(2)}</span><span>可信度 ${Number(memory.confidence ?? .7).toFixed(2)}</span>${memory.conflict_with ? '<span>检测到冲突</span>' : ''}${memory.expires_at ? `<span>过期 ${timeText(memory.expires_at)}</span>` : ''}</div>
          <div class="record-actions">${memory.status === 'pending' ? `<button class="button button-primary button-small" type="button" onclick="confirmMemory('${memory.id}',true,${Boolean(memory.conflict_with)})">确认</button><button class="button button-quiet button-small" type="button" onclick="confirmMemory('${memory.id}',false,false)">拒绝</button>` : ''}<button class="button button-danger button-small" type="button" onclick="removeMemory('${memory.id}')">删除</button></div>
        </article>`).join('')}</div>` : '<div class="state-page"><span class="state-code">长期记忆</span><h2>还没有记忆</h2><p>可以手动新增，也可以在智能体中启用自动经验沉淀。</p></div>'}
    </div>`;
}

function createMemory() {
  modal('新增长期记忆', `<form id="memoryForm" class="form-layout">
    ${selectField('范围', 'scope', '<option value="project">项目</option><option value="user">用户</option><option value="thread">会话</option>')}
    ${field('范围 ID', 'scope_id', 'default')}${field('类型', 'kind', 'fact')}
    ${field('重要度（0-1）', 'importance', 0.6, 'number')}${field('可信度（0-1）', 'confidence', 0.8, 'number')}${field('过期时间戳（可空）', 'expires_at', '')}${field('内容', 'content', '', 'textarea', true)}
  </form>`, async () => {
    const data = formData($('#memoryForm')); data.importance = Number(data.importance); data.confidence = Number(data.confidence); data.expires_at = data.expires_at ? Number(data.expires_at) : null;
    try { await api('/api/memories', { method: 'POST', body: JSON.stringify(data) }); closeModal(); toast('记忆已保存'); if (state.page === 'memories') loadPage(); }
    catch (error) { toast(error.message, true); }
  }, false, '保存记忆');
}

async function confirmMemory(id, accept, supersede) {
  try { await api(`/api/memories/${id}/confirm`, { method:'POST', body:JSON.stringify({accept, supersede_conflict:supersede}) }); toast(accept ? '记忆已确认' : '记忆已拒绝'); loadPage(); }
  catch(error){ toast(error.message, true); }
}

async function removeMemory(id) {
  if (!confirm('确定删除这条记忆？')) return;
  try { await api(`/api/memories/${id}`, { method: 'DELETE' }); toast('记忆已删除'); loadPage(); }
  catch (error) { toast(error.message, true); }
}

async function resources(kind) {
  const list = await load(kind);
  const enabled = list.filter(item => item.enabled !== false).length;
  $('#content').innerHTML = `
    <div class="collection-page page-enter">
      <header class="collection-header">
        <div><span class="overline">能力管理</span><h1>${labels[kind][0]}</h1><p>${labels[kind][1]}</p></div>
        <div class="header-actions">
          ${kind === 'skills' ? '<button class="button button-quiet" type="button" onclick="importSkill()">导入 Skill 包</button>' : ''}
          <button class="button button-primary" type="button" onclick="editResource('${kind}')">新建${labels[kind][0]}</button>
        </div>
      </header>
      <div class="collection-toolbar">
        <div class="collection-count"><strong>${list.length}</strong><span>全部</span><span class="count-divider"></span><strong>${enabled}</strong><span>已启用</span></div>
        <label class="filter-control"><span>筛选</span><input type="search" oninput="filterResources(this.value)" placeholder="按名称或描述查找"></label>
      </div>
      ${list.length ? `<div class="resource-list" id="resourceList">${list.map(item => resourceCard(kind, item)).join('')}</div>` : `
        <div class="state-page">
          <span class="state-code">空工作区</span><h2>还没有${labels[kind][0]}</h2><p>创建第一个配置后，它会显示在这里。</p>
          <button class="button button-primary" type="button" onclick="editResource('${kind}')">立即创建</button>
        </div>`}
    </div>`;
}

function resourceCard(kind, item) {
  const description = item.description || item.base_url || item.transport || `${(item.nodes || []).length} 个节点` || '暂无描述';
  let facts = [];
  if (kind === 'agents') facts = [item.model || '未选择模型', `${(item.skill_ids || []).length} 个技能`, `${(item.knowledge_ids || []).length} 个知识库`];
  if (kind === 'agent_teams') facts = [`${(item.member_ids || []).length} 个成员`, `并行 ${item.max_concurrency || 4}`, `深度 ${item.max_depth || 2}`];
  if (kind === 'providers') facts = [item.type === 'bailian' ? '阿里云百炼' : 'OpenAI compatible', `${(item.models || []).length} 个模型`, item.api_key_configured ? '密钥已配置' : '等待密钥'];
  if (kind === 'knowledge') facts = [`${item.document_count || 0} 个文档`, `${item.chunk_count || 0} 个片段`, item.backend === 'ragflow' ? 'RAGFlow' : (item.embedding_model || '本地 Milvus')];
  if (kind === 'mcp_servers') facts = [(item.transport || 'stdio').toUpperCase()];
  if (kind === 'lsp_servers') facts = [item.command || '未配置命令'];
  if (kind === 'workflows') facts = [`${(item.nodes || []).length} 个节点`];
  if (kind === 'skills') facts = ['SKILL.md'];
  const searchText = `${item.name} ${description} ${facts.join(' ')}`.toLowerCase();

  return `
    <article class="resource-record" data-search="${esc(searchText)}">
      <div class="record-identity">
        <span class="state-badge ${item.enabled === false ? 'is-off' : ''}">${item.enabled === false ? '停用' : '启用'}</span>
        <div><h2>${esc(item.name)}</h2><p>${esc(description)}</p></div>
      </div>
      <div class="record-facts">${facts.map(fact => `<span>${esc(fact)}</span>`).join('')}</div>
      <div class="record-actions">
        <button class="button button-quiet button-small" type="button" onclick="editResource('${kind}','${item.id}')">编辑</button>
        ${kind === 'providers' ? `<button class="button button-quiet button-small" type="button" onclick="testProvider('${item.id}')">测试连接</button>` : ''}
        ${kind === 'knowledge' ? `${item.backend === 'ragflow' && !item.ragflow_dataset_id ? `<button class="button button-quiet button-small" type="button" onclick="provisionRagflow('${item.id}')">创建数据集</button>` : ''}<button class="button button-quiet button-small" type="button" onclick="uploadDoc('${item.id}')">上传文档</button><button class="button button-quiet button-small" type="button" onclick="showKnowledgeStatus('${item.id}')">文档状态</button><button class="button button-quiet button-small" type="button" onclick="testKnowledge('${item.id}')">测试检索</button>` : ''}
        ${kind === 'mcp_servers' ? `<button class="button button-quiet button-small" type="button" onclick="testMcp('${item.id}')">测试服务</button>` : ''}
        ${kind === 'workflows' ? `<button class="button button-quiet button-small" type="button" onclick="runWorkflow('${item.id}')">前台运行</button><button class="button button-quiet button-small" type="button" onclick="enqueueWorkflow('${item.id}')">后台运行</button>` : ''}
        <button class="button button-danger button-small" type="button" onclick="removeResource('${kind}','${item.id}')">删除</button>
      </div>
    </article>`;
}

function filterResources(query) {
  const value = query.trim().toLowerCase();
  $$('.resource-record').forEach(item => { item.hidden = value && !item.dataset.search.includes(value); });
}

async function editResource(kind, id) {
  const item = id ? state.cache[kind]?.find(value => value.id === id) : {};
  if (kind === 'providers') return providerForm(item || {});
  if (kind === 'skills') return skillForm(item || {});
  if (kind === 'mcp_servers') return mcpForm(item || {});
  if (kind === 'lsp_servers') return lspForm(item || {});
  if (kind === 'knowledge') return knowledgeForm(item || {});
  if (kind === 'agents') return agentForm(item || {});
  if (kind === 'agent_teams') return agentTeamForm(item || {});
  if (kind === 'workflows') return workflowForm(item || {});
}

async function save(kind, id, data) {
  const button = $('#modalSave');
  if (button) { button.disabled = true; button.textContent = '保存中'; }
  try {
    await api(`/api/resources/${kind}${id ? `/${id}` : ''}`, { method: id ? 'PUT' : 'POST', body: JSON.stringify(data) });
    closeModal();
    toast('配置已保存');
    await loadPage();
  } catch (error) {
    if (button) { button.disabled = false; button.textContent = '保存'; }
    toast(error.message, true);
  }
}

async function providerForm(item) {
  const presets = (await api('/api/provider-presets')).data;
  const presetOptions = [`<option value="openai">OpenAI Compatible（自定义）</option>`, ...presets.map(preset => `<option value="${preset.id}">${esc(preset.name)}</option>`)].join('');
  modal(item.id ? '编辑模型提供方' : '新建模型提供方', `
    <form id="editForm" class="form-layout">
      <section class="form-section control-full"><header><h3>连接信息</h3><p>选择预设，或填写兼容 OpenAI API 的服务地址。</p></header></section>
      ${selectField('快速预设', 'preset', presetOptions, true, '套用预设后仍可调整下面的字段。', 'providerPreset')}
      ${field('名称', 'name', item.name)}
      ${selectField('类型', 'type', `<option value="openai" ${item.type !== 'bailian' ? 'selected' : ''}>OpenAI Compatible</option><option value="bailian" ${item.type === 'bailian' ? 'selected' : ''}>阿里云百炼 Qwen</option>`, false, '', 'providerType')}
      ${field('Base URL', 'base_url', item.base_url || 'https://api.openai.com/v1', 'text', true)}
      ${field('API Key', 'api_key', '', 'password', true, item.api_key_configured ? '密钥已经配置。留空会保留原密钥。' : '填写与当前地域和计费方案匹配的密钥。')}
      <section class="form-section control-full"><header><h3>模型设置</h3><p>定义这个提供方可供智能体选择的模型。</p></header></section>
      ${field('模型（逗号分隔）', 'models', (item.models || []).join(', '), 'text', true, '例如 qwen3.7-plus。')}
      ${field('默认模型', 'default_model', item.default_model || 'gpt-4.1-mini')}
      ${field('超时（秒）', 'timeout', item.timeout || 120, 'number')}
      ${selectField('API 模式', 'api_mode', `<option value="chat_completions" ${(item.api_mode || 'chat_completions') === 'chat_completions' ? 'selected' : ''}>Chat Completions 兼容模式</option><option value="responses" ${item.api_mode === 'responses' ? 'selected' : ''}>Responses API</option>`, true, '只有端点真实支持 /responses 时才选择 Responses API。')}
      ${selectField('默认推理强度', 'reasoning_effort', ['low','medium','high','xhigh'].map(value => `<option value="${value}" ${(item.reasoning_effort || 'medium') === value ? 'selected' : ''}>${value}</option>`).join(''))}
      ${field('压缩阈值（token）', 'compact_threshold', item.compact_threshold || 120000, 'number')}
      ${toggleField('自动上下文压缩', 'context_compaction', item.context_compaction !== false)}${toggleField('异步工具声明', 'async_tools', item.async_tools === true)}
    </form>`, () => {
      const data = formData($('#editForm'));
      delete data.preset;
      data.models = data.models.split(',').map(value => value.trim()).filter(Boolean);
      data.timeout = Number(data.timeout);
      data.compact_threshold = Number(data.compact_threshold);
      data.context_compaction = $('#editForm [name=context_compaction]').checked;
      data.async_tools = $('#editForm [name=async_tools]').checked;
      save('providers', item.id, data);
    });
  const form = $('#editForm');
  form.preset.onchange = () => {
    const preset = presets.find(value => value.id === form.preset.value);
    if (!preset) return;
    form.name.value = item.id ? item.name : preset.name;
    form.type.value = preset.type;
    form.base_url.value = preset.base_url;
    form.models.value = preset.models.join(', ');
    form.default_model.value = preset.default_model;
  };
}

function skillForm(item) {
  modal(item.id ? '编辑技能' : '新建技能', `
    <form id="editForm" class="form-layout">
      ${field('名称', 'name', item.name)}${field('描述', 'description', item.description)}
      ${field('SKILL.md 内容', 'content', item.content || '# Skill\n\n描述智能体应遵循的工作步骤。', 'textarea', true)}
      ${toggleField('启用技能', 'enabled', item.enabled !== false, true)}
    </form>`, () => {
      const data = formData($('#editForm'));
      data.enabled = $('#editForm [name=enabled]').checked;
      save('skills', item.id, data);
    });
}

function mcpForm(item) {
  modal(item.id ? '编辑 MCP 服务' : '新建 MCP 服务', `
    <form id="editForm" class="form-layout">
      <section class="form-section control-full"><header><h3>服务连接</h3><p>选择本地进程或 HTTP JSON-RPC。</p></header></section>
      ${field('名称', 'name', item.name)}
      ${selectField('Transport', 'transport', `<option value="stdio" ${item.transport !== 'http' ? 'selected' : ''}>stdio</option><option value="http" ${item.transport === 'http' ? 'selected' : ''}>HTTP JSON-RPC</option>`)}
      ${field('命令（stdio）', 'command', item.command || 'npx', 'text', true)}
      ${field('参数 JSON 数组', 'args', JSON.stringify(item.args || []), 'textarea', true)}
      ${field('HTTP URL', 'url', item.url || '', 'text', true)}
      ${field('环境变量 JSON', 'env', JSON.stringify(item.env || {}), 'textarea')}
      ${field('HTTP Headers JSON', 'headers', JSON.stringify(item.headers || {}), 'textarea')}
      ${toggleField('启用服务', 'enabled', item.enabled !== false, true)}
    </form>`, () => {
      try {
        const data = formData($('#editForm'));
        data.args = JSON.parse(data.args || '[]');
        data.env = JSON.parse(data.env || '{}');
        data.headers = JSON.parse(data.headers || '{}');
        data.enabled = $('#editForm [name=enabled]').checked;
        save('mcp_servers', item.id, data);
      } catch (error) { toast(`JSON 格式错误：${error.message}`, true); }
    });
}

async function knowledgeForm(item) {
  const providers = await load('providers');
  const provider = item.embedding_provider_id || providers.find(value => value.type === 'bailian')?.id || providers[0]?.id || '';
  const selectedBackend = item.backend || 'local';
  modal(item.id ? '编辑知识库' : '新建知识库', `
    <form id="editForm" class="form-layout">
      ${field('名称', 'name', item.name)}${field('描述', 'description', item.description)}
      <section class="form-section control-full"><header><h3>检索后端</h3><p>已有知识库默认保持本地；RAGFlow 通过独立服务 API 接入。</p></header></section>
      ${selectField('后端类型', 'backend', `<option value="local" ${selectedBackend === 'local' ? 'selected' : ''}>本地 Milvus</option><option value="ragflow" ${selectedBackend === 'ragflow' ? 'selected' : ''}>RAGFlow</option>`)}
      ${field('RAGFlow 数据集 ID', 'ragflow_dataset_id', item.ragflow_dataset_id || '', 'text', false, 'RAGFlow 后端必填。先在 RAGFlow 创建数据集，再复制数据集 ID；连接地址和 API Key 由环境变量统一提供。')}
      ${selectField('RAGFlow 切片方法', 'chunk_method', ['naive','book','email','laws','manual','one','paper','picture','presentation','qa','table','tag'].map(value => `<option value="${value}" ${(item.chunk_method || 'naive') === value ? 'selected' : ''}>${value}</option>`).join(''))}
      <section class="form-section control-full"><header><h3>本地向量索引</h3><p>仅本地 Milvus 后端使用；修改模型或维度后需要重建索引。</p></header></section>
      ${selectField('Embedding 提供方', 'embedding_provider_id', providers.map(value => `<option value="${value.id}" ${provider === value.id ? 'selected' : ''}>${esc(value.name)}</option>`).join(''))}
      ${field('Embedding 模型', 'embedding_model', item.embedding_model || 'qwen3.7-text-embedding')}
      ${field('向量维度', 'embedding_dimension', item.embedding_dimension || 1024, 'number')}
      ${field('重排序模型', 'rerank_model', item.rerank_model || 'qwen3-rerank')}
      <section class="form-section control-full"><header><h3>RAGFlow 检索参数</h3><p>控制混合召回、候选池和重排窗口。</p></header></section>
      ${field('相似度阈值', 'similarity_threshold', item.similarity_threshold ?? 0.2, 'number')}
      ${field('向量权重', 'vector_similarity_weight', item.vector_similarity_weight ?? 0.3, 'number')}
      ${field('KNN Top K', 'knn_top_k', item.knn_top_k || 1024, 'number')}
      ${field('KNN 候选数', 'knn_num_candidates', item.knn_num_candidates || 2048, 'number')}
      ${field('重排候选数', 'rerank_candidates_count', item.rerank_candidates_count || 64, 'number')}
      ${field('RAGFlow Reranker ID', 'rerank_id', item.rerank_id || '')}
      ${toggleField('TOC 增强', 'toc_enhance', item.toc_enhance === true)}${toggleField('知识图谱增强', 'use_kg', item.use_kg === true)}
      ${toggleField('启用知识库', 'enabled', item.enabled !== false, true)}
    </form>`, () => {
      const data = formData($('#editForm'));
      if (!['local', 'ragflow'].includes(data.backend)) { toast('请选择有效的知识库后端', true); return; }
      if (data.backend === 'ragflow' && !data.ragflow_dataset_id.trim()) { toast('RAGFlow 后端需要数据集 ID', true); return; }
      data.embedding_dimension = Number(data.embedding_dimension);
      for (const key of ['similarity_threshold', 'vector_similarity_weight']) data[key] = Number(data[key]);
      for (const key of ['knn_top_k', 'knn_num_candidates', 'rerank_candidates_count']) data[key] = Number(data[key]);
      data.toc_enhance = $('#editForm [name=toc_enhance]').checked;
      data.use_kg = $('#editForm [name=use_kg]').checked;
      data.enabled = $('#editForm [name=enabled]').checked;
      save('knowledge', item.id, data);
    });
}

function choiceGroup(title, name, items, selected = []) {
  return `
    <div class="control control-full">
      <span class="control-label">${esc(title)}</span>
      <div class="choice-grid">
        ${items.length ? items.map(item => `
          <label class="choice-item"><input type="checkbox" name="${name}" value="${item.id}" ${selected.includes(item.id) ? 'checked' : ''}><span>${esc(item.name)}</span></label>`).join('') : '<span class="control-help">暂无可选项</span>'}
      </div>
    </div>`;
}

function lspForm(item) {
  modal(item.id ? '编辑 LSP 服务' : '新建 LSP 服务', `
    <form id="editForm" class="form-layout">
      ${field('名称', 'name', item.name)}${field('语言', 'language', item.language || 'python')}
      ${field('启动命令', 'command', item.command || 'pyright-langserver')}
      ${field('参数 JSON 数组', 'args', JSON.stringify(item.args || ['--stdio']), 'textarea', true)}
      ${toggleField('启用服务', 'enabled', item.enabled !== false, true)}
    </form>`, () => {
      try {
        const data = formData($('#editForm')); data.args = JSON.parse(data.args || '[]'); data.enabled = $('#editForm [name=enabled]').checked;
        save('lsp_servers', item.id, data);
      } catch (error) { toast(`JSON 格式错误：${error.message}`, true); }
    });
}

async function agentTeamForm(item) {
  const agents = await load('agents');
  modal(item.id ? '编辑智能体团队' : '新建智能体团队', `
    <form id="editForm" class="form-layout">
      ${field('名称', 'name', item.name)}${field('描述', 'description', item.description)}
      ${selectField('协调智能体', 'coordinator_agent_id', agents.map(agent => `<option value="${agent.id}" ${item.coordinator_agent_id === agent.id ? 'selected' : ''}>${esc(agent.name)}</option>`).join(''), true, '协调智能体负责拆解任务并通过 delegate_task 委派。')}
      ${choiceGroup('团队成员', 'member_ids', agents, item.member_ids || [])}
      ${field('最大并行数', 'max_concurrency', item.max_concurrency || 4, 'number')}${field('最大委派深度', 'max_depth', item.max_depth || 2, 'number')}
      ${selectField('委派策略', 'strategy', `<option value="model" ${item.strategy !== 'round_robin' ? 'selected' : ''}>由模型选择</option><option value="round_robin" ${item.strategy === 'round_robin' ? 'selected' : ''}>轮询</option>`)}
      ${toggleField('启用团队', 'enabled', item.enabled !== false, true)}
    </form>`, () => {
      const data = formData($('#editForm'));
      data.member_ids = $$('#editForm [name=member_ids]:checked').map(input => input.value).filter(id => id !== data.coordinator_agent_id);
      data.max_concurrency = Number(data.max_concurrency); data.max_depth = Number(data.max_depth);
      data.enabled = $('#editForm [name=enabled]').checked;
      save('agent_teams', item.id, data);
    }, true);
}

async function agentForm(item) {
  const sandboxModes = [
    { value: 'read-only', label: '只读（read-only）' },
    { value: 'workspace-write', label: '工作区可写（workspace-write）' },
  ];
  const selectedSandbox = item.sandbox_mode ?? 'read-only';
  const unsupportedSandbox = !sandboxModes.some(mode => mode.value === selectedSandbox);
  const sandboxOptions = (unsupportedSandbox ? '<option value="" selected disabled>旧配置不受支持，请重新选择</option>' : '')
    + sandboxModes.map(mode => `<option value="${mode.value}" ${selectedSandbox === mode.value ? 'selected' : ''}>${mode.label}</option>`).join('');
  const [providers, skills, knowledge, mcps, agents, teams, lsps, templateResult] = await Promise.all([
    ...['providers', 'skills', 'knowledge', 'mcp_servers', 'agents', 'agent_teams', 'lsp_servers'].map(load),
    api('/api/agent-templates'),
  ]);
  const templates = templateResult.data;
  const tools = [
    { id: 'knowledge_search', name: '知识检索' }, { id: 'list_files', name: '列目录' }, { id: 'read_file', name: '读文件' },
    { id: 'search_code', name: '代码搜索' }, { id: 'write_file', name: '写文件' }, { id: 'apply_patch', name: '应用补丁' },
    { id: 'restore_file', name: '恢复文件' }, { id: 'run_shell', name: 'Shell' }, { id: 'run_tests', name: '运行测试' },
    { id: 'git_status', name: 'Git 状态' }, { id: 'git_diff', name: 'Git 差异' }, { id: 'git_log', name: 'Git 日志' },
    { id: 'git_branch', name: 'Git 分支' }, { id: 'git_stage', name: 'Git 暂存' }, { id: 'git_commit', name: 'Git 提交' }, { id: 'review', name: '代码审查' },
    { id: 'code_index', name: '代码索引' }, { id: 'code_symbols', name: '符号查询' }, { id: 'find_references', name: '引用查找' },
    { id: 'call_graph', name: '调用图' }, { id: 'dependency_graph', name: '依赖图' }, { id: 'lsp_request', name: 'LSP 查询' },
    { id: 'git_clone', name: 'Git Clone' }, { id: 'git_fetch', name: 'Git Fetch' }, { id: 'git_push', name: 'Git Push' },
    { id: 'git_merge', name: 'Git Merge' }, { id: 'git_merge_abort', name: '中止 Merge' },
    { id: 'github_create_pr', name: '创建 PR' }, { id: 'github_ci_status', name: 'CI 状态' }, { id: 'github_review_comment', name: 'PR Review 评论' },
    { id: 'skill_read_file', name: '读取 Skill 包文件' }, { id: 'skill_run_script', name: '执行 Skill 脚本' }, { id: 'browser', name: '浏览器 / 截图' },
  ];
  const defaultPolicy = { default: 'inherit', tools: { write_file: 'ask', apply_patch: 'ask', restore_file: 'ask', run_shell: 'ask', run_tests: 'ask', git_branch: 'ask', git_stage: 'ask', git_commit: 'ask', git_clone: 'ask', git_fetch: 'ask', git_push: 'ask', git_merge: 'ask', git_merge_abort: 'ask', github_create_pr: 'ask', github_review_comment: 'ask', skill_run_script: 'ask', browser: 'ask', 'mcp:*': 'ask' } };
  modal(item.id ? '编辑智能体' : '新建智能体', `
    <form id="editForm" class="form-layout">
      <section class="form-section control-full"><header><h3>身份与模型</h3><p>定义智能体的职责和推理模型。</p></header></section>
      ${field('名称', 'name', item.name)}${field('描述', 'description', item.description)}
      ${selectField('角色模板', 'role_template', templates.map(template => `<option value="${template.id}" ${(item.role_template || 'general') === template.id ? 'selected' : ''}>${esc(template.name)} · ${esc(template.description)}</option>`).join(''), true, '角色模板作为系统提示词的受控补充，不会覆盖你的自定义提示词。')}
      ${selectField('所属智能体团队', 'team_id', `<option value="">不使用团队</option>${teams.map(team => `<option value="${team.id}" ${item.team_id === team.id ? 'selected' : ''}>${esc(team.name)}</option>`).join('')}`, true, '启用团队后，会合并团队成员作为可委派子智能体。')}
      ${selectField('模型提供方', 'provider_id', providers.map(value => `<option value="${value.id}" ${item.provider_id === value.id ? 'selected' : ''}>${esc(value.name)}</option>`).join(''))}
      ${field('模型名称', 'model', item.model || providers[0]?.default_model || '')}
      ${field('动态模型路由 JSON', 'model_routes', JSON.stringify(item.model_routes || [], null, 2), 'textarea', true, '按 priority 从高到低匹配 pattern 或 keywords；每项可指定 provider_id 和 model。')}
      ${field('故障回退模型 JSON', 'fallback_models', JSON.stringify(item.fallback_models || [], null, 2), 'textarea', true, '格式：[ { "provider_id": "...", "model": "..." } ]')}
      ${field('系统提示词', 'system_prompt', item.system_prompt || '你是一个可靠的智能体。', 'textarea', true)}
      ${field('Temperature', 'temperature', item.temperature ?? 0.2, 'number')}${field('最大工具轮次', 'max_tool_rounds', item.max_tool_rounds || 6, 'number')}
      ${selectField('推理强度', 'reasoning_effort', ['low','medium','high','xhigh'].map(value => `<option value="${value}" ${(item.reasoning_effort || 'medium') === value ? 'selected' : ''}>${value}</option>`).join(''))}${toggleField('并行工具调用', 'parallel_tools', item.parallel_tools !== false)}
      <section class="form-section control-full"><header><h3>能力装配</h3><p>选择这个智能体可以访问的能力。</p></header></section>
      ${choiceGroup('技能', 'skill_ids', skills, item.skill_ids)}
      ${choiceGroup('知识库', 'knowledge_ids', knowledge, item.knowledge_ids)}
      ${choiceGroup('MCP 服务', 'mcp_server_ids', mcps, item.mcp_server_ids)}
      ${choiceGroup('LSP 服务', 'lsp_server_ids', lsps, item.lsp_server_ids || [])}
      ${choiceGroup('内置工具', 'builtin_tools', tools, item.builtin_tools || [])}
      ${choiceGroup('可委派子智能体', 'subagent_ids', agents.filter(agent => agent.id !== item.id), item.subagent_ids || [])}
      ${field('最大并行子智能体', 'max_concurrent_subagents', item.max_concurrent_subagents || 4, 'number')}${field('最大委派深度', 'max_subagent_depth', item.max_subagent_depth || 2, 'number')}
      <section class="form-section control-full"><header><h3>记忆与工具策略</h3><p>长期记忆按用户、项目和会话分层；工具策略支持 allow / ask / deny / inherit。</p></header></section>
      ${field('记忆项目 ID', 'memory_project_id', item.memory_project_id || 'default')}${field('记忆用户 ID', 'memory_user_id', item.memory_user_id || 'default')}
      ${field('工具策略 JSON', 'tool_policy', JSON.stringify(item.tool_policy || defaultPolicy, null, 2), 'textarea', true)}
      ${toggleField('启用长期记忆', 'memory_enabled', item.memory_enabled === true)}${toggleField('自动沉淀任务经验', 'auto_memory', item.auto_memory === true)}
      <section class="form-section control-full"><header><h3>执行权限与沙箱</h3><p>沙箱模式不会自动开启 Shell、自动批准或启动沙箱服务。</p></header></section>
      ${selectField('沙箱模式', 'sandbox_mode', sandboxOptions, true, '只读：容器不能写入工作区；工作区可写：容器可修改工作区文件。普通命令禁止联网；Git 远端操作需要单独启用 broker 的受控网络。MCP 和浏览器不受 Shell 沙箱隔离。旧配置未指定模式时，保存会设为只读；不支持 danger-full-access。')}
      ${toggleField('允许执行 Shell', 'allow_shell', item.allow_shell === true)}${toggleField('允许浏览器操作', 'allow_browser', item.allow_browser === true)}${toggleField('自动批准写入、Shell 和 MCP', 'auto_approve', item.auto_approve === true)}${toggleField('启用智能体', 'enabled', item.enabled !== false)}
    </form>`, () => {
      const data = formData($('#editForm'));
      if (!sandboxModes.some(mode => mode.value === data.sandbox_mode)) {
        toast('请选择有效的沙箱模式：只读或工作区可写', true);
        return;
      }
      try {
        for (const name of ['skill_ids', 'knowledge_ids', 'mcp_server_ids', 'lsp_server_ids', 'builtin_tools', 'subagent_ids']) {
          data[name] = $$(`#editForm [name=${name}]:checked`).map(input => input.value);
        }
        data.model_routes = JSON.parse(data.model_routes || '[]');
        data.fallback_models = JSON.parse(data.fallback_models || '[]');
        data.tool_policy = JSON.parse(data.tool_policy || '{}');
        data.temperature = Number(data.temperature);
        data.max_tool_rounds = Number(data.max_tool_rounds);
        data.max_concurrent_subagents = Number(data.max_concurrent_subagents);
        data.max_subagent_depth = Number(data.max_subagent_depth);
        data.allow_shell = $('#editForm [name=allow_shell]').checked;
        data.allow_browser = $('#editForm [name=allow_browser]').checked;
        data.auto_approve = $('#editForm [name=auto_approve]').checked;
        data.memory_enabled = $('#editForm [name=memory_enabled]').checked;
        data.auto_memory = $('#editForm [name=auto_memory]').checked;
        data.parallel_tools = $('#editForm [name=parallel_tools]').checked;
        data.enabled = $('#editForm [name=enabled]').checked;
        save('agents', item.id, data);
      } catch (error) { toast(`JSON 格式错误：${error.message}`, true); }
    }, true);
}

function workflowForm(item) {
  const sample = {
    name: item.name || '文档问答流', description: item.description || '', enabled: item.enabled !== false,
    nodes: item.nodes || [{ id: 'input_1', type: 'input' }, { id: 'agent_1', type: 'agent', agent_id: '在此填智能体ID', prompt: '{{input}}' }, { id: 'output_1', type: 'output', template: '{{last}}' }],
    edges: item.edges || [{ source: 'input_1', target: 'agent_1' }, { source: 'agent_1', target: 'output_1' }],
  };
  modal(item.id ? '编辑工作流' : '新建工作流', `
    <form id="editForm" class="form-layout">
      ${field('名称', 'name', sample.name)}${field('描述', 'description', sample.description)}
      ${field('工作流 JSON', 'definition', JSON.stringify({ max_parallel: item.max_parallel || 4, nodes: sample.nodes, edges: sample.edges }, null, 2), 'textarea', true, '节点支持 retries、timeout；条件边使用 when: true/false；同一批就绪节点会真实并行执行。')}
      ${toggleField('启用工作流', 'enabled', sample.enabled, true)}
    </form>`, () => {
      try {
        const data = formData($('#editForm'));
        const definition = JSON.parse(data.definition);
        save('workflows', item.id, { name: data.name, description: data.description, enabled: $('#editForm [name=enabled]').checked, max_parallel: Number(definition.max_parallel || 4), nodes: definition.nodes || [], edges: definition.edges || [] });
      } catch (error) { toast(`JSON 格式错误：${error.message}`, true); }
    }, true);
  $('#editForm [name=definition]').classList.add('code-editor');
}

async function removeResource(kind, id) {
  if (!confirm('确定删除？此操作不可撤销。')) return;
  try {
    await api(`/api/resources/${kind}/${id}`, { method: 'DELETE' });
    toast('配置已删除');
    loadPage();
  } catch (error) { toast(error.message, true); }
}

function importSkill() {
  modal('导入 Skill 包', `
    <form id="uploadForm"><label class="drop-field"><input type="file" name="file" accept=".md,.zip,text/markdown,application/zip" required><span class="drop-title">选择 SKILL.md 或 ZIP 包</span><span>ZIP 可包含 scripts/、references/、assets/ 和 skill.json；导入时会校验路径与完整性。</span></label></form>`, async () => {
      try {
        await api('/api/skills/import', { method: 'POST', body: new FormData($('#uploadForm')) });
        closeModal(); toast('技能已导入'); loadPage();
      } catch (error) { toast(error.message, true); }
    }, false, '导入');
}

async function provisionRagflow(id) {
  try {
    toast('正在创建 RAGFlow 数据集');
    const result = await api(`/api/knowledge/${id}/ragflow/provision`, { method: 'POST', body: '{}' });
    toast(result.created ? 'RAGFlow 数据集已创建并绑定' : '该知识库已绑定数据集');
    loadPage();
  } catch (error) { toast(error.message, true); }
}

async function showKnowledgeStatus(id) {
  try {
    const result = await api(`/api/knowledge/${id}/documents/status`);
    const documents = result.documents || [];
    modal('文档解析状态', documents.length ? `<div class="search-results">${documents.map(item => `
      <article class="search-hit"><header><span>${esc(item.name || item.source || item.id)}</span><strong>${esc(String(item.run || 'UNKNOWN'))}</strong></header>
      <div class="search-source">片段 ${Number(item.chunk_count || item.chunks || 0)} · Token ${Number(item.token_count || 0)}</div>
      <p>${esc(item.progress_msg || (result.backend === 'ragflow' ? 'RAGFlow 异步处理状态' : '本地索引已提交'))}</p></article>`).join('')}</div>` : '<div class="state-inline"><p>暂无文档状态。</p></div>', null, true);
  } catch (error) { toast(error.message, true); }
}

function uploadDoc(id) {
  const knowledge = cache.knowledge?.find(item => item.id === id) || {};
  const isRagflow = knowledge.backend === 'ragflow';
  modal('上传知识文档', `
    <form id="uploadForm"><label class="drop-field"><input type="file" name="file" required><span class="drop-title">选择知识文档</span><span>${isRagflow ? '文件将转发到 RAGFlow，并异步解析和建立索引。' : '文档会被分块、向量化并写入本地 Milvus。'}</span></label></form>`, async () => {
    const button = $('#modalSave');
    try {
      button.disabled = true; button.textContent = isRagflow ? '提交解析中' : '向量化中';
      const result = await api(`/api/knowledge/${id}/documents`, { method: 'POST', body: new FormData($('#uploadForm')) });
      closeModal();
      toast(result.status === 'processing' ? `文档已提交，解析状态：${result.run || 'UNSTART'}` : `已写入 ${result.chunks} 个片段`);
      loadPage();
    } catch (error) { button.disabled = false; button.textContent = '上传'; toast(error.message, true); }
  }, false, '上传');
}

function testKnowledge(id) {
  modal('测试 RAG 检索', `<form id="searchForm" class="form-layout">${field('查询内容', 'query', '', 'textarea', true, '执行向量和关键词混合召回，再使用模型重排序。')}</form>`, async () => {
    const query = formData($('#searchForm')).query.trim();
    if (!query) return;
    const button = $('#modalSave');
    try {
      button.disabled = true; button.textContent = '检索中';
      const result = await api('/api/knowledge/search', { method: 'POST', body: JSON.stringify({ query, knowledge_ids: [id], limit: 6 }) });
      modal('检索结果', result.data.length ? `
        <div class="search-results">${result.data.map((entry, index) => `
          <article class="search-hit"><header><span>来源 ${index + 1}</span><strong>${Number(entry.score || 0).toFixed(4)}</strong></header><div class="search-source">${esc(entry.source)} #片段${Number(entry.position) + 1}<span>${esc(entry.retrieval || 'hybrid')}</span></div><p>${esc(entry.content)}</p></article>`).join('')}</div>` : '<div class="state-inline"><p>没有找到相关内容。</p></div>', null, true);
    } catch (error) { button.disabled = false; button.textContent = '检索'; toast(error.message, true); }
  }, false, '检索');
}

async function testMcp(id) {
  toast('正在连接 MCP');
  try {
    const result = await api(`/api/mcp_servers/${id}/test`, { method: 'POST' });
    modal('MCP 连接成功', `<div class="result-summary"><strong>${result.tools.length}</strong><span>个可用工具 · 协议 ${esc(result.protocol_version || '未知')}</span></div><div class="result-block"><span>服务能力</span><pre class="code-output">${esc(JSON.stringify(result.capabilities || {}, null, 2))}</pre></div><div class="result-block"><span>工具</span><pre class="code-output">${esc(JSON.stringify(result.tools, null, 2))}</pre></div>`, null, true);
  } catch (error) { toast(error.message, true); }
}

async function testProvider(id) {
  toast('正在请求模型');
  try {
    const result = await api(`/api/providers/${id}/test`, { method: 'POST', body: '{}' });
    modal('模型连接成功', `
      <div class="result-grid"><div><span>提供方</span><strong>${esc(result.provider_type)}</strong></div><div><span>模型</span><strong>${esc(result.model)}</strong></div></div>
      <div class="result-block"><span>兼容端点</span><code>${esc(result.base_url)}</code></div>
      <div class="result-block"><span>模型响应</span><pre class="code-output">${esc(result.response)}</pre></div>`);
  } catch (error) { toast(error.message, true); }
}

function runWorkflow(id) {
  modal('运行工作流', `<form id="runForm" class="form-layout">${field('输入内容', 'input', '', 'textarea', true)}</form>`, async () => {
    const button = $('#modalSave');
    try {
      button.disabled = true; button.textContent = '运行中';
      const result = await api(`/api/workflows/${id}/run`, { method: 'POST', body: JSON.stringify({ input: formData($('#runForm')).input }) });
      modal(result.status === 'completed' ? '运行完成' : '运行失败', `
        <div class="result-block"><span>输出</span><pre class="code-output">${esc(typeof result.output === 'string' ? result.output : JSON.stringify(result.output, null, 2))}</pre></div>
        <div class="trace-list"><h3>节点记录</h3>${result.trace.map(entry => `<article class="trace-entry"><header><strong>${esc(entry.node_id)}</strong><span>${esc(entry.type)}</span></header><pre>${esc(typeof entry.output === 'string' ? entry.output : JSON.stringify(entry.output, null, 2))}</pre></article>`).join('')}</div>`, null, true);
    } catch (error) { button.disabled = false; button.textContent = '运行'; toast(error.message, true); }
  }, false, '运行');
}

function richText(value) {
  const blocks = [];
  let text = esc(value).replace(/```([\s\S]*?)```/g, (_, code) => {
    const token = `CODEBLOCK${blocks.length}TOKEN`;
    blocks.push(`<pre class="message-code"><code>${code.trim()}</code></pre>`);
    return token;
  });
  text = text.replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>');
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/\n/g, '<br>');
  blocks.forEach((block, index) => { text = text.replace(`CODEBLOCK${index}TOKEN`, block); });
  return text;
}

function threadStatus(status) {
  return ({ idle: '就绪', running: '运行中', waiting_for_approval: '等待审批', error: '出错' })[status] || status || '就绪';
}

function closeSessionMenus() {
  const root = $('#sessionMenuRoot');
  if (root) { root.innerHTML = ''; delete root.dataset.threadId; }
  $$('.session-more[aria-expanded="true"]').forEach(button => button.setAttribute('aria-expanded', 'false'));
}

function toggleSessionMenu(event, threadId) {
  event.stopPropagation();
  const button = event.currentTarget;
  const root = $('#sessionMenuRoot');
  const shouldOpen = root?.dataset.threadId !== threadId;
  closeSessionMenus();
  if (!root || !shouldOpen) return;
  const archived = state.threadScope === 'archived';
  root.dataset.threadId = threadId;
  root.innerHTML = `
    <div class="session-menu" role="menu" aria-label="会话操作">
      <button type="button" role="menuitem" onclick="event.stopPropagation();renameThread('${threadId}')">重命名</button>
      <button type="button" role="menuitem" onclick="event.stopPropagation();archiveThread('${threadId}',${!archived})">${archived ? '恢复会话' : '归档会话'}</button>
      <span class="session-menu-separator" aria-hidden="true"></span>
      <button class="is-danger" type="button" role="menuitem" onclick="event.stopPropagation();deleteThread('${threadId}')">删除会话</button>
    </div>`;
  const menu = root.firstElementChild;
  button.setAttribute('aria-expanded', 'true');
  const trigger = button.getBoundingClientRect();
  const width = menu.offsetWidth;
  const height = menu.offsetHeight;
  const left = Math.max(12, Math.min(window.innerWidth - width - 12, trigger.right - width));
  const below = trigger.bottom + 6;
  const top = below + height <= window.innerHeight - 12 ? below : Math.max(12, trigger.top - height - 6);
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}

function setThreadScope(scope) {
  closeSessionMenus();
  state.threadScope = scope === 'archived' ? 'archived' : 'active';
  state.thread = null;
  loadPage();
}

function selectThread(threadId) {
  closeSessionMenus();
  state.thread = threadId;
  loadPage();
}

function getManagedThread(threadId) {
  return state.chatThreads.find(thread => thread.id === threadId);
}

function renameThread(threadId) {
  closeSessionMenus();
  const thread = getManagedThread(threadId);
  if (!thread) return;
  modal('重命名会话', `<form id="threadRenameForm" class="form-layout">${field('会话名称', 'name', thread.name, 'text', true, '最多 80 个字符。')}</form>`, async () => {
    const button = $('#modalSave');
    const name = formData($('#threadRenameForm')).name.trim();
    if (!name) { toast('会话名称不能为空', true); return; }
    button.disabled = true;
    try {
      await api(`/api/threads/${threadId}`, { method: 'PATCH', body: JSON.stringify({ name }) });
      closeModal();
      toast('会话已重命名');
      await loadPage();
    } catch (error) { button.disabled = false; toast(error.message, true); }
  }, false, '保存名称');
  const input = $('#field_name');
  window.setTimeout(() => { input?.focus(); input?.select(); }, 0);
}

async function archiveThread(threadId, archived) {
  closeSessionMenus();
  try {
    await api(`/api/threads/${threadId}`, { method: 'PATCH', body: JSON.stringify({ archived }) });
    if (state.thread === threadId) state.thread = null;
    toast(archived ? '会话已归档' : '会话已恢复');
    await loadPage();
  } catch (error) { toast(error.message, true); }
}

function deleteThread(threadId) {
  closeSessionMenus();
  const thread = getManagedThread(threadId);
  if (!thread) return;
  modal('删除会话', `
    <div class="delete-confirmation">
      <span class="delete-confirmation-mark" aria-hidden="true">!</span>
      <div><h3>永久删除“${esc(thread.name)}”？</h3><p>此会话中的全部消息和运行记录都会被删除，且无法恢复。</p></div>
    </div>`, async () => {
    const button = $('#modalSave');
    button.disabled = true;
    try {
      await api(`/api/threads/${threadId}`, { method: 'DELETE' });
      if (state.thread === threadId) state.thread = null;
      closeModal();
      toast('会话已删除');
      await loadPage();
    } catch (error) { button.disabled = false; toast(error.message, true); }
  }, false, '永久删除');
  $('#modalSave')?.classList.add('button-danger-solid');
}

async function chat() {
  const archived = state.threadScope === 'archived';
  const [agents, skills, mcps, threadResult] = await Promise.all([
    load('agents'), load('skills'), load('mcp_servers'), api(`/api/threads?archived=${archived}`),
  ]);
  const threads = threadResult.data;
  state.chatThreads = threads;
  if (!threads.some(thread => thread.id === state.thread)) state.thread = state.pendingDashboardPrompt ? null : (threads[0]?.id || null);
  const current = state.thread ? await api(`/api/threads/${state.thread}`).catch(() => null) : null;
  const approvals = state.thread
    ? (await api(`/api/threads/${state.thread}/approvals/inbox`).catch(() => ({ data: [] }))).data
    : [];
  const selectedAgent = current?.agent_id || agents[0]?.id || '';
  const selectedAgentConfig = agents.find(item => item.id === selectedAgent) || {};
  const overrides = current?.capability_overrides || {};
  state.chatCapabilities = {
    skill_ids: Array.isArray(overrides.skill_ids) ? overrides.skill_ids : (selectedAgentConfig.skill_ids || []),
    mcp_server_ids: Array.isArray(overrides.mcp_server_ids) ? overrides.mcp_server_ids : (selectedAgentConfig.mcp_server_ids || []),
  };
  state.currentThread = current;
  $('#content').innerHTML = `
    <div class="chat-studio page-enter">
      <aside class="session-browser">
        <header class="session-header">
          <div class="session-heading"><span>${archived ? '已归档' : '调试会话'}</span><strong>${threads.length}</strong></div>
          <button class="button button-primary button-small" type="button" onclick="newThread()">新对话</button>
          <div class="session-tabs" role="tablist" aria-label="会话范围">
            <button class="${archived ? '' : 'is-active'}" type="button" role="tab" aria-selected="${!archived}" onclick="setThreadScope('active')">会话</button>
            <button class="${archived ? 'is-active' : ''}" type="button" role="tab" aria-selected="${archived}" onclick="setThreadScope('archived')">归档</button>
          </div>
        </header>
        <div class="session-list">
          ${threads.length ? threads.map(thread => `
            <div class="session-item ${state.thread === thread.id ? 'is-active' : ''}">
              <button class="session-open" type="button" onclick="selectThread('${thread.id}')" aria-label="打开会话 ${esc(thread.name)}">
                <span class="session-name">${esc(thread.name)}</span><span class="session-state">${esc(threadStatus(thread.status))}</span>
              </button>
              <button class="session-more" type="button" aria-label="管理会话 ${esc(thread.name)}" aria-haspopup="menu" aria-expanded="false" onclick="toggleSessionMenu(event,'${thread.id}')"><span aria-hidden="true">•••</span></button>
            </div>`).join('') : `<div class="state-inline"><p>${archived ? '还没有已归档的会话。' : '还没有会话。'}</p></div>`}
        </div>
      </aside>
      <section class="conversation">
        <div class="conversation-top">
          <header class="conversation-bar">
            <div class="conversation-title"><span>当前会话</span><strong>${esc(current?.name || '新对话')}</strong></div>
            <label class="agent-selector"><span>运行智能体</span><select id="chatAgent" aria-label="选择智能体" onchange="changeChatAgent(this.value)">${agents.map(agent => `<option value="${agent.id}" ${selectedAgent === agent.id ? 'selected' : ''}>${esc(agent.name)}</option>`).join('')}</select></label>
          </header>
          <div class="capability-strip" id="capabilityStrip">${capabilityBarHtml(skills, mcps)}</div>
        </div>
        <div class="message-stream" id="messages" aria-live="polite">
          ${current?.messages?.length || approvals.length ? `${(current?.messages || []).map(messageHtml).join('')}${approvals.map(approvalHtml).join('')}` : `
            <div class="conversation-empty"><span class="empty-mark" aria-hidden="true">Z</span><h2>开始调试智能体</h2><p>输入任务，查看模型、工具和知识库如何协同运行。</p></div>`}
        </div>
        <footer class="prompt-dock">
          <textarea id="chatInput" aria-label="消息" rows="1" placeholder="向智能体发送任务"></textarea>
          <div class="prompt-footer"><span>Enter 发送　Shift+Enter 换行</span><button class="button button-primary" id="sendBtn" type="button" onclick="sendMessage()">发送</button></div>
        </footer>
      </section>
    </div>`;
  window.setTimeout(() => {
    if (state.page !== 'chat') return;
    bindComposer();
    if (state.pendingDashboardPrompt) {
      const prompt = state.pendingDashboardPrompt;
      state.pendingDashboardPrompt = null;
      const input = $('#chatInput');
      if (input) {
        input.value = prompt;
        input.dispatchEvent(new Event('input'));
        sendMessage();
      }
    }
  }, 0);
}

function enqueueWorkflow(id) {
  modal('后台运行工作流', `<form id="runForm" class="form-layout">${field('输入内容', 'input', '', 'textarea', true)}${field('最大尝试次数', 'max_attempts', 3, 'number')}</form>`, async () => {
    const data = formData($('#runForm')); data.max_attempts = Number(data.max_attempts);
    try {
      const result = await api(`/api/workflows/${id}/enqueue`, { method: 'POST', body: JSON.stringify(data) });
      closeModal(); toast(`工作流已进入队列：${result.task.id}`); go('tasks');
    } catch (error) { toast(error.message, true); }
  }, false, '加入队列');
}

function capabilityBarHtml(skills = state.cache.skills || [], mcps = state.cache.mcp_servers || []) {
  const selectedSkills = skills.filter(item => state.chatCapabilities.skill_ids.includes(item.id));
  const selectedMcps = mcps.filter(item => state.chatCapabilities.mcp_server_ids.includes(item.id));
  const chips = [
    ...selectedSkills.map(item => ({ ...item, kind: 'skill_ids', label: 'SKILL' })),
    ...selectedMcps.map(item => ({ ...item, kind: 'mcp_server_ids', label: 'MCP' })),
  ];
  return `
    <span class="capability-caption">当前能力</span>
    <div class="capability-chips">
      ${chips.length ? chips.map(item => `
        <span class="capability-chip"><small>${item.label}</small><strong>${esc(item.name)}</strong>
          <button type="button" aria-label="从本会话移除 ${esc(item.name)}" onclick="removeChatCapability('${item.kind}','${item.id}')">×</button>
        </span>`).join('') : '<span class="capability-empty">本会话未启用 Skill 或 MCP</span>'}
      <button class="capability-add" type="button" onclick="openCapabilityPicker()" aria-label="添加 Skill 或 MCP"><span aria-hidden="true">+</span> 添加</button>
    </div>`;
}

function renderCapabilityBar() {
  const target = $('#capabilityStrip');
  if (target) target.innerHTML = capabilityBarHtml();
}

async function ensureChatThread() {
  if (state.thread) return state.thread;
  const agent = $('#chatAgent')?.value || state.cache.agents?.[0]?.id;
  const result = await api('/api/threads', { method: 'POST', body: JSON.stringify({ name: '新对话', agent_id: agent }) });
  state.thread = result.id;
  return result.id;
}

async function saveChatCapabilities() {
  const threadId = await ensureChatThread();
  await api(`/api/threads/${threadId}`, {
    method: 'PATCH',
    body: JSON.stringify({ capability_overrides: state.chatCapabilities }),
  });
}

async function removeChatCapability(kind, id) {
  if (state.activeTurn) return toast('请先停止当前运行', true);
  const previous = [...state.chatCapabilities[kind]];
  state.chatCapabilities[kind] = previous.filter(item => item !== id);
  renderCapabilityBar();
  try {
    await saveChatCapabilities();
    toast('已从本会话移除');
  } catch (error) {
    state.chatCapabilities[kind] = previous;
    renderCapabilityBar();
    toast(error.message, true);
  }
}

function openCapabilityPicker() {
  if (state.activeTurn) return toast('请先停止当前运行', true);
  const skills = (state.cache.skills || []).filter(item => item.enabled !== false);
  const mcps = (state.cache.mcp_servers || []).filter(item => item.enabled !== false);
  modal('添加会话能力', `
    <form id="capabilityForm" class="form-layout">
      <section class="form-section control-full"><header><h3>Skill 与 MCP</h3><p>本会话选择立即生效，也可以同步为当前智能体的默认能力。</p></header></section>
      ${choiceGroup('Skills', 'skill_ids', skills, state.chatCapabilities.skill_ids)}
      ${choiceGroup('MCP 服务', 'mcp_server_ids', mcps, state.chatCapabilities.mcp_server_ids)}
      ${toggleField('同时保存为当前智能体的全局默认配置', 'save_global', false, true)}
    </form>`, async () => {
      const form = $('#capabilityForm');
      const button = $('#modalSave');
      button.disabled = true;
      const next = {
        skill_ids: $$('input[name="skill_ids"]:checked').map(input => input.value),
        mcp_server_ids: $$('input[name="mcp_server_ids"]:checked').map(input => input.value),
      };
      try {
        const saveGlobal = form.elements.save_global.checked;
        state.chatCapabilities = next;
        await saveChatCapabilities();
        if (saveGlobal) {
          const agentId = $('#chatAgent')?.value;
          const agent = (state.cache.agents || []).find(item => item.id === agentId);
          if (!agent) throw new Error('当前智能体不存在');
          const updated = await api(`/api/resources/agents/${agentId}`, {
            method: 'PUT', body: JSON.stringify({ ...agent, ...next }),
          });
          state.cache.agents = state.cache.agents.map(item => item.id === agentId ? updated : item);
        }
        closeModal();
        renderCapabilityBar();
        toast(saveGlobal ? '已更新本会话和智能体默认能力' : '已更新本会话能力');
      } catch (error) {
        button.disabled = false;
        toast(error.message, true);
      }
    }, true, '应用');
}

async function changeChatAgent(agentId) {
  if (state.activeTurn) return;
  const agent = (state.cache.agents || []).find(item => item.id === agentId);
  if (!agent) return;
  state.chatCapabilities = {
    skill_ids: [...(agent.skill_ids || [])],
    mcp_server_ids: [...(agent.mcp_server_ids || [])],
  };
  renderCapabilityBar();
  if (!state.thread) return;
  try {
    await api(`/api/threads/${state.thread}`, { method: 'PATCH', body: JSON.stringify({ agent_id: agentId }) });
  } catch (error) { toast(error.message, true); }
}

function messageHtml(message) {
  const events = message.meta?.events || [];
  const sources = message.meta?.sources || [];
  const model = message.meta?.runtime?.model;
  const assistant = message.role !== 'user';
  return `
    <article class="message-turn ${assistant ? 'assistant' : 'user'} ${message.error ? 'is-error' : ''}">
      <div class="turn-avatar" aria-hidden="true">${assistant ? 'Z' : '你'}</div>
      <div class="turn-content">
        <header><strong>${assistant ? 'Codezzn' : '你'}</strong>${model ? `<span>${esc(model)}</span>` : ''}</header>
        <div class="message-copy">${richText(message.content)}</div>
        ${events.filter(event => event.type.startsWith('tool_')).map(event => `<div class="tool-call"><span>${event.type === 'tool_started' ? '调用工具' : event.type === 'tool_failed' ? '工具失败' : '工具完成'}</span><strong>${esc(event.name)}</strong></div>`).join('')}
        ${sources.length ? `<div class="source-list"><span>知识来源</span><div>${sources.map((source, index) => `<button type="button">[${index + 1}] ${esc(source.source)} #片段${Number(source.position) + 1}</button>`).join('')}</div></div>` : ''}
      </div>
    </article>`;
}

function approvalHtml(approval) {
  const args = JSON.stringify(approval.arguments || {}, null, 2);
  return `
    <article class="message-turn assistant approval-turn" id="approval_${esc(approval.id)}">
      <div class="turn-avatar" aria-hidden="true">!</div>
      <div class="turn-content">
        <header><strong>需要审批</strong><span>${esc(approval.tool_name)}</span></header>
        <div class="approval-card">
          <div class="approval-heading"><span>工具准备执行</span><strong>${esc(approval.tool_name)}</strong></div>
          <pre>${esc(args)}</pre>
          <div class="approval-actions">
            <button class="button button-quiet button-small" type="button" onclick="resolveApproval('${approval.id}','denied')">拒绝</button>
            <button class="button button-primary button-small" type="button" onclick="resolveApproval('${approval.id}','approved')">允许并继续</button>
          </div>
        </div>
      </div>
    </article>`;
}

async function resolveApproval(approvalId, decision) {
  const card = document.getElementById(`approval_${approvalId}`);
  const buttons = card ? [...card.querySelectorAll('button')] : [];
  buttons.forEach(button => { button.disabled = true; });
  const action = decision === 'approved' ? '正在执行并继续对话' : '正在拒绝并继续对话';
  const heading = card?.querySelector('.approval-heading span');
  if (heading) heading.textContent = action;
  try {
    await api(`/api/approvals/${approvalId}`, {
      method: 'POST',
      body: JSON.stringify({ decision }),
    });
    toast(decision === 'approved' ? '已允许工具调用' : '已拒绝工具调用');
    await loadPage();
  } catch (error) {
    buttons.forEach(button => { button.disabled = false; });
    if (heading) heading.textContent = '工具准备执行';
    toast(error.message, true);
  }
}

function scrollMessages(smooth = false) {
  const messages = $('#messages');
  if (messages) messages.scrollTo({ top: messages.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
}

function bindComposer() {
  const input = $('#chatInput');
  scrollMessages();
  if (!input) return;
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); sendMessage(); }
  });
  input.addEventListener('input', () => {
    input.style.height = '54px';
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
  });
  input.focus();
}

async function newThread() {
  try {
    state.threadScope = 'active';
    const agent = $('#chatAgent')?.value || state.cache.agents?.[0]?.id;
    const result = await api('/api/threads', { method: 'POST', body: JSON.stringify({ name: '新对话', agent_id: agent }) });
    state.thread = result.id;
    if (state.page !== 'chat') go('chat'); else await loadPage();
  } catch (error) { toast(error.message, true); }
}

function createStreamTextAnimator(onFrame) {
  let target = [];
  let visible = 0;
  let visibleText = '';
  let frame = null;
  let cancelled = false;
  let waiters = [];
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

  const settle = () => {
    if (visible < target.length || frame !== null) return;
    const pending = waiters;
    waiters = [];
    pending.forEach(resolve => resolve());
  };
  const draw = () => {
    frame = null;
    if (cancelled) { settle(); return; }
    const backlog = target.length - visible;
    if (backlog <= 0) { settle(); return; }
    // Network chunks frequently contain many model deltas. Reveal them over
    // animation frames so one read() cannot collapse the whole answer into a
    // single browser paint. Large backlogs catch up without making long
    // answers feel artificially slow.
    const step = reducedMotion ? backlog : Math.max(1, Math.min(12, Math.ceil(backlog / 48)));
    const next = Math.min(target.length, visible + step);
    visibleText += target.slice(visible, next).join('');
    visible = next;
    onFrame(visibleText);
    if (visible < target.length) frame = requestAnimationFrame(draw);
    else settle();
  };
  const schedule = () => {
    if (!cancelled && frame === null && visible < target.length) frame = requestAnimationFrame(draw);
  };

  return {
    append(text) {
      if (!text || cancelled) return;
      target.push(...Array.from(text));
      schedule();
    },
    replace(text) {
      if (cancelled) return;
      const next = Array.from(text || '');
      const nextText = next.join('');
      if (!nextText.startsWith(visibleText)) {
        visible = 0;
        visibleText = '';
        onFrame('');
      }
      target = next;
      schedule();
    },
    flush() {
      if (cancelled || (visible >= target.length && frame === null)) return Promise.resolve();
      schedule();
      return new Promise(resolve => waiters.push(resolve));
    },
    cancel() {
      cancelled = true;
      if (frame !== null) cancelAnimationFrame(frame);
      frame = null;
      const pending = waiters;
      waiters = [];
      pending.forEach(resolve => resolve());
    },
  };
}

async function sendMessage() {
  let input = $('#chatInput');
  let button = $('#sendBtn');
  let agentSelect = $('#chatAgent');
  if (state.activeTurn) return stopGeneration();
  if (!input || !button || button.disabled) return;
  const content = input.value.trim();
  const agent = agentSelect?.value;
  if (!content) return;
  if (!agent) { toast('请先创建并选择智能体', true); return; }
  if (!state.thread) await ensureChatThread();
  const messages = $('#messages');
  const pendingId = `pending_${Date.now()}`;
  messages?.querySelector('.conversation-empty')?.remove();
  messages?.insertAdjacentHTML('beforeend', messageHtml({ role: 'user', content }) + `
    <article class="message-turn assistant is-pending" id="${pendingId}"><div class="turn-avatar" aria-hidden="true">Z</div><div class="turn-content"><header><strong>Codezzn</strong></header><div class="thinking-line"><span></span><span></span><span></span><b>正在检索知识并运行</b></div></div></article>`);
  input.value = '';
  input.style.height = '54px';
  const controller = new AbortController();
  const activeTurn = { controller, pendingId, cancelled: false };
  state.activeTurn = activeTurn;
  button.classList.add('is-running');
  button.setAttribute('aria-label', '停止生成');
  button.innerHTML = '<span class="stop-glyph" aria-hidden="true"></span><span>停止</span>';
  agentSelect.disabled = true;
  input.disabled = true;
  scrollMessages(true);
  try {
    const response = await fetch(`/api/threads/${state.thread}/turns/stream`, {
      method: 'POST', headers: headers(), body: JSON.stringify({ content, agent_id: agent }), signal: controller.signal,
    });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''; let answer = ''; let renderedAnswer = ''; const events = []; let streamError = ''; let resultStatus = ''; let approvalId = '';
    const renderPending = () => { const pending = document.getElementById(pendingId); if (pending) pending.querySelector('.turn-content').innerHTML = `<header><strong>Codezzn</strong></header><div class="message-copy">${richText(renderedAnswer)}</div><div class="thinking-line"><b>${esc(events.at(-1)?.status || events.at(-1)?.type || '运行中')}</b></div>`; scrollMessages(); };
    const animator = createStreamTextAnimator(text => { renderedAnswer = text; renderPending(); });
    activeTurn.animator = animator;
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const parts = buffer.split(/\n\n/);
      buffer = parts.pop();
      for (const part of parts) {
        const line = part.split('\n').find(item => item.startsWith('data:'));
        if (!line) continue;
        const event = JSON.parse(line.slice(5));
        events.push(event);
        if (event.type === 'assistant_delta') {
          const delta = event.content || '';
          answer += delta;
          animator.append(delta);
        } else {
          if (event.type === 'turn_result') {
            answer = event.content || answer;
            resultStatus = event.status || '';
            approvalId = event.approval_id || '';
            animator.replace(answer);
          }
          if (event.type === 'turn_error') streamError = event.message || event.reason || '运行失败';
          if (event.type === 'turn_cancelled') activeTurn.cancelled = true;
          renderPending();
        }
      }
      if (done) break;
    }
    if (streamError) throw new Error(streamError);
    await animator.flush();
    const pending = document.getElementById(pendingId);
    if (pending && resultStatus === 'waiting_for_approval') {
      const inbox = await api(`/api/threads/${state.thread}/approvals/inbox`).catch(() => ({ data: [] }));
      const approval = inbox.data.find(item => item.id === approvalId) || inbox.data.at(-1);
      pending.outerHTML = approval
        ? approvalHtml(approval)
        : messageHtml({ role: 'assistant', content: '工具调用正在等待审批，请刷新页面后处理。', meta: { events, usage: {}, runtime: {}, sources: [] } });
    } else if (pending) {
      pending.outerHTML = messageHtml({ role: 'assistant', content: activeTurn.cancelled ? '已停止生成。' : (answer || '模型返回了空响应。'), meta: { events, usage: {}, runtime: {}, sources: [] } });
    }
    scrollMessages(true);
  } catch (error) {
    const pending = document.getElementById(pendingId);
    const cancelled = activeTurn.cancelled || error.name === 'AbortError';
    if (pending) pending.outerHTML = messageHtml({ role: 'assistant', content: cancelled ? '已停止生成。' : `请求失败：${error.message}`, error: !cancelled });
    if (!cancelled) toast(error.message, true);
    scrollMessages(true);
  } finally {
    button = $('#sendBtn'); input = $('#chatInput'); agentSelect = $('#chatAgent');
    activeTurn.animator?.cancel();
    if (state.activeTurn === activeTurn) state.activeTurn = null;
    if (button) { button.disabled = false; button.classList.remove('is-running', 'is-stopping'); button.setAttribute('aria-label', '发送消息'); button.textContent = '发送'; }
    if (agentSelect) agentSelect.disabled = false;
    if (input) { input.disabled = false; input.focus(); }
  }
}

async function stopGeneration() {
  const active = state.activeTurn;
  if (!active || !state.thread || active.cancelled) return;
  active.cancelled = true;
  const button = $('#sendBtn');
  if (button) {
    button.classList.add('is-stopping');
    button.innerHTML = '<span class="stop-glyph" aria-hidden="true"></span><span>停止中</span>';
  }
  const cancellation = api(`/api/threads/${state.thread}/turns/active`, { method: 'DELETE' }).catch(() => null);
  active.animator?.cancel();
  active.controller.abort();
  await cancellation;
}

function openSettings() {
  modal('访问密钥', `<form id="settingsForm" class="form-layout">${field('X-Codezzn-Key', 'key', localStorage.codezznKey || '', 'password', true, '仅当服务端设置了 CODEZZN_ADMIN_KEY 时需要。')}</form>`, () => {
    localStorage.codezznKey = formData($('#settingsForm')).key;
    closeModal(); toast('访问密钥已保存'); loadPage();
  });
}

async function checkHealth() {
  const status = $('.service-state');
  try {
    const result = await fetch('/healthz').then(response => response.json());
    $('#healthText').textContent = `${result.name} 在线`;
    status?.classList.add('is-online'); status?.classList.remove('is-offline');
  } catch (error) {
    $('#healthText').textContent = '服务离线';
    status?.classList.add('is-offline'); status?.classList.remove('is-online');
  }
}

document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    if ($('.session-menu')) closeSessionMenus();
    else if ($('#modalRoot').innerHTML) closeModal();
    else toggleRail(false);
  }
});

document.addEventListener('click', closeSessionMenus);
window.addEventListener('resize', closeSessionMenus);

window.addEventListener('hashchange', () => {
  const page = location.hash.slice(1);
  if (pages.some(item => item.id === page)) go(page);
});

state.page = pages.some(item => item.id === location.hash.slice(1)) ? location.hash.slice(1) : 'dashboard';
setupRailBehavior();
nav();
$('#pageTitle').textContent = pages.find(item => item.id === state.page).label;
checkHealth();
loadSession();
loadPage();
