const pages = [
  { id: 'dashboard', label: 'Agent', short: 'HOME' },
  { id: 'chat', label: '历史', short: 'CHAT' },
  { id: 'projects', label: '项目', short: 'PROJECT' },
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
  ['工作区', ['dashboard', 'chat', 'projects', 'tasks']],
  ['构建', ['agents', 'agent_teams', 'providers', 'skills', 'mcp_servers', 'lsp_servers', 'knowledge', 'memories']],
  ['编排', ['workflows']],
];

const codezznLogoHtml = '<img src="/assets/codezzn-mark.svg?v=1" alt="">';

const navIcons = {
  dashboard: '<path d="M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z"/>',
  chat: '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.5 9 9 0 0 1-4-.9L3 21l1.9-5A9 9 0 1 1 21 11.5Z"/>',
  projects: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M3 10h18"/>',
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
  chatRuntime: null,
  projects: [], activeProjectId: null, pendingProjectTurn: null, projectDetailId: null, intentPending: false,
  filesPanelOpen: false, chatFiles: [], chatHistoryOpen: true, chatThreadFilter: '',
  chatModels: [], chatModelError: '', chatAttachments: [], chatDrafts: {}, modelSaving: false,
  approvalPending: false,
  chatQueue: [], chatInteractions: [], chatSubmitPending: false, chatUnknownSubmission: null,
  chatPollTimer: null, chatPollEpoch: 0, chatPollError: '', chatStopPending: false,
  chatEventSequences: {}, chatEvents: {}, chatMessageSignatures: {}, chatInteractionSignatures: {}, chatInteractionSubmissions: {},
  chatInteractionCollapsed: {}, chatQueueMutations: {},
  userMessageEdit: null,
  fileWorkspace: null,
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
  if (!response.ok) { const error = new Error(data.detail || `HTTP ${response.status}`); error.status = response.status; throw error; }
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

function closeModal() {
  const dialog = $('#modalRoot dialog, #modalRoot .drawer');
  if (dialog?.dataset.busy === 'true') return;
  if (dialog?.open) dialog.close();
  $('#modalRoot').innerHTML = '';
}

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

function toggleRail(open) {
  document.body.classList.toggle('rail-open', open);
  syncRailAccessibility();
  if (window.matchMedia('(max-width: 700px)').matches) {
    const target = open ? $('#workspaceRail .rail-close') : $('.chat-menu-button') || $('.menu-button');
    target?.focus();
  }
}

function syncRailAccessibility() {
  const mobile = window.matchMedia('(max-width: 700px)').matches;
  const open = document.body.classList.contains('rail-open');
  const rail = $('#workspaceRail');
  if (rail) { rail.inert = mobile && !open; rail.setAttribute('aria-hidden', String(mobile && !open)); }
  const main = $('.workspace-main');
  if (main) main.inert = mobile && open;
  $$('.menu-button').forEach(button => button.setAttribute('aria-expanded', String(mobile && open)));
}

function toggleRailExpanded() {
  document.body.classList.add('rail-expanded');
  syncRailState();
  syncRailAccessibility();
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
  document.body.classList.add('rail-expanded');
  syncRailState();
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
    location.assign('/login?logged_out=1');
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
          <button class="nav-item ${active ? 'is-active' : ''}" type="button" onclick="${id === 'chat' ? 'openChatHistory()' : `go('${id}')`}" aria-label="${esc(page.label)}" title="${esc(page.label)}" ${active ? 'aria-current="page"' : ''} ${id === 'chat' ? `id="chatHistoryToggle" aria-controls="chatHistorySubmenu" aria-expanded="${state.chatHistoryOpen}"` : ''}>
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${navIcons[id]}</svg>
            <span class="nav-label">${page.label}</span><span class="nav-short">${page.short}</span>
            ${id === 'chat' ? `<span class="nav-history-chevron" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="${state.chatHistoryOpen ? 'm6 9 6 6 6-6' : 'm9 6 6 6-6 6'}"/></svg></span>` : ''}
          </button>${id === 'chat' ? `<div id="chatHistorySubmenu" class="chat-history-submenu" ${state.chatHistoryOpen ? '' : 'hidden'}>${chatHistoryHtml()}</div>` : ''}`;
      }).join('')}
    </section>`).join('');
}

function go(page) {
  if (state.chatSubmitPending || state.intentPending || state.approvalPending || state.modelSaving || state.chatAttachments.some(item => item.status === 'uploading')) return toast('请先等待当前操作完成', true);
  if (state.page === 'chat' && page !== 'chat' && state.pendingProjectTurn) return toast('请先处理当前任务的项目确认', true);
  saveComposerDraft();
  state.page = page;
  toggleRail(false);
  document.body.classList.toggle('page-dashboard', page === 'dashboard');
  document.body.classList.toggle('page-chat', page === 'chat');
  if (location.hash !== `#${page}`) history.replaceState(null, '', `#${page}`);
  nav();
  $('#pageTitle').textContent = pages.find(item => item.id === page)?.label || page;
  return loadPage();
}

function quickCreate() {
  if (state.page === 'chat') return newThread();
  if (state.page === 'projects') return startProjectCreation();
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
  if (state.page === 'chat' && state.pendingProjectTurn) return toast('请先处理当前任务的项目确认', true);
  const content = $('#content');
  stopChatPolling();
  if (state.page !== 'chat' || (state.fileWorkspace && state.fileWorkspace.threadId !== state.thread)) disposeFileWorkspace();
  else state.fileWorkspace?.dragCleanup?.();
  document.body.classList.toggle('page-dashboard', state.page === 'dashboard');
  content.classList.toggle('viewport-chat', state.page === 'chat');
  content.innerHTML = loading();
  try {
    if (state.page === 'dashboard') return dashboard();
    if (state.page === 'chat') return chat();
    if (state.page === 'projects') return projectsPage();
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
          <div class="record-actions"><button class="button button-quiet button-small" type="button" onclick="showTask('${task.id}')">详情</button>${task.status === 'waiting' && task.result?.status === 'budget_exhausted' ? `<button class="button button-quiet button-small" type="button" onclick="continuePersistentTask('${task.id}')">继续执行</button>` : ''}${['queued','running','waiting'].includes(task.status) ? `<button class="button button-danger button-small" type="button" onclick="cancelPersistentTask('${task.id}')">取消</button>` : ''}</div>
        </article>`).join('')}</div>` : '<div class="state-page"><span class="state-code">后台队列</span><h2>还没有任务</h2><p>创建一个智能体任务，或从工作流页面选择后台运行。</p></div>'}
    </div>`;
}

async function createAgentTask() {
  const [agents, projectResult] = await Promise.all([load('agents'), api('/api/projects')]);
  modal('新建后台任务', `<form id="taskForm" class="form-layout">
    ${field('任务名称', 'name', '')}
    ${selectField('产物项目', 'project_id', '<option value="">不绑定项目</option>' + (projectResult.data || []).map(project => `<option value="${esc(project.id)}">${esc(project.name)}</option>`).join(''), true, '后台任务没有即时对话审批。文件任务请选择项目并提前配置最小工具权限；不绑定时文件保存在独立任务副本，不能声称已保存到项目。')}
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

async function continuePersistentTask(id) {
  try { await api(`/api/tasks/${encodeURIComponent(id)}/continue`, {method:'POST', body:'{}'}); toast('已在原任务上增加执行预算'); if (state.page === 'tasks') loadPage(); }
  catch (error) { toast(error.message, true); }
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
  if (kind === 'lsp_servers') facts = [item.transport === 'sandbox' ? `Docker · ${item.sandbox_server_id || item.id}` : item.transport === 'http' ? 'HTTP 代理' : item.command || '未配置命令'];
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
        ${kind === 'workflows' ? `<button class="button button-quiet button-small" type="button" onclick="runWorkflow('${item.id}')">前台运行</button><button class="button button-quiet button-small" type="button" onclick="enqueueWorkflow('${item.id}')">后台运行</button><button class="button button-quiet button-small" type="button" data-workflow-id="${esc(item.id)}" data-workflow-name="${esc(item.name)}" onclick="showWorkflowHistory(this)">历史</button>` : ''}
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
  const transport = item.transport || (item.id ? 'stdio' : 'sandbox');
  const sandboxId = item.sandbox_server_id || 'python';
  const sandboxIds = [...new Set(['python', 'typescript', sandboxId])];
  modal(item.id ? '编辑 LSP 服务' : '新建 LSP 服务', `
    <form id="editForm" class="form-layout">
      ${field('名称', 'name', item.name)}${field('语言', 'language', item.language || 'python')}
      ${selectField('执行方式', 'transport', `<option value="sandbox" ${transport === 'sandbox' ? 'selected' : ''}>Docker 沙箱（多用户推荐）</option><option value="http" ${transport === 'http' ? 'selected' : ''}>管理员 HTTP 代理</option><option value="stdio" ${transport === 'stdio' ? 'selected' : ''}>本机 stdio（仅单用户）</option>`, true, '多用户不会在主容器或 Windows 主机运行语言服务器。')}
      <div id="lspSandboxFields" class="control-full" ${transport !== 'sandbox' ? 'hidden' : ''}>
        ${selectField('沙箱服务标识', 'sandbox_server_id', sandboxIds.map(id => `<option value="${esc(id)}" ${id === sandboxId ? 'selected' : ''}>${esc(id)}</option>`).join(''), true, '必须匹配管理员 CODEZZN_LSP_SERVERS_JSON 的键，且沙箱镜像已安装对应服务。用户不能配置沙箱执行命令。')}
      </div>
      <div id="lspHttpFields" class="control-full" ${transport !== 'http' ? 'hidden' : ''}>
        ${field('代理端点', 'endpoint', item.endpoint || '', 'text', true, '仅允许管理员 CODEZZN_LSP_PROXY_URLS 白名单中的端点；Token 只从服务器环境读取。')}
      </div>
      <div id="lspStdioFields" class="control-full" ${transport !== 'stdio' ? 'hidden' : ''}>
        ${field('启动命令', 'command', item.command || 'pyright-langserver')}
        ${field('参数 JSON 数组', 'args', JSON.stringify(item.args || ['--stdio']), 'textarea', true)}
      </div>
      ${toggleField('启用服务', 'enabled', item.enabled !== false, true)}
    </form>`, () => {
      try {
        const data = formData($('#editForm')); data.enabled = $('#editForm [name=enabled]').checked;
        if (data.transport === 'stdio') {
          data.args = JSON.parse(data.args || '[]');
          if (!Array.isArray(data.args) || data.args.some(arg => typeof arg !== 'string')) throw new Error('参数必须是字符串数组');
        } else { delete data.command; delete data.args; }
        if (data.transport !== 'http') delete data.endpoint;
        if (data.transport !== 'sandbox') delete data.sandbox_server_id;
        save('lsp_servers', item.id, data);
      } catch (error) { toast(`LSP 配置错误：${error.message}`, true); }
    });
  const selector = $('#editForm [name=transport]');
  selector.addEventListener('change', () => {
    for (const [mode, id] of [['sandbox', 'lspSandboxFields'], ['http', 'lspHttpFields'], ['stdio', 'lspStdioFields']]) $(`#${id}`).hidden = selector.value !== mode;
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
    { id: 'project_list', name: '列出项目' }, { id: 'project_create', name: '创建项目' }, { id: 'project_select', name: '选择已有项目' }, { id: 'project_artifacts', name: '查看项目产物' },
    { id: 'workflow_list', name: '列出工作流' }, { id: 'workflow_get', name: '查看工作流' }, { id: 'workflow_versions', name: '查看工作流版本' }, { id: 'workflow_version_get', name: '查看工作流历史定义' }, { id: 'workflow_run_get', name: '查看运行状态' },
    { id: 'workflow_draft_create', name: '创建工作流草稿' }, { id: 'workflow_draft_update', name: '更新工作流草稿' },
    { id: 'workflow_draft_save', name: '保存工作流草稿' }, { id: 'workflow_draft_discard', name: '丢弃工作流草稿' }, { id: 'workflow_run', name: '运行工作流' },
  ];
  const defaultPolicy = { default: 'inherit', tools: { write_file: 'ask', apply_patch: 'ask', restore_file: 'ask', run_shell: 'ask', run_tests: 'ask', git_branch: 'ask', git_stage: 'ask', git_commit: 'ask', git_clone: 'ask', git_fetch: 'ask', git_push: 'ask', git_merge: 'ask', git_merge_abort: 'ask', github_create_pr: 'ask', github_review_comment: 'ask', skill_run_script: 'ask', browser: 'ask', project_create: 'ask', project_select: 'ask', workflow_draft_create: 'ask', workflow_draft_update: 'ask', workflow_draft_save: 'ask', workflow_draft_discard: 'ask', workflow_run: 'ask', 'mcp:*': 'ask' } };
  const policyForForm = { ...defaultPolicy, ...(item.tool_policy || {}), tools: { ...defaultPolicy.tools, ...(item.tool_policy?.tools || {}) } };
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
      ${field('上下文估算 Token 预算', 'context_token_budget', item.context_token_budget ?? 40000, 'number')}${toggleField('语义上下文压缩', 'semantic_compaction', item.semantic_compaction !== false)}
      ${toggleField('按需加载 MCP 工具', 'lazy_tools', item.lazy_tools ?? item.role_template === 'coding')}${toggleField('同时按需加载内置工具', 'defer_builtin_tools', item.defer_builtin_tools === true)}
      <p class="control-help control-full">预算是保守估算而非供应商精确 tokenizer；语义压缩使用当前模型并可能计费，失败回退结构化摘要。工具轮次耗尽时保存检查点并询问继续，不自动增加无限预算。并行仅用于已知只读工具。</p>
      <section class="form-section control-full"><header><h3>能力装配</h3><p>选择这个智能体可以访问的能力。</p></header></section>
      ${choiceGroup('技能', 'skill_ids', skills, item.skill_ids)}
      ${choiceGroup('知识库', 'knowledge_ids', knowledge, item.knowledge_ids)}
      ${selectField('知识检索方式', 'retrieval_mode', [['auto','自动：按任务需要检索'],['always','始终：每次回答前检索'],['off','关闭知识检索']].map(([value,label]) => `<option value="${value}" ${(item.retrieval_mode || 'auto') === value ? 'selected' : ''}>${label}</option>`).join(''), true, '自动模式由智能体判断是否需要已绑定的知识库；始终模式提前检索，关闭模式不会访问知识库。旧智能体默认使用自动模式。')}
      ${choiceGroup('MCP 服务', 'mcp_server_ids', mcps, item.mcp_server_ids)}
      ${choiceGroup('LSP 服务', 'lsp_server_ids', lsps, item.lsp_server_ids || [])}
      ${choiceGroup('内置工具', 'builtin_tools', tools, item.builtin_tools || [])}
      <p class="control-help control-full">选择“软件工程师”角色后，会自动提供编码工具：bash、read、write、edit、replace_file、glob_search、grep、todo_read、todo_write 和 done。启用“允许浏览器操作”后，还会自动提供 Browser Use 风格的页面导航、元素操作、搜索、截图和 PDF 工具。执行 Shell 仍需单独授权。</p>
      ${choiceGroup('可委派子智能体', 'subagent_ids', agents.filter(agent => agent.id !== item.id), item.subagent_ids || [])}
      ${field('最大并行子智能体', 'max_concurrent_subagents', item.max_concurrent_subagents || 4, 'number')}${field('最大委派深度', 'max_subagent_depth', item.max_subagent_depth || 2, 'number')}
      <section class="form-section control-full"><header><h3>记忆与工具策略</h3><p>长期记忆按用户、项目和会话分层；工具策略支持 allow / ask / deny / inherit。</p></header></section>
      ${field('记忆项目 ID', 'memory_project_id', item.memory_project_id || 'default')}${field('记忆用户 ID', 'memory_user_id', item.memory_user_id || 'default')}
      ${field('工具策略 JSON', 'tool_policy', JSON.stringify(policyForForm, null, 2), 'textarea', true)}
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
        data.context_token_budget = Number(data.context_token_budget);
        if (!Number.isInteger(data.context_token_budget) || data.context_token_budget < 2000 || data.context_token_budget > 2000000) throw new Error('上下文预算必须为 2000–2000000 的整数');
        for (const key of ['semantic_compaction', 'lazy_tools', 'defer_builtin_tools']) data[key] = $(`#editForm [name=${key}]`).checked;
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
  location.href = `/workflow.html${item.id ? '?id=' + encodeURIComponent(item.id) : ''}`;
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
  CodezznKnowledge.openStatus(id, knowledgeUI());
}

function chatHistoryHtml() {
  const archived = state.threadScope === 'archived';
  return `<button class="sidebar-new-thread" type="button" onclick="newThread()"><span aria-hidden="true">＋</span> 新对话</button>
    <div class="history-scope" role="tablist" aria-label="会话范围"><button type="button" role="tab" aria-selected="${!archived}" class="${archived ? '' : 'is-active'}" onclick="setThreadScope('active')">会话</button><button type="button" role="tab" aria-selected="${archived}" class="${archived ? 'is-active' : ''}" onclick="setThreadScope('archived')">归档</button></div>
    <input class="session-search" type="search" aria-label="查找历史对话" placeholder="查找对话" value="${esc(state.chatThreadFilter)}" oninput="filterChatThreads(this.value)">
    <div class="session-list">${state.chatThreads.map(thread => `<div class="session-item ${state.thread === thread.id ? 'is-active' : ''}" data-thread-id="${esc(thread.id)}" data-name="${esc(thread.name.toLowerCase())}" ${state.chatThreadFilter && !thread.name.toLowerCase().includes(state.chatThreadFilter.toLowerCase()) ? 'hidden' : ''}><button class="session-open" type="button" onclick="selectThread('${thread.id}')" aria-label="打开会话 ${esc(thread.name)}"><span class="session-name">${esc(thread.name)}</span><span class="session-state">${esc(threadStatus(thread.status))}</span></button><button class="session-more" type="button" aria-label="管理会话 ${esc(thread.name)}" aria-haspopup="menu" aria-expanded="false" onclick="toggleSessionMenu(event,'${thread.id}')">···</button></div>`).join('') || '<small class="sidebar-history-empty">暂无历史对话</small>'}</div>`;
}

function renderChatHistory() {
  const element = $('#chatHistorySubmenu');
  if (element) { element.innerHTML = chatHistoryHtml(); element.hidden = !state.chatHistoryOpen; }
}

function toggleChatHistory() { state.chatHistoryOpen = !state.chatHistoryOpen; nav(); }

function openChatHistory() {
  if (state.page === 'chat') {
    toggleChatHistory();
    $('#chatHistoryToggle')?.focus?.({ preventScroll: true });
    return;
  }
  const result = go('chat');
  // Preserve navigation guards: a pending operation must not switch pages.
  if (state.page === 'chat') {
    state.chatHistoryOpen = true;
    nav();
  }
  return result;
}

function filterChatThreads(value) {
  state.chatThreadFilter = value;
  $$('#chatHistorySubmenu .session-item').forEach(item => { item.hidden = !item.dataset.name.includes(value.toLowerCase()); });
}

function saveComposerDraft() {
  if (state.page !== 'chat' || !$('#chatInput')) return;
  state.chatDrafts[state.thread || 'new'] = { content: $('#chatInput').value, attachments: [...state.chatAttachments] };
}

function uploadDoc(id) {
  const knowledge = state.cache.knowledge?.find(item => item.id === id) || {};
  CodezznKnowledge.openUpload(id, knowledge, knowledgeUI());
}

function knowledgeUI() {
  return { api, modal, toast, esc, headers, loadPage };
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

function threadStatus(status) {
  return ({ idle: '就绪', running: '运行中', waiting_for_input: '等待回答', waiting_for_project: '选择保存项目', waiting_for_approval: '等待审批', error: '出错' })[status] || status || '就绪';
}

async function showWorkflowHistory(button) {
  const { workflowId, workflowName } = button.dataset;
  try {
    const result = await api(`/api/workflows/${encodeURIComponent(workflowId)}/versions`);
    const versions = Array.isArray(result.data) ? result.data : [];
    const rows = versions.map(item => {
      const version = Number(item.version);
      const timestamp = Number(item.created_at);
      const date = Number.isFinite(timestamp) ? new Date(timestamp * 1000).toLocaleString() : '';
      return `<article class="project-history-row"><div><strong>版本 ${version}</strong><small>${esc(date)}</small></div><button type="button" class="button button-quiet button-small" data-workflow-id="${esc(workflowId)}" data-workflow-name="${esc(workflowName)}" data-version="${version}" onclick="viewWorkflowVersion(this)">查看定义</button></article>`;
    }).join('');
    modal(`${workflowName} · 版本历史`, rows || '<p>尚无历史版本。</p>', null, true);
  } catch (error) { toast(error.message, true); }
}

async function viewWorkflowVersion(button) {
  const { workflowId, workflowName } = button.dataset;
  const version = Number(button.dataset.version);
  if (!Number.isSafeInteger(version) || version < 1) return toast('版本号无效', true);
  try {
    const definition = await api(`/api/workflows/${encodeURIComponent(workflowId)}/versions/${version}`);
    modal(`${workflowName} · 版本 ${version}`, `<pre class="project-file-preview">${esc(JSON.stringify(definition, null, 2))}</pre><div class="project-card-actions"><button type="button" class="button button-quiet button-small" data-workflow-id="${esc(workflowId)}" data-workflow-name="${esc(workflowName)}" onclick="showWorkflowHistory(this)">返回历史</button></div>`, null, true);
  } catch (error) { toast(error.message, true); }
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
  if (state.chatSubmitPending || state.intentPending || state.approvalPending || state.modelSaving || state.chatAttachments.some(item => item.status === 'uploading')) return toast('请先等待当前操作完成', true);
  if (state.pendingProjectTurn) return toast('请先处理当前任务的项目确认', true);
  closeSessionMenus();
  saveComposerDraft();
  state.threadScope = scope === 'archived' ? 'archived' : 'active';
  state.thread = null;
  if (state.page !== 'chat') go('chat'); else loadPage();
}

function selectThread(threadId) {
  if (state.chatSubmitPending || state.intentPending || state.approvalPending || state.modelSaving || state.chatAttachments.some(item => item.status === 'uploading')) return toast('请先等待当前操作完成', true);
  if (state.pendingProjectTurn) return toast('请先处理当前任务的项目确认', true);
  closeSessionMenus();
  saveComposerDraft();
  state.thread = threadId;
  if (state.page !== 'chat') go('chat'); else loadPage();
}

function getManagedThread(threadId) {
  return state.chatThreads.find(thread => thread.id === threadId);
}

let activeThreadRename = null;

function renameThread(threadId) {
  closeSessionMenus();
  if (activeThreadRename?.saving) return toast('正在保存会话名称，请稍后', true);
  activeThreadRename?.cancel();
  const thread = getManagedThread(threadId);
  if (!thread) return;
  const row = $$('.session-item').find(item => item.dataset.threadId === threadId);
  const original = row?.querySelector('.session-open');
  if (!original) return;
  const editor = document.createElement('div');
  editor.className = 'session-open session-rename';
  const input = document.createElement('input');
  input.className = 'session-rename-input';
  input.type = 'text';
  input.value = thread.name;
  input.maxLength = 80;
  input.setAttribute('aria-label', '会话名称');
  input.setAttribute('aria-describedby', 'sessionRenameHint');
  const hint = document.createElement('span');
  hint.id = 'sessionRenameHint';
  hint.className = 'session-state';
  hint.textContent = 'Enter 保存 · Esc 取消';
  editor.append(input, hint);
  original.replaceWith(editor);
  let finished = false;
  let saving = false;
  const control = { get saving() { return saving; }, cancel: () => { if (!saving) finish(); } };
  activeThreadRename = control;
  function finish(name) {
    if (finished) return;
    finished = true;
    if (name) {
      thread.name = name;
      original.querySelector('.session-name').textContent = name;
      original.setAttribute('aria-label', `打开会话 ${name}`);
      row.querySelector('.session-more')?.setAttribute('aria-label', `管理会话 ${name}`);
      if (state.thread === threadId) {
        const title = $('.conversation-title strong');
        if (title) title.textContent = name;
      }
    }
    editor.replaceWith(original);
    if (activeThreadRename === control) activeThreadRename = null;
  }
  async function save() {
    if (finished || saving || input.composing) return;
    const name = input.value.trim();
    if (!name) { toast('会话名称不能为空', true); finish(); return; }
    if (name === thread.name) { finish(); return; }
    saving = true;
    input.readOnly = true;
    hint.textContent = '保存中…';
    try {
      await api(`/api/threads/${encodeURIComponent(threadId)}`, { method: 'PATCH', body: JSON.stringify({ name }) });
      finish(name);
      toast('会话已重命名');
    } catch (error) {
      saving = false;
      input.readOnly = false;
      hint.textContent = '保存失败 · Enter 重试';
      toast(error.message, true);
      if (input.isConnected) input.focus();
    }
  }
  input.addEventListener('compositionstart', () => { input.composing = true; });
  input.addEventListener('compositionend', () => { input.composing = false; });
  input.addEventListener('keydown', event => {
    event.stopPropagation();
    if (event.isComposing || input.composing || event.keyCode === 229) return;
    if (event.key === 'Enter') { event.preventDefault(); save(); }
    if (event.key === 'Escape') { event.preventDefault(); control.cancel(); original.focus(); }
  });
  input.addEventListener('blur', save);
  editor.addEventListener('click', event => event.stopPropagation());
  input.focus();
  input.select();
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
  const previousFocus = document.activeElement;
  $('#modalRoot').innerHTML = `<dialog class="thread-delete-dialog" aria-labelledby="deleteThreadTitle" aria-describedby="deleteThreadDescription">
    <h2 id="deleteThreadTitle">删除会话“${esc(thread.name)}”？</h2>
    <p id="deleteThreadDescription">此会话中的全部消息和运行记录都会被永久删除，且无法恢复。</p>
    <footer><button type="button" class="button button-quiet" id="cancelThreadDelete" autofocus>取消</button><button type="button" class="button button-danger-solid" id="confirmThreadDelete">永久删除</button></footer>
  </dialog>`;
  const dialog = $('#modalRoot dialog');
  const cancel = $('#cancelThreadDelete');
  const button = $('#confirmThreadDelete');
  cancel.onclick = closeModal;
  dialog.addEventListener('cancel', event => { event.preventDefault(); closeModal(); });
  dialog.addEventListener('close', () => { if (previousFocus?.isConnected) previousFocus.focus(); });
  button.onclick = async () => {
    if (dialog.dataset.busy === 'true') return;
    dialog.dataset.busy = 'true';
    button.disabled = true;
    cancel.disabled = true;
    button.textContent = '删除中…';
    try {
      await api(`/api/threads/${encodeURIComponent(threadId)}`, { method: 'DELETE' });
      if (state.thread === threadId) state.thread = null;
      dialog.dataset.busy = 'false';
      closeModal();
      toast('会话已删除');
      await loadPage();
    } catch (error) {
      dialog.dataset.busy = 'false'; button.disabled = false; cancel.disabled = false;
      button.textContent = '永久删除'; toast(error.message, true);
    }
  };
  dialog.showModal();
}

function projectName(projectId) {
  return state.projects.find(item => item.id === projectId)?.name || '未选择项目';
}

async function refreshProjects() {
  const result = await api('/api/projects');
  state.projects = Array.isArray(result.data) ? result.data : [];
  return state.projects;
}

function projectChipHtml() {
  return `<button class="project-active-chip" type="button" onclick="openProjectPicker('activate')" aria-label="选择当前项目">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
    <span>${esc(projectName(state.activeProjectId))}</span><span aria-hidden="true">⌄</span>
  </button>`;
}

function renderProjectChip() {
  const target = $('#projectChip');
  if (target) target.innerHTML = projectChipHtml();
}

async function setActiveProject(projectId) {
  const threadId = await ensureChatThread();
  await api(`/api/threads/${encodeURIComponent(threadId)}`, {
    method: 'PATCH', body: JSON.stringify({ active_project_id: projectId }),
  });
  state.activeProjectId = projectId;
  if (state.currentThread) state.currentThread.active_project_id = projectId;
  await refreshChatRuntime();
  renderProjectChip();
  if (state.page === 'chat') await refreshChatFiles();
}

function fileTreeHtml(artifacts, projectId) {
  const workspace = ensureFileWorkspace();
  const folder = (name, path, children, root = false) => {
    const key = `${projectId}:${path}`;
    return `<details class="chat-file-folder ${root ? 'chat-file-project-root' : ''}" data-folder-key="${esc(key)}" ${workspace.closedFolders.has(key) ? '' : 'open'} ontoggle="rememberFileFolder(this)"><summary><span class="chat-file-chevron">${fileWorkspaceIcon('chevron')}</span><span class="chat-file-folder-icon" aria-hidden="true"><span class="folder-icon-open">${fileWorkspaceIcon('folder-open')}</span><span class="folder-icon-closed">${fileWorkspaceIcon('folder')}</span></span><span class="chat-file-folder-name">${esc(name)}</span><button type="button" class="chat-file-download" data-project-id="${esc(projectId)}" data-folder-path="${esc(path)}" onclick="event.preventDefault();event.stopPropagation();downloadProjectArchive(this.dataset.projectId,this.dataset.folderPath)" aria-label="下载文件夹 ${esc(name)}">${fileWorkspaceIcon('download')}</button></summary><div class="chat-file-children">${children}</div></details>`;
  };
  const root = { directories: new Map(), files: [] };
  for (const artifact of artifacts) {
    const parts = String(artifact.path || '').split('/').filter(Boolean);
    if (!parts.length) continue;
    let node = root;
    for (const name of parts.slice(0, -1)) {
      if (!node.directories.has(name)) node.directories.set(name, { directories: new Map(), files: [] });
      node = node.directories.get(name);
    }
    node.files.push({ ...artifact, name: parts.at(-1) });
  }
  const render = (node, parentPath = '') => `${[...node.directories].sort(([a], [b]) => a.localeCompare(b)).map(([name, child]) => {
    const folderPath = parentPath ? `${parentPath}/${name}` : name;
    return folder(name, folderPath, render(child, folderPath));
  }).join('')}
    ${node.files.sort((a, b) => a.name.localeCompare(b.name)).map(item => `
    <div class="chat-file-row"><button type="button" class="chat-file-open" data-project-id="${esc(projectId)}" data-artifact-id="${esc(item.id)}" onclick="viewProjectArtifact(this.dataset.projectId,this.dataset.artifactId)" title="查看 ${esc(item.path)}" aria-label="查看 ${esc(item.path)}"><span aria-hidden="true">${fileWorkspaceIcon(item.name)}</span><span>${esc(item.name)}</span></button><small>${item.size_bytes != null ? formatFileSize(item.size_bytes) : ''}</small><button type="button" class="chat-file-download" data-project-id="${esc(projectId)}" data-artifact-id="${esc(item.id)}" data-file-name="${esc(item.name)}" onclick="downloadProjectArtifact(this.dataset.projectId,this.dataset.artifactId,this.dataset.fileName)" aria-label="下载 ${esc(item.path)}">${fileWorkspaceIcon('download')}</button></div>`).join('')}`;
  return folder(projectName(projectId), '', render(root), true);
}

function fileWorkspaceIcon(name) {
  return typeof CodezznFileCode !== 'undefined' ? CodezznFileCode.icon(name) : '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M6 3h9l4 4v14H6z"/></svg>';
}

function disposeFileWorkspace() {
  const workspace = state.fileWorkspace;
  workspace?.dragCleanup?.();
  for (const tab of workspace?.tabs || []) { tab.controller?.abort(); if (tab.url) URL.revokeObjectURL(tab.url); }
  if (workspace) { state.filesPanelOpen = false; state.chatFiles = []; }
  state.fileWorkspace = null;
}

function ensureFileWorkspace() {
  if (state.fileWorkspace?.threadId !== state.thread) disposeFileWorkspace();
  if (!state.fileWorkspace) {
    let ratio = 55;
    try { ratio = Number(localStorage.getItem?.('codezzn.files.chatRatio')) || 55; } catch (_) { /* storage may be disabled */ }
    state.fileWorkspace = { threadId: state.thread, tabs: [], active: 'files', closedFolders: new Set(), treeScroll: 0, ratio: Math.max(28, Math.min(96, ratio)) };
  }
  return state.fileWorkspace;
}

function rememberFileFolder(details) {
  if (!details.isConnected) return;
  const workspace = ensureFileWorkspace(), key = details.dataset.folderKey;
  if (details.open) workspace.closedFolders.delete(key); else workspace.closedFolders.add(key);
}

function activateFileTab(key) {
  const workspace = ensureFileWorkspace();
  if (key !== 'files' && !workspace.tabs.some(tab => tab.key === key)) return;
  const body = $('#fileWorkspaceBody');
  if (workspace.active === 'files') workspace.treeScroll = body?.scrollTop || 0;
  else { const prior = workspace.tabs.find(tab => tab.key === workspace.active); if (prior) prior.scroll = body?.scrollTop || 0; }
  workspace.active = key; state.filesPanelOpen = true; renderChatFilesPanel();
}

function closeFileTab(key) {
  const workspace = ensureFileWorkspace(); const index = workspace.tabs.findIndex(tab => tab.key === key);
  if (index < 0) return;
  const tab = workspace.tabs[index]; tab.controller?.abort(); if (tab.url) URL.revokeObjectURL(tab.url);
  workspace.tabs.splice(index, 1);
  if (workspace.active === key) workspace.active = workspace.tabs[Math.min(index, workspace.tabs.length - 1)]?.key || 'files';
  renderChatFilesPanel();
}

function filePreviewHtml(tab) {
  if (tab.status === 'loading') return '<div class="file-preview-status" role="status">正在读取文件…</div>';
  if (tab.status === 'error') return `<div class="file-preview-status" role="alert"><p>${esc(tab.error)}</p><button type="button" data-file-key="${esc(tab.key)}" onclick="retryFileTab(this.dataset.fileKey)">重试读取</button><button type="button" data-file-key="${esc(tab.key)}" onclick="downloadFileTab(this.dataset.fileKey)">下载文件</button></div>`;
  if (tab.url) return `<div class="file-preview-media"><img src="${tab.url}" alt="${esc(tab.path)}"></div>`;
  if (tab.kind === 'binary') return `<div class="file-preview-status"><p>此文件不支持文本预览，请下载查看。</p><button type="button" data-file-key="${esc(tab.key)}" onclick="downloadFileTab(this.dataset.fileKey)">下载文件</button></div>`;
  if (tab.highlightedSource !== tab.content || tab.highlightedPath !== tab.path || tab.highlighted == null) {
    tab.highlighted = typeof CodezznFileCode !== 'undefined' ? CodezznFileCode.highlight(tab.content || '', tab.path) : esc(tab.content || '');
    tab.highlightedSource = tab.content; tab.highlightedPath = tab.path;
  }
  return `<pre class="file-source-preview" tabindex="0" aria-label="${esc(tab.path)} 文件内容"><code>${tab.highlighted}</code></pre>`;
}

function downloadFileTab(key) {
  const tab = ensureFileWorkspace().tabs.find(item => item.key === key); if (!tab) return;
  if (tab.projectId) return downloadProjectArtifact(tab.projectId, tab.artifactId, tab.path);
  return downloadArtifactFile({ dataset: { url: tab.downloadUrl, fileName: tab.path } });
}

function retryFileTab(key) {
  const tab = ensureFileWorkspace().tabs.find(item => item.key === key);
  if (tab) return loadFileTab(tab);
}

async function loadFileTab(tab) {
  const workspace = ensureFileWorkspace(); const threadId = state.thread;
  tab.controller?.abort(); const controller = new AbortController(); tab.controller = controller;
  if (tab.url) URL.revokeObjectURL(tab.url); tab.url = null; tab.status = 'loading'; renderChatFilesPanel();
  const current = () => state.page === 'chat' && state.thread === threadId && state.fileWorkspace === workspace && workspace.tabs.includes(tab) && tab.controller === controller;
  try {
    const image = /\.(png|jpe?g|webp|gif|avif)$/i.test(tab.path);
    const text = /\.(py|pyi|js|mjs|cjs|ts|tsx|jsx|html?|svg|css|scss|json|jsonl|md|markdown|txt|ya?ml|toml|sh|bash|ps1|sql|xml|csv|log|ini|conf|cfg|c|h|cpp|hpp|cs|java|go|rs|rb|php|vue|svelte|dockerfile)$/i.test(tab.path) || /(^|\/)(\.gitignore|\.env(?:\.example)?|Dockerfile|Makefile|LICENSE)$/i.test(tab.path);
    if (!image && !text) { tab.kind = 'binary'; tab.status = 'ready'; return; }
    if (tab.size > (image ? 20 * 1024 * 1024 : 1024 * 1024)) throw new Error('文件过大，请下载后查看');
    if (image || !tab.projectId) {
      const response = await fetch(tab.downloadUrl, { headers: headers(false), signal: controller.signal });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
      const blob = await readFilePreviewBlob(response, image ? 20 * 1024 * 1024 : 1024 * 1024);
      if (!current()) return;
      if (blob.size > (image ? 20 * 1024 * 1024 : 1024 * 1024)) throw new Error('文件过大，请下载后查看');
      if (image) { tab.url = URL.createObjectURL(new Blob([blob], {type: `image/${/jpe?g$/i.test(tab.path) ? 'jpeg' : tab.path.split('.').pop().toLowerCase()}`})); tab.kind = 'image'; }
      else { tab.content = await blob.text(); if (tab.content.includes('\0')) throw new Error('该文件不是可预览的文本文件'); tab.kind = 'text'; }
    } else {
      const result = await api(`/api/projects/${encodeURIComponent(tab.projectId)}/artifacts/${encodeURIComponent(tab.artifactId)}/content`, {signal: controller.signal});
      if (!current()) return;
      tab.content = String(result.content ?? ''); tab.kind = 'text';
    }
    if (current()) tab.status = 'ready';
  } catch (error) { if (current() && error.name !== 'AbortError') { tab.status = 'error'; tab.error = error.message; } }
  finally { if (current()) renderChatFilesPanel(); }
}

function openFileTab(item) {
  const workspace = ensureFileWorkspace(); const key = `${item.projectId || 'conversation'}:${item.artifactId}`;
  let tab = workspace.tabs.find(value => value.key === key);
  if (!tab) {
    if (workspace.tabs.length >= 20) return toast('最多同时预览 20 个文件，请先关闭部分标签', true);
    tab = {...item, key, status: 'loading'}; workspace.tabs.push(tab);
  }
  activateFileTab(key);
  if (tab.status === 'loading' && !tab.controller) return loadFileTab(tab);
}

async function readFilePreviewBlob(response, limit) {
  if (Number(response.headers?.get('content-length')) > limit) throw new Error('文件过大，请下载后查看');
  if (!response.body?.getReader) { const blob = await response.blob(); if (blob.size > limit) throw new Error('文件过大，请下载后查看'); return blob; }
  const reader = response.body.getReader(), chunks = []; let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      size += value.byteLength;
      if (size > limit) { await reader.cancel(); throw new Error('文件过大，请下载后查看'); }
      chunks.push(value);
    }
    return new Blob(chunks);
  } finally { reader.releaseLock(); }
}

function formatFileSize(bytes) {
  const size = Number(bytes);
  if (!Number.isFinite(size)) return '';
  return size < 1024 ? `${size} B` : size < 1024 * 1024 ? `${Math.ceil(size / 1024)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function renderChatFilesPanel() {
  const studio = $('.chat-studio');
  const panel = $('#chatFilesPanel');
  if (!studio || !panel) return;
  const workspace = ensureFileWorkspace();
  const visible = state.filesPanelOpen;
  const outputs = state.currentThread?.conversation_artifacts || [];
  const totalFiles = state.chatFiles.length + outputs.length;
  studio.classList.toggle('has-file-panel', visible);
  panel.hidden = !visible;
  const splitter = $('#chatFilesSplitter'); if (splitter) splitter.hidden = !visible;
  applyFileSplit(workspace.ratio, false);
  const toggle = $('#filesPanelToggle');
  if (toggle) {
    toggle.hidden = !totalFiles && !workspace.tabs.length && !visible;
    toggle.setAttribute('aria-pressed', String(visible));
    toggle.innerHTML = `<span aria-hidden="true">${fileWorkspaceIcon('file-text')}</span> Files <small>${totalFiles}</small>`;
  }
  const projectId = state.activeProjectId;
  const tab = workspace.tabs.find(item => item.key === workspace.active);
  const tabsHtml = `<header class="file-workspace-tabs" role="tablist" aria-label="文件标签"><button type="button" role="tab" aria-selected="${!tab}" aria-controls="fileWorkspaceBody" onclick="activateFileTab('files')">${fileWorkspaceIcon('file-text')}<span>Files <small>(${totalFiles})</small></span></button>${workspace.tabs.map(item => `<div class="file-workspace-tab ${item.key === workspace.active ? 'is-active' : ''}"><button type="button" role="tab" aria-selected="${item.key === workspace.active}" aria-controls="fileWorkspaceBody" data-file-key="${esc(item.key)}" title="${esc(item.path)}" onclick="activateFileTab(this.dataset.fileKey)">${fileWorkspaceIcon(item.path)}<span>${esc(item.path.split('/').at(-1))}</span></button><button type="button" data-file-key="${esc(item.key)}" onclick="closeFileTab(this.dataset.fileKey)" aria-label="关闭 ${esc(item.path.split('/').at(-1))}">${fileWorkspaceIcon('close')}</button></div>`).join('')}</header>`;
  const treeHtml = `<div class="chat-files-toolbar"><span>${totalFiles} files</span>${projectId && state.chatFiles.length ? `<button type="button" data-project-id="${esc(projectId)}" onclick="downloadProjectArchive(this.dataset.projectId)">${fileWorkspaceIcon('download')} Download all</button>` : ''}</div><div class="chat-files-tree" role="tree" aria-label="项目文件树">${!projectId ? '<div class="chat-files-empty"><p>选择一个项目，在这里查看智能体创建的文件。</p><button type="button" onclick="openProjectPicker()">选择项目</button></div>' : state.chatFiles.length ? fileTreeHtml(state.chatFiles, projectId) : '<div class="chat-files-empty"><p>这个项目还没有已保存的文件。</p></div>'}${outputs.length ? `<section class="conversation-file-list"><h3>对话产物</h3>${outputs.map(item => `<div class="chat-file-row"><button type="button" class="chat-file-open" data-artifact-id="${esc(item.id)}" onclick="openConversationFile(this.dataset.artifactId)">${fileWorkspaceIcon(item.name || item.path)}<span>${esc(item.name || item.path)}</span></button><small>${formatFileSize(item.size_bytes)}</small><button type="button" class="chat-file-download" data-url="${esc(item.download_url)}" data-file-name="${esc(item.name || item.path)}" onclick="downloadArtifactFile(this)" aria-label="下载 ${esc(item.name || item.path)}">${fileWorkspaceIcon('download')}</button></div>`).join('')}</section>` : ''}</div>`;
  const html = tabsHtml + `<div class="file-workspace-body ${tab ? 'is-preview' : ''}" id="fileWorkspaceBody" role="tabpanel">${tab ? filePreviewHtml(tab) : treeHtml}</div>`;
  if (panel._filesHtml !== html) {
    const body = $('#fileWorkspaceBody'); const same = panel.dataset.activeFile === (tab?.key || 'files'); const scroll = same ? body?.scrollTop : tab?.scroll || workspace.treeScroll;
    panel.innerHTML = html; panel._filesHtml = html; panel.dataset.activeFile = tab?.key || 'files';
    const next = $('#fileWorkspaceBody'); if (next) next.scrollTop = scroll || 0;
  }
}

function openConversationFile(artifactId) {
  const item = (state.currentThread?.conversation_artifacts || []).find(file => file.id === artifactId);
  if (!item) return toast('文件不存在或不属于当前对话', true);
  if (!/^\/api\/threads\/thr_[0-9a-f]{16}\/artifacts\/art_[0-9a-f]{16}\/download$/.test(item.download_url || '')) return toast('产物下载地址无效', true);
  return openFileTab({ artifactId: item.id, path: item.name || item.path, downloadUrl: item.download_url, size: item.size_bytes });
}

function applyFileSplit(value, persist = true) {
  const studio = $('.chat-studio'); if (!studio) return;
  const width = studio.getBoundingClientRect?.().width || 1200;
  const minimum = Math.max(28, Math.min(48, 320 / width * 100));
  const maximum = Math.max(minimum, Math.min(96, 100 - Math.min(240, width * .35) / width * 100));
  const ratio = Math.max(minimum, Math.min(maximum, Number(value) || 55));
  ensureFileWorkspace().ratio = ratio;
  studio.style.setProperty('--files-chat-ratio', `${ratio}fr`); studio.style.setProperty('--files-panel-ratio', `${100 - ratio}fr`);
  const splitter = $('#chatFilesSplitter'); if (splitter) { splitter.setAttribute('aria-valuenow', String(Math.round(ratio))); splitter.setAttribute('aria-valuetext', `${Math.round(ratio)}% chat width`); }
  if (persist) try { localStorage.setItem('codezzn.files.chatRatio', String(ratio)); } catch (_) { /* private browsing */ }
}

function resizeFilesKey(event) {
  const ratio = ensureFileWorkspace().ratio;
  const next = {ArrowLeft: ratio - 2, ArrowRight: ratio + 2, Home: 28, End: 96}[event.key];
  if (next != null) { event.preventDefault(); applyFileSplit(next); }
}

function startFilesResize(event) {
  if (event.button !== 0) return;
  event.preventDefault(); const handle = event.currentTarget, workspace = ensureFileWorkspace();
  workspace.dragCleanup?.(); handle.setPointerCapture?.(event.pointerId); document.body.classList.add('is-resizing-files');
  const move = pointer => { if (pointer.pointerId !== event.pointerId) return; const rect = $('.chat-studio')?.getBoundingClientRect(); if (rect?.width) applyFileSplit((pointer.clientX - rect.left) / rect.width * 100, false); };
  const cleanup = () => { handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', end); handle.removeEventListener('pointercancel', end); handle.removeEventListener('lostpointercapture', end); document.body.classList.remove('is-resizing-files'); workspace.dragCleanup = null; };
  const end = pointer => { if (pointer.pointerId !== event.pointerId) return; cleanup(); applyFileSplit(workspace.ratio); };
  workspace.dragCleanup = cleanup; handle.addEventListener('pointermove', move); handle.addEventListener('pointerup', end); handle.addEventListener('pointercancel', end); handle.addEventListener('lostpointercapture', end);
}

function toggleChatFiles() {
  state.filesPanelOpen = !state.filesPanelOpen;
  renderChatFilesPanel();
}

async function openChatProject(button) {
  const projectId = button.dataset.projectId;
  if (!projectId) return;
  try {
    if (state.activeProjectId !== projectId) await setActiveProject(projectId);
    state.filesPanelOpen = true;
    renderChatFilesPanel();
  } catch (error) { toast(error.message, true); }
}

async function openChatArtifact(button) {
  await viewProjectArtifact(button.dataset.projectId, button.dataset.artifactId);
}

async function refreshChatFiles() {
  const projectId = state.activeProjectId;
  const threadId = state.thread;
  if (state.fileWorkspace?.projectId !== projectId) state.chatFiles = [];
  ensureFileWorkspace().projectId = projectId;
  renderChatFilesPanel();
  if (!projectId) return;
  try {
    const result = await api(`/api/projects/${encodeURIComponent(projectId)}/artifacts`);
    if (state.page !== 'chat' || state.activeProjectId !== projectId || state.thread !== threadId) return;
    state.chatFiles = Array.isArray(result.data) ? result.data : [];
    for (const tab of ensureFileWorkspace().tabs) {
      if (tab.projectId !== projectId) continue;
      const file = state.chatFiles.find(item => item.id === tab.artifactId);
      if (!file) { tab.controller?.abort(); if (tab.url) URL.revokeObjectURL(tab.url); tab.url = null; tab.status = 'error'; tab.error = '文件已移除或暂不可用，请刷新后重试'; }
      else if (tab.version !== (file.sha256 || file.updated_at || file.size_bytes)) { tab.version = file.sha256 || file.updated_at || file.size_bytes; loadFileTab(tab); }
    }
    renderChatFilesPanel();
  } catch (error) {
    if (state.activeProjectId === projectId) toast(`项目文件加载失败：${error.message}`, true);
  }
}

async function downloadProjectArchive(projectId, folderPath = '') {
  try {
    const query = folderPath ? `?prefix=${encodeURIComponent(folderPath)}` : '';
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/artifacts/archive${query}`, { headers: headers(false) });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = folderPath ? `${folderPath.split('/').at(-1)}.zip` : `project-${projectId}.zip`;
    document.body.append(anchor); anchor.click(); anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { toast(error.message, true); }
}

function projectPickerItems(tab = 'recent', search = '') {
  const query = search.trim().toLocaleLowerCase();
  const projects = [...state.projects]
    .sort((a, b) => Number(b.updated_at || b.created_at || 0) - Number(a.updated_at || a.created_at || 0))
    .filter(item => !query || `${item.name} ${item.description || ''}`.toLocaleLowerCase().includes(query));
  const visible = tab === 'recent' ? projects.slice(0, 8) : projects;
  return visible.length ? visible.map(item => `
    <button class="project-picker-item" type="button" onclick="selectProjectFromPicker('${esc(item.id)}')">
      <span class="project-picker-thumb" aria-hidden="true">▣</span>
      <span class="project-picker-copy"><strong>${esc(item.name)}</strong><small>${esc(item.description || `项目 ID：${item.id}`)}</small></span>
      <span class="project-picker-arrow" aria-hidden="true">→</span>
    </button>`).join('') : '<div class="project-picker-empty">没有匹配的项目。可以新建一个项目。</div>';
}

function renderProjectPickerItems() {
  const list = $('#projectPickerList');
  if (!list) return;
  const tab = $('#projectPickerTabs .is-active')?.dataset.tab || 'recent';
  list.innerHTML = projectPickerItems(tab, $('#projectPickerSearch')?.value || '');
}

function switchProjectPickerTab(tab) {
  $$('#projectPickerTabs button').forEach(button => {
    const selected = button.dataset.tab === tab;
    button.classList.toggle('is-active', selected);
    button.setAttribute('aria-selected', String(selected));
  });
  renderProjectPickerItems();
}

async function openProjectPicker(purpose = 'activate') {
  try { await refreshProjects(); } catch (error) { toast(error.message, true); return; }
  state.projectPickerPurpose = purpose;
  $('#modalRoot').innerHTML = `
    <div class="project-picker-layer" onclick="if(event.target===this)closeModal()">
      <section class="project-picker" role="dialog" aria-modal="true" aria-labelledby="projectPickerTitle">
        <header class="project-picker-header">
          <span class="project-picker-header-icon" aria-hidden="true">▣</span>
          <div><h2 id="projectPickerTitle">打开项目</h2><p>选择一个项目，关联本次对话与生成的文件。</p></div>
          <button class="project-picker-close" type="button" onclick="closeModal()" aria-label="关闭项目选择">×</button>
        </header>
        <div class="project-picker-toolbar"><input id="projectPickerSearch" type="search" placeholder="搜索项目" aria-label="搜索项目" oninput="renderProjectPickerItems()"></div>
        <div class="project-picker-tabs" id="projectPickerTabs" role="tablist" aria-label="项目列表范围">
          <button type="button" class="is-active" data-tab="recent" role="tab" aria-selected="true" onclick="switchProjectPickerTab('recent')">最近</button>
          <button type="button" data-tab="all" role="tab" aria-selected="false" onclick="switchProjectPickerTab('all')">所有项目</button>
        </div>
        <div class="project-picker-list" id="projectPickerList">${projectPickerItems()}</div>
        <footer class="project-picker-footer"><button class="button button-quiet" type="button" onclick="closeModal()">取消</button><button class="button button-primary" type="button" onclick="closeModal();startProjectCreation()">+ 新建项目</button></footer>
      </section>
    </div>`;
  $('#projectPickerSearch')?.focus();
}

async function selectProjectFromPicker(projectId) {
  try {
    await setActiveProject(projectId);
    closeModal();
    if (state.projectPickerPurpose === 'pending' && state.pendingProjectTurn) {
      state.pendingProjectTurn.unresolvedTargetName = null;
      renderProjectDecision('save');
    }
    else toast(`已选择项目：${projectName(projectId)}`);
  } catch (error) { toast(error.message, true); }
}

function startProjectCreation() {
  if (state.pendingProjectTurn) return renderProjectDecision('create');
  modal('创建项目', `<form id="projectCreateForm" class="form-layout">${field('项目名称', 'name', '', 'text', true)}${field('描述（可选）', 'description', '', 'textarea', true)}</form>`, async () => {
    const data = formData($('#projectCreateForm'));
    if (!data.name.trim()) return toast('请输入项目名称', true);
    const button = $('#modalSave'); button.disabled = true;
    try {
      const project = await api('/api/projects', { method: 'POST', body: JSON.stringify({ name: data.name.trim(), description: data.description.trim() }) });
      await refreshProjects();
      if (state.page === 'chat') await setActiveProject(project.id);
      closeModal();
      toast('项目已创建');
      if (state.page === 'projects') { state.projectDetailId = project.id; await projectsPage(); }
    } catch (error) { button.disabled = false; toast(error.message, true); }
  }, false, '创建项目');
}

async function projectsPage() {
  await refreshProjects();
  const selected = state.projects.find(item => item.id === state.projectDetailId) || state.projects[0] || null;
  state.projectDetailId = selected?.id || null;
  const [artifacts, projectResources] = selected ? await Promise.all([
    api(`/api/projects/${encodeURIComponent(selected.id)}/artifacts`).then(result => result.data || []),
    api(`/api/projects/${encodeURIComponent(selected.id)}/resources`),
  ]) : [[], { workflows: [] }];
  const linkedWorkflows = Array.isArray(projectResources.workflows) ? projectResources.workflows : [];
  $('#content').innerHTML = `<div class="project-page page-enter">
    <header class="collection-header"><div><span class="overline">工作区资产</span><h1>项目</h1><p>将对话生成的真实文件归档到独立项目，按项目查看与下载。</p></div><div class="header-actions"><button class="button button-quiet" type="button" onclick="loadPage()">刷新</button><button class="button button-primary" type="button" onclick="startProjectCreation()">新建项目</button></div></header>
    <div class="project-page-layout"><aside class="project-sidebar"><h2>我的项目 <span>${state.projects.length}</span></h2>
      ${state.projects.length ? state.projects.map(item => `<button type="button" class="project-nav-item ${selected?.id === item.id ? 'is-active' : ''}" onclick="openProjectDetail('${esc(item.id)}')"><span aria-hidden="true">▣</span><span><strong>${esc(item.name)}</strong><small>${esc(item.description || item.id)}</small></span></button>`).join('') : '<p class="project-empty-note">还没有项目。创建一个项目后，Agent 就可以将产物保存进去。</p>'}
    </aside><section class="project-detail">
      ${selected ? `<header class="project-detail-head"><span class="project-detail-icon" aria-hidden="true">▣</span><div><span>PROJECT</span><h2>${esc(selected.name)}</h2><p>${esc(selected.description || '此项目尚无描述')}</p></div><button class="button button-quiet button-small" type="button" onclick="editProject('${esc(selected.id)}')">编辑</button></header>
        <div class="project-detail-meta"><span>项目 ID <code>${esc(selected.id)}</code></span><span>${artifacts.length} 个文件</span></div>
        <div class="project-artifacts"><h3>项目文件</h3>${artifacts.length ? artifacts.map(item => `<article class="project-artifact"><span class="project-artifact-icon" aria-hidden="true">${/\.(py|js|ts|tsx|jsx|html|css|json|md|txt)$/i.test(item.path) ? '⌘' : '▤'}</span><div><strong>${esc(item.path)}</strong><small>${esc(item.kind || 'file')} · ${esc(item.thread_id || '')} <span class="project-version-badge">v${Number(item.version) || 1}</span></small></div><button type="button" class="button button-quiet button-small" onclick="viewProjectArtifact('${esc(selected.id)}','${esc(item.id)}')">查看</button><button type="button" class="button button-quiet button-small" onclick="downloadProjectArtifact('${esc(selected.id)}','${esc(item.id)}',decodeURIComponent('${encodeURIComponent(item.path).replace(/'/g, '%27')}'))">下载</button><button type="button" class="button button-quiet button-small" data-project-id="${esc(selected.id)}" data-artifact-id="${esc(item.id)}" data-file-name="${esc(item.path)}" onclick="showProjectArtifactHistory(this)">历史</button></article>`).join('') : '<div class="project-empty-files"><strong>尚无文件</strong><p>在对话中选择此项目，并确认保存 Agent 的输出。</p><button type="button" class="button button-primary button-small" onclick="go(\'chat\')">开始对话</button></div>'}</div><div class="project-artifacts"><h3>关联工作流 <span>${linkedWorkflows.length}</span></h3>${linkedWorkflows.length ? linkedWorkflows.map(item => `<article class="project-artifact"><span class="project-artifact-icon" aria-hidden="true">◇</span><div><strong>${esc(item.name)}</strong><small>${esc(item.description || '')} <span class="project-version-badge">v${Number(item.version) || 1}</span></small></div><button type="button" class="button button-quiet button-small" data-kind="workflow" data-id="${esc(item.id)}" onclick="openResourceAsset(this)">打开</button></article>`).join('') : '<p class="project-empty-note">暂无关联工作流。</p>'}</div>` : '<div class="project-empty-files"><strong>创建第一个项目</strong><p>项目隔离存放代码与其他产物，方便按任务管理。</p></div>'}
    </section></div></div>`;
}

function openProjectDetail(projectId) { state.projectDetailId = projectId; projectsPage().catch(error => toast(error.message, true)); }

function editProject(projectId) {
  const project = state.projects.find(item => item.id === projectId);
  if (!project) return;
  modal('编辑项目', `<form id="projectEditForm" class="form-layout">${field('项目名称', 'name', project.name, 'text', true)}${field('描述', 'description', project.description || '', 'textarea', true)}</form>`, async () => {
    const data = formData($('#projectEditForm'));
    if (!data.name.trim()) return toast('项目名称不能为空', true);
    const button = $('#modalSave'); button.disabled = true;
    try {
      await api(`/api/projects/${encodeURIComponent(projectId)}`, { method: 'PATCH', body: JSON.stringify({ name: data.name.trim(), description: data.description.trim() }) });
      closeModal(); await projectsPage(); toast('项目已更新');
    } catch (error) { button.disabled = false; toast(error.message, true); }
  }, false, '保存');
}

async function projectArtifactResponse(projectId, artifactId) {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/download`, { headers: headers(false) });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
  return response;
}

async function viewProjectArtifact(projectId, artifactId) {
  const threadId = state.thread, fromChat = state.page === 'chat';
  let item;
  try { item = (await api(`/api/projects/${encodeURIComponent(projectId)}/artifacts`)).data.find(value => value.id === artifactId); }
  catch (error) { return toast(`读取文件列表失败：${error.message}`, true); }
  if (fromChat) {
    if (threadId !== state.thread || state.page !== 'chat') return;
    if (!item) return toast('文件不存在', true);
    return openFileTab({ projectId, artifactId, path: item.path, downloadUrl: `/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/download`, size: item.size_bytes, version: item.sha256 || item.updated_at || item.size_bytes });
  }
  if (item && /\.(png|jpe?g|webp)$/i.test(item.path)) return viewArtifactImage({ dataset: { url: `/api/projects/${projectId}/artifacts/${artifactId}/download`, fileName: item.path } });
  if (!item) return toast('文件不存在', true);
  if (!/\.(py|js|ts|tsx|jsx|html|css|json|md|txt|yaml|yml|toml|sh|ps1|sql)$/i.test(item.path)) return downloadProjectArtifact(projectId, artifactId, item.path);
  try {
    const result = await api(`/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/content`);
    modal(item.path, `<pre class="project-file-preview">${esc(result.content)}</pre>`, null, true);
  } catch (error) { toast(error.message, true); }
}

async function downloadProjectArtifact(projectId, artifactId, path) {
  try {
    const blob = await (await projectArtifactResponse(projectId, artifactId)).blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = String(path).split(/[\\/]/).pop() || 'artifact';
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { toast(error.message, true); }
}

async function showProjectArtifactHistory(button) {
  const { projectId, artifactId, fileName } = button.dataset;
  try {
    const result = await api(`/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/versions`);
    const versions = Array.isArray(result.data) ? result.data : [];
    const rows = versions.map(item => {
      const version = Number(item.version);
      const timestamp = Number(item.created_at);
      const date = Number.isFinite(timestamp) ? new Date(timestamp * 1000).toLocaleString() : '';
      const size = Number.isFinite(Number(item.size_bytes)) ? `${Number(item.size_bytes)} B` : '';
      return `<article class="project-history-row"><div><strong>版本 ${version}</strong><small>${esc(date)}${size ? ` · ${esc(size)}` : ''}${item.turn_id ? ` · 会话 ${esc(item.turn_id)}` : ''}</small></div>${item.downloadable && Number.isSafeInteger(version) && version > 0 ? `<button type="button" class="button button-quiet button-small" data-project-id="${esc(projectId)}" data-artifact-id="${esc(artifactId)}" data-version="${version}" data-file-name="${esc(fileName)}" onclick="downloadProjectArtifactVersion(this)">下载</button>` : '<span class="project-history-unavailable">无快照</span>'}</article>`;
    }).join('');
    modal(`${fileName} · 版本历史`, rows || '<p>尚无历史版本。</p>', null, true);
  } catch (error) { toast(error.message, true); }
}

async function downloadProjectArtifactVersion(button) {
  const { projectId, artifactId, fileName } = button.dataset;
  const version = Number(button.dataset.version);
  if (!Number.isSafeInteger(version) || version < 1) return toast('版本号无效', true);
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/versions/${version}/download`, { headers: headers(false) });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement('a');
    anchor.href = url;
    const name = String(fileName).split(/[\\/]/).pop() || 'artifact';
    const dot = name.lastIndexOf('.');
    anchor.download = dot > 0 ? `${name.slice(0, dot)}.v${version}${name.slice(dot)}` : `${name}.v${version}`;
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { toast(error.message, true); }
}

async function chat() {
  stopChatPolling();
  clearChatAttachmentPreviews();
  document.body.classList.add('page-chat');
  const archived = state.threadScope === 'archived';
  const [agents, skills, mcps, threadResult, modelResult, runtime] = await Promise.all([
    load('agents'), load('skills'), load('mcp_servers'), api(`/api/threads?archived=${archived}`), api('/api/chat/models').catch(error => ({ data: [], error: error.message })), api('/api/chat/runtime'), refreshProjects(),
  ]);
  const threads = threadResult.data;
  state.chatThreads = threads;
  if (!threads.some(thread => thread.id === state.thread)) state.thread = state.pendingDashboardPrompt ? null : (threads[0]?.id || null);
  const current = state.thread ? await api(`/api/threads/${state.thread}`).catch(() => null) : null;
  const approvals = state.thread
    ? (await api(`/api/threads/${state.thread}/approvals/inbox`).catch(() => ({ data: [] }))).data
    : [];
  state.chatRuntime = current ? await api(`/api/chat/runtime?thread_id=${encodeURIComponent(current.id)}`) : runtime;
  const selectedAgent = current?.agent_id || runtime.default_agent_id || agents[0]?.id || '';
  const selectedAgentConfig = agents.find(item => item.id === selectedAgent) || {};
  const overrides = current?.capability_overrides || {};
  state.chatCapabilities = {
    skill_ids: Array.isArray(overrides.skill_ids) ? overrides.skill_ids : (selectedAgentConfig.skill_ids || []),
    mcp_server_ids: Array.isArray(overrides.mcp_server_ids) ? overrides.mcp_server_ids : (selectedAgentConfig.mcp_server_ids || []),
  };
  state.currentThread = current;
  state.chatQueue = current?.queue_messages || [];
  state.chatInteractions = current?.interactions || [];
  restoreChatInteractionSubmissions(state.thread);
  state.chatMessageSignatures = {}; state.chatInteractionSignatures = {};
  state.chatUnknownSubmission = readUnknownChatSubmission(state.thread);
  syncActiveChatTurn();
  state.chatModels = modelResult.data || [];
  state.chatModelError = modelResult.error || '';
  const draft = state.chatDrafts[state.thread || 'new'] || { content: '', attachments: [] };
  state.chatAttachments = [...draft.attachments];
  state.activeProjectId = current?.active_project_id || null;
  state.chatFiles = [];
  $('#content').innerHTML = `
    <div class="chat-studio cloud-chat page-enter">
      <section class="conversation">
        <div class="conversation-top">
          <header class="conversation-bar">
            <div class="conversation-title"><button class="icon-button menu-button chat-menu-button" type="button" onclick="toggleRail(true)" aria-label="打开导航" aria-controls="workspaceRail" aria-expanded="false">${chatIcon('menu')}</button><strong>${esc(current?.name || '新对话')}</strong></div>
            <div class="conversation-header-actions"><button class="chat-files-toggle" id="filesPanelToggle" type="button" onclick="toggleChatFiles()" aria-label="切换文件面板" aria-pressed="${state.filesPanelOpen}"><span aria-hidden="true">▤</span> Files <small>0</small></button><label class="agent-selector"><span>运行智能体</span><select id="chatAgent" aria-label="选择智能体" onchange="changeChatAgent(this.value)">${agents.map(agent => `<option value="${agent.id}" ${selectedAgent === agent.id ? 'selected' : ''}>${esc(agent.name)}</option>`).join('')}</select></label></div>
          </header>
          ${assetStripHtml(current?.messages || [])}
        </div>
        <div class="message-stream" id="messages" aria-live="polite">
          ${current?.messages?.length || approvals.length || state.chatInteractions.length ? `${persistentChatTimelineHtml(current?.messages || [], state.chatInteractions)}${approvals.filter(approval => !state.chatInteractions.some(item => item.turn_id === approval.turn_id && ['question','tool_approval'].includes(item.kind) && item.payload?.tool_name === approval.tool_name)).map(approvalHtml).join('')}` : `
            <div class="conversation-empty"><span class="empty-mark" aria-hidden="true">${codezznLogoHtml}</span><h2>今天想让智能体做什么？</h2><p>分析资料、编写代码，或让工具完成任务。</p><div class="chat-suggestions"><button type="button" onclick="fillChatPrompt('请帮我分析上传的文档，提炼重点和待办事项。')">${chatIcon('file')}<span>分析文档资料<small>提炼重点、比较信息</small></span></button><button type="button" onclick="fillChatPrompt('请帮我审查这段代码，找出错误并给出修复建议。')">${chatIcon('code')}<span>编写与审查代码<small>从想法到可运行的代码</small></span></button></div></div>`}
        </div>
        <section class="chat-interaction-dock" id="chatInteractionDock" aria-label="等待你确认" hidden></section>
        <footer class="prompt-dock">
          <div class="chat-queue" id="chatQueue" aria-live="polite"></div>
          <div class="composer-attachments" id="chatAttachments" aria-live="polite"></div>
          <textarea id="chatInput" aria-label="消息" rows="2" placeholder="向智能体发送任务…">${esc(draft.content)}</textarea>
          <div class="prompt-footer"><div class="prompt-tools composer-tools"><button type="button" class="composer-action" id="attachBtn" onclick="document.getElementById('chatAttachmentInput').click()" aria-label="上传附件" title="上传文档、代码或图片">${chatIcon('attach')}</button><input type="file" id="chatAttachmentInput" aria-label="选择对话附件" multiple hidden accept=".txt,.md,.markdown,.pdf,.docx,.json,.csv,.py,.js,.ts,.tsx,.jsx,.html,.css,.yaml,.yml,.xml,.log,.sql,.sh,.png,.jpg,.jpeg,.webp" onchange="uploadChatAttachments(Array.from(this.files));this.value=''">
            <label class="composer-model">${chatIcon('model')}<select id="chatModel" aria-label="选择模型" onchange="changeChatModel(this.value)">${chatModelOptions(selectedAgentConfig)}</select></label>
            <label class="composer-permission"><select id="chatPermissionMode" aria-label="权限模式" title="权限在执行工具时检查，不能绕过沙箱或拒绝策略" onchange="changeChatPermissionMode(this.value)">${chatPermissionOptions()}</select></label>
            <button type="button" class="composer-action" onclick="openSkillCommands()" aria-label="按需使用 Skill" title="输入 /技能名 按需使用">/</button>
            <button type="button" class="composer-action" onclick="openRuntimeSettings()" aria-label="默认配置" title="用户与项目默认配置">⚙</button>
          </div><button class="composer-interrupt" id="interruptBtn" type="button" onclick="sendMessage({interrupt:true})" hidden title="停止当前任务后立即执行输入框中的新指令">立即调整</button><button class="composer-stop" id="stopBtn" type="button" onclick="stopGeneration()" hidden aria-label="停止当前任务" title="停止当前任务，保留待执行队列"><span class="stop-glyph" aria-hidden="true"></span></button><button class="button button-primary composer-send" id="sendBtn" type="button" onclick="sendMessage()" aria-label="发送消息" title="发送消息">${chatIcon('send')}</button></div>
          <div class="composer-context"><div class="project-context-bar"><div id="projectChip">${projectChipHtml()}</div></div><div class="capability-strip" id="capabilityStrip">${capabilityBarHtml(skills, mcps)}</div></div>
          <div class="attachment-error" id="chatComposerError" role="alert">${state.chatModelError ? `模型列表加载失败：${esc(state.chatModelError)}` : ''}</div>
          <div class="composer-hint" id="chatQueueHint">Enter 发送 · /技能名 按需使用 · 写入和命令执行时审批</div>
          <div id="skillCommands" class="skill-command-menu" hidden></div>
        </footer>
      </section>
      <div class="chat-files-splitter" id="chatFilesSplitter" role="separator" tabindex="0" aria-label="调整聊天与文件面板宽度" aria-orientation="vertical" aria-valuemin="28" aria-valuemax="96" aria-valuenow="55" onpointerdown="startFilesResize(event)" onkeydown="resizeFilesKey(event)" hidden></div>
      <aside class="chat-files-panel" id="chatFilesPanel" aria-label="项目文件"></aside>
    </div>`;
  renderChatFilesPanel();
  syncRailAccessibility();
  renderChatHistory();
  renderChatAttachments();
  renderChatQueue();
  applyPersistentChatInteractions();
  updateComposerControls();
  startChatPolling();
  window.setTimeout(() => {
    if (state.page !== 'chat') return;
    bindComposer();
    refreshChatFiles();
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

function chatIcon(name) {
  if (name === 'copy') return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>';
  if (name === 'edit') return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m16 3 5 5-12 12-6 1 1-6zM14 5l5 5M4 15l5 5"/></svg>';
  const paths = { attach: '<path d="m21 11-8.5 8.5a6 6 0 0 1-8.5-8.5l9-9a4 4 0 0 1 5.5 5.5l-9 9a2 2 0 0 1-2.8-2.8l8.3-8.3"/>', send: '<path d="M12 19V5m-7 7 7-7 7 7"/>', menu: '<path d="M4 6h16M4 12h16M4 18h16"/>', model: '<path d="m12 3 3 6 6 3-6 3-3 6-3-6-6-3 6-3z"/>', file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>', code: '<path d="m8 7-5 5 5 5m8-10 5 5-5 5m-3-13-2 20"/>' };
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`;
}

function chatModelOptions(agent = {}) {
  if (state.chatRuntime && state.chatRuntime.agent_id === agent?.id) agent = { ...agent, model: state.chatRuntime.model };
  const chosen = state.currentThread?.model_override || {};
  const selected = chosen.provider_id && chosen.model ? encodeURIComponent(JSON.stringify({ provider_id: chosen.provider_id, model: chosen.model })) : '';
  const groups = new Map();
  state.chatModels.forEach(model => { const label = model.provider_name || '模型提供方'; if (!groups.has(label)) groups.set(label, []); groups.get(label).push(model); });
  const unavailable = selected && !state.chatModels.some(item => item.provider_id === chosen.provider_id && item.model === chosen.model);
  return `<option value="" ${!selected ? 'selected' : ''}>${esc(agent.model || '继承智能体模型')} · 默认</option>${unavailable ? `<option value="${esc(selected)}" selected disabled>${esc(chosen.model)} · 暂不可用</option>` : ''}${[...groups].map(([name, models]) => `<optgroup label="${esc(name)}">${models.map(model => { const value = encodeURIComponent(JSON.stringify({ provider_id: model.provider_id, model: model.model })); return `<option value="${esc(value)}" ${selected === value ? 'selected' : ''}>${esc(model.model)}</option>`; }).join('')}</optgroup>`).join('')}`;
}

async function changeChatModel(value) {
  if (state.activeTurn || state.chatQueue.some(item => ['pending','dispatching'].includes(item.status)) || state.intentPending || state.approvalPending || state.pendingProjectTurn || state.modelSaving) return;
  const select = $('#chatModel');
  state.modelSaving = true; if (select) select.disabled = true; updateComposerControls();
  try {
    const id = await ensureChatThread($('#chatAgent')?.value || state.cache.agents?.[0]?.id);
    const override = value ? JSON.parse(decodeURIComponent(value)) : {};
    const updated = await api(`/api/threads/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ model_override: override }) });
    state.currentThread = { ...state.currentThread, ...updated };
    toast(value ? `当前会话已选择 ${override.model}` : '当前会话使用智能体默认模型');
  } catch (error) { toast(`模型切换失败：${error.message}`, true); }
  finally {
    state.modelSaving = false;
    if (select) { select.innerHTML = chatModelOptions((state.cache.agents || []).find(agent => agent.id === $('#chatAgent')?.value)); select.disabled = false; }
    updateComposerControls();
  }
}

function fillChatPrompt(value) { const input = $('#chatInput'); if (input && !input.disabled) { input.value = value; input.dispatchEvent(new Event('input')); input.focus(); } }

function attachmentHtml(attachment, removableIndex = null) {
  const name = attachment.name || '附件';
  const available = /^att_[0-9a-f]{16}$/.test(attachment.id || '');
  return `<span class="chat-attachment ${attachment.status === 'failed' ? 'is-error' : ''}">${attachment.kind === 'image' && available ? `<img data-attachment-preview="${attachment.id}" alt="${esc(name)}">` : chatIcon('file')}${available ? `<a href="/api/chat/attachments/${attachment.id}/download" data-attachment-id="${attachment.id}" data-file-name="${esc(name)}" onclick="event.preventDefault();downloadChatAttachment(this)" download>${esc(name)}</a>` : `<span>${esc(name)}</span>`}${attachment.status === 'uploading' ? '<small>上传中…</small>' : ''}${attachment.error ? `<small>${esc(attachment.error)}</small>` : ''}${removableIndex !== null ? `<button type="button" onclick="removeChatAttachment(${removableIndex})" aria-label="移除附件 ${esc(name)}">×</button>` : ''}</span>`;
}

const chatAttachmentPreviews = new Map();

function clearChatAttachmentPreviews() {
  for (const entry of chatAttachmentPreviews.values()) if (entry.url) URL.revokeObjectURL(entry.url);
  chatAttachmentPreviews.clear();
}

async function fetchChatAttachment(id) {
  if (!/^att_[0-9a-f]{16}$/.test(id || '')) throw new Error('附件不存在');
  const response = await fetch(`/api/chat/attachments/${id}/download`, { headers: headers(false) });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
  return response.blob();
}

async function fetchArtifactFile(url) {
  if (!/^\/api\/(?:threads\/thr_[0-9a-f]{16}|projects\/prj_[0-9a-f]{16})\/artifacts\/art_[0-9a-f]{16}\/download$/.test(url || '')) throw new Error('产物下载地址无效');
  const response = await fetch(url, { headers: headers(false) });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
  return response.blob();
}

function artifactOutputHtml(item) {
  const url = item.download_url;
  if (!url) return '';
  return `<section class="chat-output-card"><header><strong>${esc(item.name || item.path)}</strong><small>${item.storage === 'project' ? '项目文件' : '对话产物'}</small></header>${item.previewable ? `<button type="button" class="chat-output-preview" data-url="${esc(url)}" data-file-name="${esc(item.name || item.path)}" onclick="viewArtifactImage(this)"><img data-artifact-preview="${esc(url)}" alt="${esc(item.name || item.path)}"><span>查看截图</span></button>` : item.canPreview ? `<button class="button button-quiet button-small" type="button" data-url="${esc(url)}" data-file-name="${esc(item.name || item.path)}" onclick="viewArtifactImage(this)">查看截图</button>` : ''}<button class="button button-quiet button-small" type="button" data-url="${esc(url)}" data-file-name="${esc(item.name || item.path)}" onclick="downloadArtifactFile(this)">下载</button></section>`;
}

async function viewArtifactImage(button) {
  if (state.page === 'chat') {
    const project = /^\/api\/projects\/(prj_[0-9a-f]{16})\/artifacts\/(art_[0-9a-f]{16})\/download$/.exec(button.dataset.url || '');
    if (project) return viewProjectArtifact(project[1], project[2]);
    const item = (state.currentThread?.conversation_artifacts || []).find(file => file.download_url === button.dataset.url);
    return item ? openConversationFile(item.id) : toast('文件不存在或不属于当前对话', true);
  }
  try {
    const url = URL.createObjectURL(await fetchArtifactFile(button.dataset.url));
    modal(button.dataset.fileName, `<img class="artifact-image-full" src="${url}" alt="${esc(button.dataset.fileName)}">`, null, true);
    $('#modalRoot .drawer-header span').textContent = '截图预览';
    $('#modalRoot .drawer-footer button').textContent = '关闭';
    const layer = $('#modalRoot .drawer-layer');
    const observer = new MutationObserver(() => { if (!layer?.isConnected) { URL.revokeObjectURL(url); observer.disconnect(); } });
    observer.observe($('#modalRoot'), { childList: true });
  } catch (error) { toast(error.message, true); }
}

async function downloadArtifactFile(button) {
  try {
    const url = URL.createObjectURL(await fetchArtifactFile(button.dataset.url));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = button.dataset.fileName || 'artifact';
    document.body.append(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { toast(error.message, true); }
}

function hydrateChatAttachmentPreviews() {
  const images = $$('img[data-attachment-preview], img[data-artifact-preview]');
  const visible = new Set(images.map(image => image.dataset.attachmentPreview || image.dataset.artifactPreview));
  for (const [id, entry] of chatAttachmentPreviews) if (!visible.has(id)) {
    if (entry.url) URL.revokeObjectURL(entry.url);
    chatAttachmentPreviews.delete(id);
  }
  for (const image of images) {
    const id = image.dataset.attachmentPreview || image.dataset.artifactPreview;
    let entry = chatAttachmentPreviews.get(id);
    if (!entry) {
      entry = {};
      chatAttachmentPreviews.set(id, entry);
      entry.promise = (image.dataset.artifactPreview ? fetchArtifactFile(id) : fetchChatAttachment(id)).then(blob => {
        if (chatAttachmentPreviews.get(id) !== entry) return null;
        entry.url = URL.createObjectURL(blob);
        return entry.url;
      }).catch(() => null);
    }
    entry.promise.then(url => {
      if (!image.isConnected) return;
      if (url && chatAttachmentPreviews.get(id) === entry) image.src = url;
      else { image.hidden = true; image.parentElement.title = '图片预览暂不可用，可点击文件名重试下载'; }
    });
  }
}

async function downloadChatAttachment(link) {
  try {
    const url = URL.createObjectURL(await fetchChatAttachment(link.dataset.attachmentId));
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = link.dataset.fileName || 'attachment';
    document.body.append(anchor); anchor.click(); anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { toast(`附件下载失败：${error.message}`, true); }
}

function renderChatAttachments() {
  const container = $('#chatAttachments');
  if (container) { container.innerHTML = state.chatAttachments.map((item, index) => attachmentHtml(item, index)).join(''); container.hidden = !state.chatAttachments.length; }
  hydrateChatAttachmentPreviews(); saveComposerDraft(); updateComposerControls();
}

function removeChatAttachment(index) {
  if (state.chatSubmitPending || state.chatAttachments[index]?.status === 'uploading') return;
  state.chatAttachments.splice(index, 1); renderChatAttachments();
}

async function uploadChatAttachments(files) {
  if (state.chatSubmitPending || state.modelSaving) return toast('请等待当前提交完成，再上传附件', true);
  const errorBox = $('#chatComposerError'); if (errorBox) errorBox.textContent = '';
  for (const file of files) {
    if (state.chatAttachments.length >= 8) { if (errorBox) errorBox.textContent = '一次最多添加 8 个附件'; break; }
    if (!file.size || file.size > 10 * 1024 * 1024) { if (errorBox) errorBox.textContent = `${file.name}：文件不能为空，且不能超过 10 MB`; continue; }
    const item = { name: file.name, size: file.size, status: 'uploading' }; state.chatAttachments.push(item); renderChatAttachments();
    const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 60000);
    try { const body = new FormData(); body.append('file', file); const result = await api('/api/chat/attachments', { method: 'POST', body, signal: controller.signal }); Object.assign(item, result, { status: 'ready' }); }
    catch (error) { item.status = 'failed'; item.error = error.name === 'AbortError' ? '上传超时，请重新选择文件' : error.message; }
    finally { clearTimeout(timeout); renderChatAttachments(); }
  }
}

function updateComposerControls() {
  const running = !!state.activeTurn;
  const configurationLocked = running || state.chatQueue.some(item => ['pending','dispatching'].includes(item.status));
  const busy = state.chatSubmitPending || state.modelSaving || state.chatAttachments.some(item => item.status === 'uploading');
  const hasContent = !!$('#chatInput')?.value.trim() || state.chatAttachments.some(item => item.status === 'ready');
  const button = $('#sendBtn');
  if (button) { button.disabled = busy || !!state.chatUnknownSubmission || !hasContent; button.setAttribute?.('aria-label', running ? '排队发送消息' : '发送消息'); button.title = running ? '排队发送，当前任务完成后执行' : '发送消息'; }
  const model = $('#chatModel'); if (model) model.disabled = configurationLocked || busy;
  const attach = $('#attachBtn'); if (attach) attach.disabled = state.chatSubmitPending || state.modelSaving;
  const agentSelect = $('#chatAgent'); if (agentSelect) agentSelect.disabled = configurationLocked || busy;
  const input = $('#chatInput'); if (input) input.disabled = false;
  const stop = $('#stopBtn'); if (stop) { stop.hidden = !running; stop.disabled = state.chatStopPending; stop.title = state.chatStopPending ? '正在请求停止…' : '停止当前任务，保留待执行队列'; }
  const interrupt = $('#interruptBtn'); if (interrupt) { interrupt.hidden = !running; interrupt.disabled = busy || !!state.chatUnknownSubmission || !hasContent || state.chatStopPending; }
  const hint = $('#chatQueueHint'); if (hint) hint.textContent = running ? '运行中可继续输入 · Enter 排队 · 立即调整会先停止当前任务' : 'Enter 发送 · Shift+Enter 换行 · 可拖入附件';
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
          <button type="button" aria-label="移除显式绑定 ${esc(item.name)}" title="移除显式绑定；自动发现开启时仍可按需使用" onclick="removeChatCapability('${item.kind}','${item.id}')">×</button>
        </span>`).join('') : `<span class="capability-empty">${state.chatRuntime?.skill_discovery === 'auto' ? 'Skill 自动发现 · 输入 / 按需使用' : '可输入 / 查看技能，或添加扩展'}</span>`}
      <button class="capability-add" type="button" onclick="openCapabilityPicker()" aria-label="添加 Skill 或 MCP"><span aria-hidden="true">+</span> 添加</button>
    </div>`;
}

function renderCapabilityBar() {
  const target = $('#capabilityStrip');
  if (target) target.innerHTML = capabilityBarHtml();
}

function chatPermissionOptions() {
  const selected = state.currentThread?.capability_overrides?.permission_mode || '';
  const effective = state.chatRuntime?.permission_mode || 'default';
  const labels = { default: '逐次审批', acceptEdits: '自动接受文件编辑', plan: '只读计划' };
  return [['', `继承：${labels[effective] || effective}`], ...Object.entries(labels)].map(([value, label]) =>
    `<option value="${value}" ${selected === value ? 'selected' : ''}>${esc(label)}</option>`).join('');
}

async function refreshChatRuntime() {
  const thread = state.thread;
  const result = await api(`/api/chat/runtime${thread ? `?thread_id=${encodeURIComponent(thread)}` : ''}`);
  if (thread !== state.thread) return;
  state.chatRuntime = result;
  const control = $('#chatPermissionMode'); if (control) control.innerHTML = chatPermissionOptions();
  renderCapabilityBar();
}

async function changeChatPermissionMode(value) {
  if (state.activeTurn || state.chatSubmitPending) return toast('请先完成或停止当前任务，再切换权限模式', true);
  try {
    const thread = await ensureChatThread();
    const overrides = { ...(state.currentThread?.capability_overrides || {}) };
    if (value) overrides.permission_mode = value; else delete overrides.permission_mode;
    const updated = await api(`/api/threads/${encodeURIComponent(thread)}`, { method: 'PATCH', body: JSON.stringify({ capability_overrides: overrides }) });
    if (state.thread !== thread) return;
    state.currentThread = { ...state.currentThread, ...updated };
    await refreshChatRuntime(); toast('权限模式已更新；沙箱和拒绝策略保持生效');
  } catch (error) { toast(error.message, true); const control = $('#chatPermissionMode'); if (control) control.innerHTML = chatPermissionOptions(); }
}

function openRuntimeSettings() {
  const current = state.chatRuntime || {};
  modal('默认运行配置', `<form id="runtimeSettingsForm" class="form-layout">
    <p class="control-help control-full">无需先创建智能体。默认 Codezzn 会继承用户配置、项目配置和会话覆盖；自定义智能体保留原权限。修改默认配置只影响之后开始的回合，不批准已暂停的操作。</p>
    ${selectField('保存范围', 'scope', `<option value="user">我的用户默认配置</option>${state.activeProjectId ? '<option value="project">当前项目配置</option>' : ''}`, true)}
    ${selectField('默认模型', 'default_model', `<option value="">保持现有默认模型</option>${(state.chatModels || []).map(model => `<option value="${esc(encodeURIComponent(JSON.stringify({provider_id:model.provider_id,model:model.model})))}">${esc(model.provider_name || model.provider_id)} / ${esc(model.model)}</option>`).join('')}`, true, '保存后由新的默认对话继承；当前会话已有的模型覆盖仍优先。')}
    ${selectField('默认权限', 'permission_mode', [['default','逐次审批：文件写入与命令都需确认'],['acceptEdits','自动接受工作区文件编辑；命令仍需确认'],['plan','只读计划：不执行写入和命令']].map(([v,l]) => `<option value="${v}" ${current.permission_mode === v ? 'selected' : ''}>${l}</option>`).join(''), true)}
    ${selectField('Skill 发现', 'skill_discovery', `<option value="auto" ${current.skill_discovery === 'auto' ? 'selected' : ''}>自动发现我的已启用技能，按需读取</option><option value="off" ${current.skill_discovery !== 'auto' ? 'selected' : ''}>仅使用显式绑定的技能</option>`, true)}
    <p class="control-help control-full">自动发现仅限当前账号安装的技能及当前项目范围。脚本依赖不会自动安装；Skill 不能提升工具权限或访问其他用户数据。</p>
  </form>`, async () => {
    const form = $('#runtimeSettingsForm');
    const url = form.elements.scope.value === 'project' ? `/api/projects/${encodeURIComponent(state.activeProjectId)}/runtime-settings` : '/api/chat/runtime/settings';
    try {
      const model = form.elements.default_model.value ? JSON.parse(decodeURIComponent(form.elements.default_model.value)) : {};
      await api(url, { method: 'PATCH', body: JSON.stringify({ ...model, permission_mode: form.elements.permission_mode.value, skill_discovery: form.elements.skill_discovery.value }) });
      closeModal(); await refreshChatRuntime(); toast('默认配置已保存；现有会话的显式覆盖优先');
    } catch (error) { toast(error.message, true); }
  });
}

function renderSkillCommands(showAll = false) {
  const menu = $('#skillCommands'), input = $('#chatInput'); if (!menu || !input) return;
  const text = input.value.trim();
  if (!showAll && (!text.startsWith('/') || /\s/.test(text))) { menu.hidden = true; return; }
  const query = showAll || ['/skills', '/skill'].includes(text) ? '' : text.slice(1).toLowerCase();
  const skills = (state.chatRuntime?.skills || []).filter(skill => skill.user_invocable && (!query || skill.command.toLowerCase().includes(query) || skill.name.toLowerCase().includes(query)));
  menu.innerHTML = `<div class="skill-command-heading">按需使用 Skill · 不改变执行权限</div>${skills.length ? skills.map(skill => `<button type="button" data-skill-id="${esc(skill.id)}" onclick="chooseSkillCommand(this)"><strong>/${esc(skill.command)}</strong><span>${esc(skill.description || skill.name)}</span>${skill.manual_only ? '<small>仅手动调用</small>' : ''}</button>`).join('') : '<p>暂无可用技能，请在“技能”页导入。当前账号和项目以外的技能不可见。</p>'}`;
  menu.hidden = false;
}

async function openSkillCommands() {
  try { await refreshChatRuntime(); renderSkillCommands(true); } catch (error) { toast(error.message, true); }
}

function chooseSkillCommand(button) {
  const skill = state.chatRuntime?.skills?.find(item => item.id === button.dataset.skillId);
  if (!skill) return;
  const duplicate = state.chatRuntime.skills.filter(item => item.command === skill.command && item.user_invocable).length > 1;
  const input = $('#chatInput'); const old = input.value.trim();
  input.value = `/${duplicate ? skill.id : skill.command} ${old.startsWith('/') ? '' : old}`;
  $('#skillCommands').hidden = true; input.focus(); saveComposerDraft(); updateComposerControls();
}

async function ensureChatThread(agentId) {
  if (state.thread) return state.thread;
  const agent = agentId || $('#chatAgent')?.value || state.cache.agents?.[0]?.id;
  const draft = state.chatDrafts.new;
  const result = await api('/api/threads', { method: 'POST', body: JSON.stringify({ name: '新对话', agent_id: agent }) });
  state.thread = result.id;
  state.currentThread = result;
  if (draft) { state.chatDrafts[result.id] = draft; delete state.chatDrafts.new; }
  state.chatThreads.unshift(result); renderChatHistory();
  return result.id;
}

async function saveChatCapabilities() {
  const threadId = await ensureChatThread();
  const updated = await api(`/api/threads/${threadId}`, {
    method: 'PATCH',
    body: JSON.stringify({ capability_overrides: { ...(state.currentThread?.capability_overrides || {}), ...state.chatCapabilities } }),
  });
  if (state.thread === threadId) state.currentThread = { ...state.currentThread, ...updated };
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
      <section class="form-section control-full"><header><h3>可选扩展</h3><p>无需选择即可聊天。自动发现开启时，已启用 Skill 会按需加载；下方用于显式绑定，自动发现可在默认配置中关闭。MCP 仅连接你明确选择的服务。</p></header></section>
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
  if (state.activeTurn || state.chatQueue.some(item => ['pending','dispatching'].includes(item.status))) return;
  const agent = (state.cache.agents || []).find(item => item.id === agentId);
  if (!agent) return;
  state.chatCapabilities = {
    skill_ids: [...(agent.skill_ids || [])],
    mcp_server_ids: [...(agent.mcp_server_ids || [])],
  };
  renderCapabilityBar();
  if (!state.thread) return;
  try {
    const updated = await api(`/api/threads/${state.thread}`, { method: 'PATCH', body: JSON.stringify({ agent_id: agentId, model_override: {} }) });
    state.currentThread = { ...state.currentThread, ...updated };
    if ($('#chatModel')) $('#chatModel').innerHTML = chatModelOptions(agent);
    await refreshChatRuntime();
  } catch (error) { toast(error.message, true); }
}

function userMessageTime(message) {
  const queued = state.chatQueue.find(item => item.id === message.meta?.queue_message_id);
  const value = message.meta?.sent_at ?? queued?.created_at ?? message.created_at;
  if (value == null || value === '') return { label: '时间未知', title: '这条历史消息未记录发送时间', iso: '' };
  const numeric = typeof value === 'number' || /^\d+(\.\d+)?$/.test(String(value));
  const date = new Date(numeric ? Number(value) * (Number(value) < 1e12 ? 1000 : 1) : value);
  if (!Number.isFinite(date.getTime())) return { label: '时间未知', title: '这条历史消息的发送时间不可用', iso: '' };
  return { label: date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }), title: `发送于 ${date.toLocaleString('zh-CN', { hour12: false })}`, iso: date.toISOString() };
}

function findUserMessage(id) { return state.currentThread?.messages?.find(item => item.id === id && item.role === 'user'); }

function refreshUserMessage(id) {
  const message = findUserMessage(id); const node = document.getElementById(`chatMessage_${id}`);
  if (!message || !node) return;
  const html = messageHtml(message); node.innerHTML = html; state.chatMessageSignatures[id] = html;
}

async function copyUserMessage(button) {
  const message = findUserMessage(button.dataset.messageId);
  if (!message || button.disabled) return;
  button.disabled = true;
  try { await copyTextToClipboard(String(message.content ?? '')); toast('消息已复制'); }
  catch (error) { toast(error.message || '复制失败', true); }
  finally { button.disabled = false; }
}

function startEditUserMessage(button) {
  const message = findUserMessage(button.dataset.messageId);
  if (!message || button.disabled) return;
  if (state.chatSubmitPending || state.chatUnknownSubmission || state.userMessageEdit?.pending) return toast('请先确认当前消息的提交状态', true);
  const old = state.userMessageEdit;
  state.userMessageEdit = { threadId: state.thread, messageId: message.id, content: String(message.content ?? '') };
  if (old?.messageId !== message.id) refreshUserMessage(old?.messageId);
  refreshUserMessage(message.id);
  const input = document.getElementById(`userMessageEdit_${message.id}`); input?.focus();
  input?.setSelectionRange?.(input.value.length, input.value.length);
}

function cancelUserMessageEdit() {
  const edit = state.userMessageEdit;
  if (!edit || edit.pending) return;
  state.userMessageEdit = null;
  if (edit.threadId === state.thread) refreshUserMessage(edit.messageId);
}

async function submitUserMessageEdit(button) {
  const edit = state.userMessageEdit;
  if (!edit || edit.pending || edit.threadId !== state.thread || button.disabled) return;
  const message = findUserMessage(edit.messageId);
  const input = document.getElementById(`userMessageEdit_${edit.messageId}`);
  const content = input?.value.trim();
  if (!message || !content) return toast('消息内容不能为空', true);
  if (state.chatSubmitPending || state.chatUnknownSubmission) return toast('请先确认当前消息的提交状态', true);
  edit.content = content; edit.pending = true;
  const controls = button.closest?.('.user-message-editor')?.querySelectorAll('button,textarea');
  controls?.forEach(control => { control.disabled = true; });
  try {
    const result = await sendMessage({ content, preserveDraft: true, attachments: (message.meta?.attachments || []).map(item => ({ ...item, status: 'ready' })) });
    if (result?.id && state.userMessageEdit === edit) state.userMessageEdit = null;
  } finally {
    edit.pending = false;
    if (edit.threadId === state.thread) { controls?.forEach(control => { control.disabled = false; }); refreshUserMessage(edit.messageId); }
  }
}

function userMessageBodyHtml(message) {
  const edit = state.userMessageEdit;
  if (message.id && edit?.threadId === state.thread && edit.messageId === message.id) return `<section class="user-message-editor" aria-label="编辑已发送消息"><textarea id="userMessageEdit_${esc(message.id)}" aria-label="编辑消息内容" rows="4" ${edit.pending ? 'disabled' : ''} oninput="if(state.userMessageEdit)state.userMessageEdit.content=this.value">${esc(edit.content)}</textarea><p>重新发送将作为新消息提交，原消息和执行记录保留。</p><div><button type="button" ${edit.pending ? 'disabled' : ''} onclick="cancelUserMessageEdit()">取消</button><button type="button" class="user-edit-send" ${edit.pending ? 'disabled' : ''} onclick="submitUserMessageEdit(this)">${edit.pending ? '正在提交…' : '重新发送'}</button></div></section>`;
  const time = userMessageTime(message);
  return `<div class="user-message-bubble"><div class="message-copy">${richText(message.content, [])}</div>${message.id ? `<div class="user-message-actions" role="group" aria-label="消息操作"><time ${time.iso ? `datetime="${esc(time.iso)}"` : ''} title="${esc(time.title)}">${esc(time.label)}</time><button type="button" data-message-id="${esc(message.id)}" onclick="copyUserMessage(this)" aria-label="复制消息" title="复制消息">${chatIcon('copy')}</button><button type="button" data-message-id="${esc(message.id)}" onclick="startEditUserMessage(this)" aria-label="编辑消息" title="编辑消息">${chatIcon('edit')}</button></div>` : ''}</div>`;
}

function messageHtml(message) {
  const events = message.meta?.events || [];
  const toolEvents = events.filter(event => event.type?.startsWith('tool_'));
  const startedAt = Date.parse(events[0]?.timestamp || '');
  const endedAt = Date.parse(events.at(-1)?.timestamp || '');
  const elapsed = Number.isFinite(startedAt) && Number.isFinite(endedAt) && endedAt >= startedAt ? `${Math.max(1, Math.ceil((endedAt - startedAt) / 1000))}s` : '';
  const sources = message.meta?.sources || [];
  const model = message.meta?.runtime?.model;
  const assistant = message.role !== 'user';
  const choice = assistant ? message.project_choice : null;
  const artifacts = assistant ? (message.project_artifacts || []) : [];
  const missingFile = assistant && choice?.save_to_project && !artifacts.length && !message.resource_assets?.length
    ? '<p class="artifact-missing-note">这条回复没有关联到实际文件。代码块不是项目文件；请让智能体继续创建文件，或重新发送任务。</p>' : '';
  const decision = choice ? `<section class="project-decision-summary" aria-label="本次项目选择"><span class="project-decision-check" aria-hidden="true">✓</span><span><strong>${choice.save_to_project ? '已确认保存到项目' : '已选择仅回答，不保存'}</strong>${choice.project_id ? `<small>${esc(projectName(choice.project_id))}</small>` : ''}</span></section>` : '';
  const artifactCards = artifacts.filter(item => item.kind !== 'screenshot').map(item => `<section class="project-result-card" aria-label="项目文件 ${esc(item.path)}"><span class="project-result-icon" aria-hidden="true">⌘</span><span class="project-result-copy"><strong>${esc(item.path)}</strong><small>已保存到 ${esc(projectName(item.project_id))}</small></span><button type="button" onclick="viewProjectArtifact('${esc(item.project_id)}','${esc(item.id)}')">打开</button><button type="button" onclick="downloadProjectArtifact('${esc(item.project_id)}','${esc(item.id)}',decodeURIComponent('${encodeURIComponent(item.path).replace(/'/g, '%27')}'))">下载</button></section>`).join('');
  const resourceCards = assistant ? (Array.isArray(message.resource_assets) ? message.resource_assets : []).map(resourceAssetHtml).join('') : '';
  const workTrace = assistant && !message.error && !message.meta?.error ? `<details class="agent-work-trace"><summary>Worked${elapsed ? ` for ${elapsed}` : ''}</summary>${toolEvents.length ? `<div class="agent-work-events">${toolEvents.map(event => `<div><span>${event.type === 'tool_started' ? '运行' : event.type === 'tool_failed' ? '失败' : '完成'}</span><strong>${esc(event.name || '')}</strong></div>`).join('')}</div>` : '<div class="agent-work-events"><span>已完成回复</span></div>'}</details>` : '';
  return `
    <article class="message-turn ${assistant ? 'assistant' : 'user'} ${message.error || message.meta?.error ? 'is-error' : ''}">
      <div class="turn-avatar" aria-hidden="true">${assistant ? codezznLogoHtml : '你'}</div>
      <div class="turn-content">
        <header><strong>${assistant ? 'Codezzn' : '你'}</strong>${model ? `<span>${esc(model)}</span>` : ''}</header>
        ${decision}
        ${workTrace}
        ${assistant ? `<div class="message-copy">${richText(message.content, artifacts)}</div>` : userMessageBodyHtml(message)}
        ${message.meta?.attachments?.length ? `<div class="message-attachments">${message.meta.attachments.map(item => attachmentHtml(item)).join('')}</div>` : ''}
        ${missingFile}
        ${artifactCards}
        ${(message.conversation_artifacts || []).map(artifactOutputHtml).join('')}
        ${artifacts.filter(item => item.kind === 'screenshot').map(item => artifactOutputHtml({ ...item, name: item.path.split('/').at(-1), previewable: true, storage: 'project', download_url: `/api/projects/${item.project_id}/artifacts/${item.id}/download` })).join('')}
        ${resourceCards}
        ${sources.length ? `<div class="source-list"><span>知识来源</span><div>${sources.map((source, index) => `<button type="button">[${index + 1}] ${esc(source.source)} #片段${Number(source.position) + 1}</button>`).join('')}</div></div>` : ''}
      </div>
    </article>`;
}

function assetStripHtml(messages) {
  const projects = new Map();
  const files = new Map();
  messages.filter(message => message.role === 'assistant').forEach(message => {
    const chosen = message.project_choice?.project_id;
    if (chosen) projects.set(chosen, chosen);
    (Array.isArray(message.resource_assets) ? message.resource_assets : []).forEach(item => {
      if (item?.kind === 'project' && item.status !== 'failed') projects.set(item.project_id || item.resource_id || item.id, item.project_id || item.resource_id || item.id);
    });
    (Array.isArray(message.project_artifacts) ? message.project_artifacts : []).forEach(item => {
      if (item?.id && item.project_id) { projects.set(item.project_id, item.project_id); files.set(item.id, item); }
    });
  });
  const count = projects.size + files.size;
  if (!count) return '<div class="conversation-assets" id="conversationAssets" hidden></div>';
  return `<div class="conversation-assets" id="conversationAssets" aria-label="会话资产"><span>▣ ${count} Assets</span>
    ${[...projects.values()].slice(0, 6).map(id => `<button type="button" class="conversation-asset-chip" data-project-id="${esc(id)}" onclick="openChatProject(this)" aria-label="在 Files 中查看项目 ${esc(projectName(id))}">▱ ${esc(projectName(id))}</button>`).join('')}
    ${[...files.values()].slice(-8).map(item => `<button type="button" class="conversation-asset-chip" data-project-id="${esc(item.project_id)}" data-artifact-id="${esc(item.id)}" onclick="openChatArtifact(this)" aria-label="在 Files 中打开 ${esc(item.path)}">▤ ${esc(item.path.split('/').at(-1))}</button>`).join('')}
    ${count > 14 ? `<button type="button" class="conversation-asset-chip" onclick="go('projects')">查看全部</button>` : ''}</div>`;
}

function resourceAssetHtml(asset) {
  if (!asset || !asset.kind) return '';
  const kind = String(asset.kind);
  const id = String(asset.resource_id || asset.id || '');
  const projectId = String(asset.project_id || (kind === 'project' ? id : ''));
  const label = { project: '项目', workflow: '工作流', workflow_draft: '工作流草稿', workflow_run: '工作流运行' }[kind] || '资源';
  const name = String(asset.name || label);
  const status = String(asset.status || '已创建');
  const action = kind === 'project' && projectId ? '打开项目' : kind === 'workflow' && id ? '打开工作流' : kind === 'workflow_draft' && id ? '查看草稿' : '';
  return `<section class="project-result-card resource-result-card" aria-label="${esc(label)} ${esc(name)}"><span class="project-result-icon" aria-hidden="true">${kind === 'project' ? '▣' : '◇'}</span><span class="project-result-copy"><strong>${esc(name)}</strong><small>${esc(label)} · ${esc(status)}</small></span>${action ? `<button type="button" data-kind="${esc(kind)}" data-id="${esc(id)}" data-project-id="${esc(projectId)}" onclick="openResourceAsset(this)">${action}</button>` : ''}</section>`;
}

async function openResourceAsset(button) {
  const kind = button.dataset.kind;
  if (kind === 'project') {
    state.projectDetailId = button.dataset.projectId;
    await go('projects');
  } else if (kind === 'workflow') {
    await go('workflows');
    if ((state.cache.workflows || []).some(item => item.id === button.dataset.id)) editResource('workflows', button.dataset.id);
  } else if (kind === 'workflow_draft') {
    await viewWorkflowDraft(button.dataset.id);
  }
}

async function viewWorkflowDraft(draftId) {
  try {
    const draft = await api(`/api/workflow-drafts/${encodeURIComponent(draftId)}`);
    const definition = draft.definition || {};
    const editable = draft.status === 'draft';
    modal(draft.name || '工作流草稿', `<div class="workflow-draft-summary"><p>${esc(draft.description || '检查草稿内容，然后选择保存或丢弃。')}</p><p>状态：${esc(draft.status || 'draft')}</p><pre class="code-output">${esc(JSON.stringify(definition, null, 2))}</pre>${editable ? `<div class="project-card-actions"><a class="button button-quiet button-small" href="/workflow.html?draft_id=${encodeURIComponent(draftId)}">在画布中编辑</a><button class="button button-quiet button-small" type="button" data-draft-id="${esc(draftId)}" onclick="decideWorkflowDraft(this,'discard')">丢弃草稿</button><button class="button button-primary button-small" type="button" data-draft-id="${esc(draftId)}" onclick="decideWorkflowDraft(this,'save')">保存为工作流</button></div>` : ''}</div>`, null, true);
  } catch (error) { toast(error.message, true); }
}

async function decideWorkflowDraft(button, action) {
  const draftId = button.dataset.draftId;
  const controls = $$('.workflow-draft-summary button');
  controls.forEach(item => { item.disabled = true; });
  try {
    await api(`/api/workflow-drafts/${encodeURIComponent(draftId)}/${action}`, { method: 'POST', body: '{}' });
    closeModal();
    toast(action === 'save' ? '工作流已保存' : '草稿已丢弃');
    if (state.page === 'chat') await loadPage();
  } catch (error) {
    controls.forEach(item => { item.disabled = false; });
    toast(error.message, true);
  }
}

function approvalHtml(approval) {
  const args = JSON.stringify(approval.arguments || {}, null, 2);
  if (!approval.resumable) return `<article class="message-turn assistant approval-turn" id="approval_${esc(approval.id)}"><div class="turn-avatar" aria-hidden="true">!</div><div class="turn-content"><header><strong>旧审批无法续跑</strong><span>${esc(approval.tool_name)}</span></header><div class="approval-card"><p class="approval-impact">这条审批缺少运行检查点。为避免重复或越权执行旧工具调用，不能直接允许；你可以将原任务重新放入输入框，按当前审批策略重新执行。</p><details class="approval-technical"><summary>查看旧工具参数</summary><pre>${esc(args)}</pre></details><div class="approval-actions"><button class="button button-quiet button-small" type="button" onclick="dismissStaleApproval('${esc(approval.id)}',false)">移除旧审批</button><button class="button button-primary button-small" type="button" onclick="dismissStaleApproval('${esc(approval.id)}',true)">重新填写任务</button></div></div></div></article>`;
  if (approval.tool_name === 'ask_user') {
    const question = String(approval.arguments?.question || '请选择下一步');
    const options = Array.isArray(approval.arguments?.options) ? approval.arguments.options.slice(0, 4) : [];
    return `<article class="message-turn assistant project-confirm-turn approval-turn" id="approval_${esc(approval.id)}"><div class="turn-avatar" aria-hidden="true">${codezznLogoHtml}</div><div class="turn-content"><header><strong>Codezzn</strong><span>等待你的回答</span></header>
      <section class="project-confirm-card" role="group" aria-label="${esc(question)}"><div class="project-confirm-head"><span class="project-question-icon" aria-hidden="true">?</span><strong>${esc(question)}</strong></div>
      <div class="project-confirm-body">${options.map(item => {
        const label = String(item?.label || '').slice(0, 120);
        if (!label) return '';
        const encoded = encodeURIComponent(label).replace(/'/g, '%27');
        return `<button class="project-choice" type="button" data-answer="${encoded}" onclick="resolveApproval('${esc(approval.id)}','approved',decodeURIComponent(this.dataset.answer))"><span class="project-choice-number" aria-hidden="true">✓</span><span><strong>${esc(label)}</strong><small>${esc(String(item?.description || '').slice(0, 300))}</small></span></button>`;
      }).join('')}
      <div class="project-custom-answer"><span aria-hidden="true">✎</span><input id="askAnswer_${esc(approval.id)}" type="text" maxlength="4000" aria-label="自定义回答" placeholder="或者输入你的回答" onkeydown="if(event.key==='Enter'){event.preventDefault();answerUserQuestion('${esc(approval.id)}')}" /><button class="project-answer-send" type="button" onclick="answerUserQuestion('${esc(approval.id)}')">发送</button></div>
      <button class="project-choice project-choice-subtle" type="button" onclick="resolveApproval('${esc(approval.id)}','denied','用户取消本次提问')"><span class="project-choice-number" aria-hidden="true">×</span><span><strong>取消这次提问</strong></span></button></div></section></div></article>`;
  }
  const details = approvalActionDetails(approval);
  return `
    <article class="message-turn assistant approval-turn" id="approval_${esc(approval.id)}">
      <div class="turn-avatar" aria-hidden="true">!</div>
      <div class="turn-content">
        <header><strong>需要审批</strong><span>${esc(approval.tool_name)}</span></header>
        <div class="approval-card">
          <div class="approval-heading"><span>${details ? '确认操作' : '工具准备执行'}</span><strong>${esc(details?.title || approval.tool_name)}</strong></div>
          ${details ? `<p class="approval-impact">${esc(details.description)}</p><details class="approval-technical"><summary>查看工具参数</summary><pre>${esc(args)}</pre></details>` : `<pre>${esc(args)}</pre>`}
          <div class="approval-actions">
            <button class="button button-quiet button-small" type="button" onclick="resolveApproval('${approval.id}','denied')">拒绝</button>
            <button class="button button-primary button-small" type="button" onclick="resolveApproval('${approval.id}','approved')">允许并继续</button>
          </div>
        </div>
      </div>
    </article>`;
}

async function dismissStaleApproval(approvalId, retry) {
  const card = document.getElementById(`approval_${approvalId}`);
  const buttons = card ? [...card.querySelectorAll('button')] : [];
  buttons.forEach(button => { button.disabled = true; });
  try {
    const result = await api(`/api/approvals/${encodeURIComponent(approvalId)}/dismiss`, { method: 'POST', body: '{}' });
    card?.remove();
    if (retry) {
      const input = $('#chatInput');
      if (input && result.content) { input.value = result.content; input.dispatchEvent(new Event('input')); input.focus(); }
      toast('原任务已放入输入框。检查内容后发送，将重新进行所需审批。');
    } else toast('旧审批已移除；没有执行任何工具。');
  } catch (error) { buttons.forEach(button => { button.disabled = false; }); toast(error.message, true); }
}

function approvalActionDetails(approval) {
  const args = approval.arguments || {};
  const target = String(args.name || args.project_name || args.workflow_name || args.project_id || args.workflow_id || args.draft_id || '未命名');
  if (approval.tool_name === 'project_create') return { title: `创建项目「${target}」`, description: '允许后将在工作区建立新项目，可供后续文件和工作流关联。' };
  if (approval.tool_name === 'project_select') return { title: `关联已有项目「${target}」`, description: '允许后会将本次对话绑定到该项目，后续确认写入的文件产物将保存在该项目中。' };
  if (approval.tool_name === 'workflow_draft_save') return { title: `保存工作流「${target}」`, description: '允许后会将草稿变更写入正式工作流，后续运行将使用新版本。' };
  if (approval.tool_name === 'workflow_run') return { title: `运行工作流「${target}」`, description: '允许后会按当前定义执行工作流节点，可能调用已配置的模型和工具。' };
  if (approval.tool_name === 'workflow_draft_discard') return { title: `丢弃工作流草稿「${target}」`, description: '允许后将移除未保存的草稿变更，正式工作流保持原样。' };
  return null;
}

function answerUserQuestion(approvalId) {
  const answer = document.getElementById(`askAnswer_${approvalId}`)?.value.trim();
  if (!answer) return toast('请输入回答', true);
  resolveApproval(approvalId, 'approved', answer);
}

async function resolveApproval(approvalId, decision, reason = '') {
  if (state.approvalPending) return;
  state.approvalPending = true;
  updateComposerControls();
  const card = document.getElementById(`approval_${approvalId}`);
  const buttons = card ? [...card.querySelectorAll('button, input')] : [];
  buttons.forEach(button => { button.disabled = true; });
  const action = decision === 'approved' ? '正在执行并继续对话' : '正在拒绝并继续对话';
  const heading = card?.querySelector('.approval-heading span, .project-confirm-head strong');
  const originalHeading = heading?.textContent;
  if (heading) heading.textContent = action;
  try {
    await api(`/api/approvals/${approvalId}`, {
      method: 'POST',
      body: JSON.stringify({ decision, reason: reason || decision }),
    });
    toast(card?.querySelector('.project-confirm-card') ? '回答已提交，智能体继续执行' : decision === 'approved' ? '已允许工具调用' : '已拒绝工具调用');
    await loadPage();
  } catch (error) {
    const status = await api(`/api/approvals/${encodeURIComponent(approvalId)}`).catch(() => null);
    if (status && status.status !== 'pending') {
      card?.remove();
      await loadPage();
      toast(status.error ? `回答已接收，后续执行失败：${status.error}` : '该回答已提交；已刷新会话状态，请勿重复点击', !!status.error);
    } else if (status?.status === 'pending') {
      buttons.forEach(button => { button.disabled = false; });
      if (heading) heading.textContent = originalHeading;
      toast(error.message, true);
    } else {
      if (heading) heading.textContent = '提交结果尚未确认';
      card?.querySelector('.turn-content')?.insertAdjacentHTML('beforeend', '<button class="button button-quiet button-small" type="button" onclick="loadPage()">刷新会话状态</button>');
      toast('提交结果尚未确认，请刷新会话状态后再操作；不会重复提交旧回答', true);
    }
  } finally {
    state.approvalPending = false;
    updateComposerControls();
    refreshSidebarThreads();
  }
}

function scrollMessages(smooth = false) {
  const messages = $('#messages');
  if (messages) messages.scrollTo({ top: messages.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
}

function bindComposer() {
  const input = $('#chatInput');
  scrollMessages(true);
  if (!input) return;
  input.addEventListener('keydown', event => {
    if (event.key === 'Escape') { const menu = $('#skillCommands'); if (menu) menu.hidden = true; }
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); sendMessage(); }
  });
  input.addEventListener('input', () => {
    input.style.height = '64px';
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
    saveComposerDraft(); updateComposerControls();
    renderSkillCommands();
  });
  const dock = $('.prompt-dock');
  dock?.addEventListener('dragover', event => { if (event.dataTransfer.types.includes('Files')) { event.preventDefault(); dock.classList.add('is-dragging'); } });
  dock?.addEventListener('dragleave', () => dock.classList.remove('is-dragging'));
  dock?.addEventListener('drop', event => { event.preventDefault(); dock.classList.remove('is-dragging'); uploadChatAttachments(Array.from(event.dataTransfer.files)); });
  input.addEventListener('paste', event => { const files = Array.from(event.clipboardData?.files || []); if (files.length) { event.preventDefault(); uploadChatAttachments(files); } });
  updateComposerControls();
  input.focus();
}

async function newThread() {
  if (state.chatSubmitPending || state.intentPending || state.approvalPending || state.modelSaving || state.chatAttachments.some(item => item.status === 'uploading')) return toast('请先等待当前操作完成', true);
  if (state.pendingProjectTurn) return toast('请先处理当前任务的项目确认', true);
  try {
    saveComposerDraft();
    state.threadScope = 'active';
    const result = await api('/api/threads', { method: 'POST', body: JSON.stringify({ name: '新对话' }) });
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

function selectedAgentWriteCapability(agentId, kind = '') {
  const agent = (state.cache.agents || []).find(item => item.id === agentId);
  if (!agent || agent.enabled === false) return { allowed: false, reason: '当前智能体不可用' };
  const tools = agent.builtin_tools || [];
  const policy = agent.tool_policy || {};
  const rules = policy.tools || {};
  if (kind === 'browser_artifact') return { allowed: !!agent.allow_browser && ['workspace-write', 'danger-full-access'].includes(agent.sandbox_mode) && rules.screenshot !== 'deny' && rules.browser !== 'deny' && policy.default !== 'deny', reason: '请启用浏览器能力、允许截图工具，并使用工作区可写模式' };
  const allows = name => (tools.includes(name) || agent.role_template === 'coding' && ['write_file', 'apply_patch'].includes(name))
    && rules[name] !== 'deny' && (rules[name] || policy.default) !== 'deny';
  const domainAllows = name => rules[name] !== 'deny' && (rules[name] || policy.default) !== 'deny';
  const projectAllowed = ['project_create', 'project_select'].some(domainAllows);
  const workflowAllowed = ['workflow_draft_create', 'workflow_draft_update', 'workflow_draft_save', 'workflow_run'].some(domainAllows);
  const fileToolsAllowed = ['write_file', 'apply_patch'].some(allows);
  const fileAllowed = fileToolsAllowed && ['workspace-write', 'danger-full-access'].includes(agent.sandbox_mode);
  if (kind === 'project' && !projectAllowed) return { allowed: false, reason: '项目创建与选择工具均被策略禁止' };
  if (kind === 'workflow' && !workflowAllowed) return { allowed: false, reason: '尚未启用工作流创建、修改或运行工具，或工具策略禁止这些操作' };
  if (['file', 'other_artifact'].includes(kind) && !fileToolsAllowed) return { allowed: false, reason: '尚未启用 write_file / apply_patch，或工具策略禁止写入文件' };
  if (['file', 'other_artifact'].includes(kind) && !fileAllowed) return { allowed: false, reason: '沙箱模式为只读，不能创建真实文件' };
  if (!kind && !projectAllowed && !workflowAllowed && !fileAllowed) return { allowed: false, reason: '尚未启用项目、工作流或写文件工具，或工具策略禁止写入' };
  return { allowed: true, reason: '' };
}

function projectDecisionCardHtml(step = 'project') {
  const pending = state.pendingProjectTurn;
  if (!pending) return '';
  const name = projectName(state.activeProjectId);
  const capability = selectedAgentWriteCapability(pending.agent, pending.kind);
  const target = pending.kind === 'workflow' ? '工作流' : pending.kind === 'project' ? '项目' : pending.kind === 'browser_artifact' ? '截图与浏览器文件' : '代码和文件';
  const title = step === 'permission' ? `当前智能体还不能创建或修改${target}`
    : step === 'save' ? `是否将本次${target}任务关联到“${name}”？`
    : step === 'create' ? '为这次任务创建项目' : pending.unresolvedTargetName ? `找不到“${pending.unresolvedTargetName}”，请选择目标项目` : '是否为这次任务关联一个项目？';
  let body = '';
  if (step === 'permission') body = `
    <p class="project-permission-note" role="status">${esc(capability.reason)}。请在智能体配置中开启所需工具${['file', 'other_artifact'].includes(pending.kind) ? '并选择“工作区可写”' : ''}。项目确认与工具审批仍会分别执行。</p>
    <button class="project-choice" type="button" onclick="openPendingAgentSettings()"><span class="project-choice-number" aria-hidden="true">⚙</span><span><strong>配置智能体</strong><small>保留这次任务文本，前往智能体设置。</small></span></button>
    <button class="project-choice" type="button" onclick="continuePendingProject(false)"><span class="project-choice-number" aria-hidden="true">↪</span><span><strong>仅回答，不保存</strong><small>继续生成答案，但不会创建文件。</small></span></button>`;
  else if (step === 'save') body = `
    <button class="project-choice" type="button" onclick="continuePendingProject(true)"><span class="project-choice-number">1</span><span><strong>关联当前项目</strong><small>Agent 将把本次${target}任务归入“${esc(name)}”。写操作仍遵守工具审批。</small></span></button>
    <button class="project-choice" type="button" onclick="continuePendingProject(false)"><span class="project-choice-number">2</span><span><strong>仅回答，不保存</strong><small>继续生成答案，但不创建持久产物。</small></span></button>
    <button class="project-choice project-choice-subtle" type="button" onclick="openProjectPicker('pending')"><span class="project-choice-number">⌕</span><span><strong>改选项目</strong><small>将本次任务关联到另一个已有项目。</small></span></button>`;
  else if (step === 'create') body = `
    <label class="project-inline-label" for="projectInlineName">项目名称</label>
    <input class="project-inline-input" id="projectInlineName" type="text" maxlength="100" value="${esc(pending.suggestedName)}" placeholder="例如：快速排序脚本" onkeydown="if(event.key==='Enter'){event.preventDefault();createPendingProject()}">
    <div class="project-card-actions"><button class="button button-quiet button-small" type="button" onclick="renderProjectDecision('project')">返回</button><button class="button button-primary button-small" type="button" onclick="createPendingProject()">创建项目</button></div>`;
  else body = `
    <button class="project-choice" type="button" onclick="renderProjectDecision('create')"><span class="project-choice-number">1</span><span><strong>创建新项目</strong><small>为此任务建立独立目录，再由你确认是否保存生成内容。</small></span></button>
    <button class="project-choice" type="button" onclick="openProjectPicker('pending')"><span class="project-choice-number">2</span><span><strong>打开已有项目</strong><small>选择一个项目作为本次任务的目标。</small></span></button>
    <button class="project-choice project-choice-subtle" type="button" onclick="continuePendingProject(false)"><span class="project-choice-number">3</span><span><strong>仅回答，不保存</strong><small>Agent 会继续回答，不写入文件。</small></span></button>`;
  return `<article class="message-turn assistant project-confirm-turn" id="${pending.cardId}"><div class="turn-avatar" aria-hidden="true">${codezznLogoHtml}</div><div class="turn-content"><header><strong>Codezzn</strong><span>需要你的确认</span></header>
    <section class="project-confirm-card" aria-label="项目与保存确认"><header class="project-confirm-head"><span class="project-question-icon" aria-hidden="true">?</span><strong>${esc(title)}</strong><div class="project-confirm-controls"><button type="button" onclick="toggleProjectDecision()" aria-label="收起确认">−</button><button type="button" onclick="cancelPendingProject()" aria-label="取消这次任务">×</button></div></header>
    <div class="project-confirm-body">${pending.intentError ? `<p class="project-permission-note" role="status">意图检查暂时不可用，请明确选择是否关联项目。</p>` : ''}${pending.unresolvedTargetName ? `<p class="project-permission-note" role="status">指定的项目不存在；不会将文件写进当前的其他项目。</p>` : ''}${body}${step === 'project' ? `<div class="project-custom-answer"><span aria-hidden="true">✎</span><input type="text" id="projectCustomAnswer" aria-label="输入项目名称" placeholder="或者输入新项目名称，按 Enter 继续" onkeydown="if(event.key==='Enter'){event.preventDefault();createPendingProjectFromCustom()}" /></div>` : ''}</div></section></div></article>`;
}

function renderProjectDecision(step = 'project') {
  const pending = state.pendingProjectTurn;
  if (!pending) return;
  pending.step = step;
  const old = document.getElementById(pending.cardId);
  if (old) old.outerHTML = projectDecisionCardHtml(step);
  else { const dock = $('#chatInteractionDock'); if (dock) { dock.hidden = false; dock.insertAdjacentHTML('beforeend', projectDecisionCardHtml(step)); } }
  scrollMessages(true);
  if (step === 'create') $('#projectInlineName')?.focus();
}

function toggleProjectDecision() {
  const card = document.querySelector('.project-confirm-card');
  card?.classList.toggle('is-collapsed');
  const control = card?.querySelector('.project-confirm-controls button');
  if (control) { control.textContent = card.classList.contains('is-collapsed') ? '+' : '−'; control.setAttribute('aria-label', card.classList.contains('is-collapsed') ? '展开确认' : '收起确认'); }
}

async function cancelPendingProject() {
  const pending = state.pendingProjectTurn;
  if (!pending) return;
  document.getElementById(pending.cardId)?.remove();
  document.getElementById(pending.userId)?.remove();
  const input = $('#chatInput');
  if (input) { input.value = pending.content; input.focus(); input.dispatchEvent(new Event('input')); }
  state.pendingProjectTurn = null;
  updateComposerControls();
  if (Object.hasOwn(pending, 'priorProjectId') && pending.priorProjectId !== state.activeProjectId) {
    try { await setActiveProject(pending.priorProjectId); }
    catch (error) { toast(`恢复原项目失败：${error.message}`, true); }
  }
}

function openPendingAgentSettings() {
  cancelPendingProject();
  go('agents');
}

function createPendingProjectFromCustom() {
  const value = $('#projectCustomAnswer')?.value.trim();
  if (!value) return;
  renderProjectDecision('create');
  const input = $('#projectInlineName');
  if (input) input.value = value;
}

async function createPendingProject() {
  const pending = state.pendingProjectTurn;
  const name = $('#projectInlineName')?.value.trim();
  if (!pending || !name) return toast('请输入项目名称', true);
  const button = $('.project-card-actions .button-primary');
  if (button) button.disabled = true;
  try {
    const project = await api('/api/projects', { method: 'POST', body: JSON.stringify({ name }) });
    await refreshProjects();
    await setActiveProject(project.id);
    pending.unresolvedTargetName = null;
    renderProjectDecision('save');
  } catch (error) { if (button) button.disabled = false; toast(error.message, true); }
}

async function continuePendingProject(saveToProject) {
  const pending = state.pendingProjectTurn;
  if (!pending) return;
  if (saveToProject && pending.unresolvedTargetName) return toast('请先选择或创建目标项目，不能写入其他项目', true);
  if (saveToProject && !state.activeProjectId) return toast('请先选择项目', true);
  if (saveToProject && !selectedAgentWriteCapability(pending.agent, pending.kind).allowed) {
    renderProjectDecision('permission');
    return;
  }
  state.pendingProjectTurn = null;
  document.getElementById(pending.cardId)?.remove();
  await sendMessage({ content: pending.content, agent: pending.agent, attachments: pending.attachments, project_id: state.activeProjectId, save_to_project: saveToProject, intent_kind: pending.kind, preRendered: true });
}

// Chat is a persistent server queue. A browser disconnect never stops execution.
const chatTerminalStatuses = new Set(['completed', 'failed', 'cancelled']);

async function conversationApi(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try { return await api(path, { ...options, signal: controller.signal }); }
  catch (error) { if (error.name === 'AbortError') throw new Error('请求超时，后台状态尚未确认'); throw error; }
  finally { clearTimeout(timeout); }
}

function chatSubmissionId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  const values = new Uint8Array(16);
  if (typeof crypto === 'undefined' || !crypto.getRandomValues) throw new Error('当前浏览器不支持安全的提交标识，请使用现代浏览器');
  crypto.getRandomValues(values); values[6] = (values[6] & 15) | 64; values[8] = (values[8] & 63) | 128;
  const hex = [...values].map(value => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}

function readUnknownChatSubmission(threadId) {
  if (!threadId) return null;
  try { return JSON.parse(localStorage.getItem?.(`codezzn.queue.unknown.${threadId}`) || 'null'); } catch (_) { return null; }
}

function rememberUnknownChatSubmission(value) {
  state.chatUnknownSubmission = value;
  try { const key = `codezzn.queue.unknown.${state.thread}`; if (value) localStorage.setItem?.(key, JSON.stringify(value)); else localStorage.removeItem?.(key); } catch (_) { /* The in-memory guard still prevents resubmission. */ }
}

function restoreChatInteractionSubmissions(threadId) {
  state.chatInteractionSubmissions = {};
  if (!threadId) return;
  try {
    const saved = JSON.parse(localStorage.getItem?.(`codezzn.interactions.unknown.${threadId}`) || '{}');
    for (const [key, value] of Object.entries(saved)) {
      const id = key.split(':')[0]; const interaction = state.chatInteractions.find(item => item.id === id);
      if (interaction?.status === 'pending' && !(key.includes(':') && interaction.response?.cards?.[key.slice(id.length + 1)])) state.chatInteractionSubmissions[key] = { ...value, pending: false, unknown: true };
    }
  } catch (_) { /* Server interaction state remains authoritative. */ }
}

function persistChatInteractionSubmissions() {
  if (!state.thread) return;
  const saved = Object.fromEntries(Object.entries(state.chatInteractionSubmissions).filter(([, value]) => value.pending || value.unknown));
  try { const key = `codezzn.interactions.unknown.${state.thread}`; if (Object.keys(saved).length) localStorage.setItem?.(key, JSON.stringify(saved)); else localStorage.removeItem?.(key); } catch (_) { /* In-memory guards still apply. */ }
}

function queueMessageActive(message) {
  if (!message || ['pending', 'cancelled', 'failed'].includes(message.status)) return false;
  return !chatTerminalStatuses.has(message.run_status || '') && (message.status === 'dispatching' || message.status === 'consumed');
}

function clearConfirmedChatDraft(unknown) {
  const input = $('#chatInput');
  if (!unknown.preserveDraft) {
    if (input?.value.trim() === unknown.payload?.content) input.value = '';
    state.chatAttachments = state.chatAttachments.filter(item => !(unknown.payload?.attachment_ids || []).includes(item.id));
  }
  renderChatAttachments(); rememberUnknownChatSubmission(null);
}

function syncActiveChatTurn() {
  const message = state.chatQueue.find(queueMessageActive);
  const interaction = state.chatInteractions.find(item => ['pending', 'submitting'].includes(item.status) && item.kind !== 'decision_cards');
  const legacyRunning = ['running','waiting_for_input','waiting_for_project','waiting_for_approval'].includes(state.currentThread?.status);
  state.activeTurn = message ? { turn_id: message.turn_id, queue_message_id: message.id, status: message.run_status } : interaction ? { turn_id: interaction.turn_id, queue_message_id: interaction.queue_message_id, status: 'waiting_for_input' } : legacyRunning ? { turn_id: state.currentThread.messages?.at(-1)?.turn_id, status: state.currentThread.status } : null;
}

function persistedChatMessagesHtml(messages) {
  return messages.map((message, index) => {
    const key = message.id || `${message.turn_id || 'history'}_${message.role}_${index}`;
    const html = messageHtml(message); state.chatMessageSignatures[key] = html;
    return `<div class="persisted-chat-message" id="chatMessage_${esc(key)}">${html}</div>`;
  }).join('');
}

function persistentChatTimelineHtml(messages, interactions) {
  const records = messages.map((message, index) => ({ kind: 'message', item: message, index })).concat(interactions.filter(item => !chatInteractionInDock(item)).map((item, index) => ({ kind: 'interaction', item, index: messages.length + index })));
  const timestamp = item => typeof item.created_at === 'number' ? item.created_at * 1000 : Date.parse(item.created_at || '') || 0;
  records.sort((a, b) => timestamp(a.item) - timestamp(b.item) || a.index - b.index);
  return records.map(record => {
    if (record.kind === 'interaction') { state.chatInteractionSignatures[record.item.id] = chatInteractionSignature(record.item); return chatInteractionHtml(record.item); }
    const message = record.item; const key = message.id || `${message.turn_id || 'history'}_${message.role}_${record.index}`;
    const html = messageHtml(message); state.chatMessageSignatures[key] = html;
    return `<div class="persisted-chat-message" id="chatMessage_${esc(key)}">${html}</div>`;
  }).join('');
}

function chatInteractionInDock(interaction) { return interaction.kind !== 'decision_cards' && ['pending', 'submitting'].includes(interaction.status); }

function toggleChatInteraction(button) {
  const id = button.dataset.interactionId;
  const body = document.getElementById(`interactionBody_${id}`);
  if (!body) return;
  body.hidden = !body.hidden;
  state.chatInteractionCollapsed[id] = body.hidden;
  document.getElementById(`interaction_${id}`)?.querySelectorAll('[data-collapse-question]').forEach(control => {
    control.setAttribute('aria-expanded', String(!body.hidden));
    if (control.dataset.collapseQuestion === 'icon') {
      control.setAttribute('aria-label', body.hidden ? '展开确认' : '收起确认');
      control.textContent = body.hidden ? '+' : '−';
    }
  });
}

function updateChatAnswerControl(input) {
  const send = document.getElementById(`interactionSubmit_${input.dataset.interactionId}`);
  if (send) send.hidden = !input.value.trim();
}

function chatInteractionHtml(interaction) {
  const payload = interaction.payload || {};
  const pending = interaction.status === 'pending';
  const locked = !pending || !!state.chatInteractionSubmissions[interaction.id]?.unknown || !!state.chatInteractionSubmissions[interaction.id]?.pending || !!state.chatInteractionSubmissions[interaction.id]?.accepted;
  const disabled = locked ? 'disabled' : '';
  const statusLabel = ({ pending: '需要你的回答', submitting: '回答已接收，正在继续', answered: '已回答', cancelled: '已取消', superseded: '已由新指令替代' })[interaction.status] || interaction.status;
  const attrs = `data-interaction-id="${esc(interaction.id)}"`;
  let body = '';
  if (interaction.kind === 'question') {
    body = `<div class="interaction-options">${(payload.options || []).map((option, index) => `<button type="button" class="interaction-choice" ${attrs} data-option-id="${esc(option.id)}" ${disabled} onclick="answerChatOption(this)"><span class="interaction-number" aria-hidden="true">${index + 1}</span><span class="interaction-choice-copy"><strong>${esc(option.label)}</strong>${option.description ? `<small>${esc(option.description)}</small>` : ''}</span></button>`).join('')}</div><div class="interaction-custom-answer"><span class="interaction-number" aria-hidden="true">${chatIcon('edit')}</span><input id="interactionAnswer_${esc(interaction.id)}" ${attrs} ${disabled} aria-label="用自己的话回答" placeholder="其他想法？请用自己的话告诉我…" oninput="updateChatAnswerControl(this)" onkeydown="if(event.key==='Enter'&&!event.isComposing){event.preventDefault();answerChatQuestion(this)}"><button id="interactionSubmit_${esc(interaction.id)}" type="button" ${attrs} ${disabled} onclick="answerChatQuestion(this)" aria-label="提交回答" hidden>${chatIcon('send')}</button></div>`;
  } else if (interaction.kind === 'tool_approval') {
    body = `<details class="interaction-tool-details"><summary>查看 ${esc(payload.tool_name || payload.name || '工具调用')} 参数</summary><pre>${esc(JSON.stringify(payload.args || payload.arguments || {}, null, 2))}</pre></details>${payload.description ? `<p>${esc(payload.description)}</p>` : ''}<div class="interaction-options"><button type="button" class="interaction-choice" ${attrs} ${disabled} onclick="answerChatInteraction(this,{decision:'approved'})"><span class="interaction-number" aria-hidden="true">1</span><span class="interaction-choice-copy"><strong>允许并继续</strong><small>仅批准此次调用，后续写入和命令仍按策略审批。</small></span></button><button type="button" class="interaction-choice" ${attrs} ${disabled} onclick="answerChatInteraction(this,{decision:'denied'})"><span class="interaction-number" aria-hidden="true">2</span><span class="interaction-choice-copy"><strong>拒绝调用</strong><small>不授权执行此次操作。</small></span></button></div>`;
  } else if (interaction.kind === 'project_confirmation') {
    body = `<label class="interaction-answer"><span>保存到已有项目</span><select id="interactionProject_${esc(interaction.id)}" ${disabled}><option value="">请选择项目</option>${(payload.projects || []).map(project => `<option value="${esc(project.id)}">${esc(project.name)}</option>`).join('')}</select></label><div class="interaction-actions"><button type="button" class="button button-primary button-small" ${attrs} ${disabled} onclick="answerChatProject(this,false)">使用所选项目</button></div>${payload.allow_create !== false ? `<label class="interaction-answer"><span>或创建新项目</span><input id="interactionProjectName_${esc(interaction.id)}" value="${esc(payload.suggested_name || '')}" ${disabled} placeholder="项目名称"></label><div class="interaction-actions"><button type="button" class="button button-quiet button-small" ${attrs} ${disabled} onclick="answerChatProject(this,true)">创建并继续</button></div>` : ''}<div class="interaction-actions"><button type="button" class="button button-quiet button-small" ${attrs} ${disabled} onclick="answerChatInteraction(this,{decision:'denied'})">取消此任务</button></div>`;
  } else if (interaction.kind === 'decision_cards') {
    body = `<div class="decision-card-grid">${(payload.cards || []).map(card => {
      const answered = !!interaction.response?.cards?.[card.id];
      const cardSubmission = state.chatInteractionSubmissions[`${interaction.id}:${card.id}`];
      const cardDisabled = answered || interaction.status !== 'pending' || cardSubmission?.pending || cardSubmission?.unknown || cardSubmission?.accepted ? 'disabled' : '';
      return `<section class="decision-card ${answered ? 'is-answered' : ''}"><span class="decision-card-kind">${esc(({ idea:'想法',opportunity:'机会',risk:'风险',ready:'就绪' })[card.kind] || '下一步')}</span><h4>${esc(card.title)}</h4><p>${esc(card.description)}</p><div class="interaction-actions">${(card.actions || []).map(action => `<button type="button" class="button button-quiet button-small" ${attrs} data-card-id="${esc(card.id)}" data-action-id="${esc(action.id)}" title="${esc(action.description || action.label)}" ${cardDisabled} onclick="answerChatDecision(this)">${esc(action.label)}</button>`).join('')}</div>${answered ? '<small>已提交</small>' : ''}${cardSubmission?.error ? `<p class="interaction-error">${esc(cardSubmission.error)}</p>` : ''}${cardSubmission?.unknown ? `<button type="button" class="button button-quiet button-small" ${attrs} data-card-id="${esc(card.id)}" onclick="refreshChatInteractionStatus(this)">刷新提交状态</button>` : ''}</section>`;
    }).join('')}</div>`;
  }
  const submission = state.chatInteractionSubmissions[interaction.id];
  const error = interaction.error || submission?.error || '';
  const answered = !pending && interaction.kind !== 'decision_cards';
  const response = interaction.response || {};
  const responseLabel = response.answer || (response.option_id ? (payload.options || []).find(option => option.id === response.option_id)?.label : '') || response.new_project_name || (response.project_id ? (payload.projects || []).find(project => project.id === response.project_id)?.name : '') || (response.decision === 'approved' ? '已允许' : response.decision === 'denied' ? '已拒绝 / 取消' : '');
  if (chatInteractionInDock(interaction)) {
    const collapsed = !!state.chatInteractionCollapsed[interaction.id];
    return `<article class="interaction-dock-item" id="interaction_${esc(interaction.id)}" data-status="${esc(interaction.status)}"><section class="chat-interaction interaction-confirmation" aria-label="${esc(interaction.question || statusLabel)}"><header class="interaction-confirmation-head"><button type="button" class="interaction-heading" ${attrs} data-collapse-question="heading" aria-expanded="${!collapsed}" aria-controls="interactionBody_${esc(interaction.id)}" onclick="toggleChatInteraction(this)"><span class="interaction-question-icon" aria-hidden="true">?</span><strong>${esc(interaction.question || statusLabel)}</strong></button><div class="interaction-confirmation-controls"><button type="button" ${attrs} data-collapse-question="icon" aria-label="${collapsed ? '展开确认' : '收起确认'}" aria-expanded="${!collapsed}" aria-controls="interactionBody_${esc(interaction.id)}" onclick="toggleChatInteraction(this)">${collapsed ? '+' : '−'}</button><button type="button" ${attrs} ${disabled} aria-label="拒绝并关闭确认" title="拒绝本次操作，不会自动授权" onclick="answerChatInteraction(this,{decision:'denied'})">×</button></div></header><div class="interaction-confirmation-body" id="interactionBody_${esc(interaction.id)}" ${collapsed ? 'hidden' : ''}>${pending ? body : '<p class="interaction-submitting" role="status">回答已接收，正在继续…</p>'}</div><p class="interaction-error" id="interactionError_${esc(interaction.id)}" role="alert">${esc(error)}</p>${submission?.unknown ? `<button type="button" class="button button-quiet button-small" ${attrs} onclick="refreshChatInteractionStatus(this)">刷新提交状态</button>` : ''}</section></article>`;
  }
  return `<article class="message-turn assistant interaction-turn" id="interaction_${esc(interaction.id)}" data-status="${esc(interaction.status)}"><div class="turn-content"><section class="chat-interaction"><header><strong>${esc(statusLabel)}</strong></header>${interaction.question ? `<p class="interaction-question">${esc(interaction.question)}</p>` : ''}${answered ? `<p class="interaction-response">${esc(responseLabel || statusLabel)}</p>` : body}<p class="interaction-error" id="interactionError_${esc(interaction.id)}" role="alert">${esc(error)}</p>${submission?.unknown ? `<button type="button" class="button button-quiet button-small" ${attrs} onclick="refreshChatInteractionStatus(this)">刷新提交状态</button>` : ''}</section></div></article>`;
}

function chatInteractionSignature(item) { return JSON.stringify([item.kind, item.status, item.question, item.payload, item.response, item.error]); }

function chatMessageRetried(item, index) {
  if (item.retried_by || state.chatQueue.some(candidate => candidate.retry_of === item.id)) return true;
  // Older clients did not send a retry link. A later identical submission
  // supersedes only the old failure banner, never the execution history.
  return state.chatQueue.slice(index + 1).some(candidate => candidate.content === item.content && candidate.agent_id === item.agent_id &&
    JSON.stringify(candidate.attachment_ids || []) === JSON.stringify(item.attachment_ids || []));
}

function acceptQueuedChatMessage(message) {
  const existing = state.chatQueue.find(item => item.id === message.id);
  if (existing) Object.assign(existing, message);
  else state.chatQueue.push(message);
  if (message.retry_of) {
    const original = state.chatQueue.find(item => item.id === message.retry_of);
    if (original) original.retried_by = message.id;
  }
}

function renderChatQueue() {
  const container = $('#chatQueue'); if (!container) return;
  const items = state.chatQueue.filter((item, index) => {
    if (item.dismissed_at) return false;
    if (item.status === 'failed' || item.run_status === 'failed') return !chatMessageRetried(item, index);
    return item.status === 'pending' || item.status === 'dispatching';
  });
  const recent = items.filter(item => item.status !== 'failed' && item.run_status !== 'failed').concat(items.filter(item => item.status === 'failed' || item.run_status === 'failed').slice(-2));
  container.hidden = !recent.length && !state.chatUnknownSubmission && !state.chatPollError;
  container.innerHTML = `${state.chatUnknownSubmission ? `<div class="queue-uncertain"><span>提交结果尚未确认，发送已锁定，避免重复执行。</span><button type="button" onclick="refreshUnknownChatSubmission()">刷新提交状态</button>${state.chatUnknownSubmission.retryAllowed ? '<button type="button" onclick="retryUnknownChatSubmission()" title="复用原提交标识，不创建第二个任务">重试原提交</button>' : ''}</div>` : ''}${state.chatPollError ? `<div class="queue-connection-error">${esc(state.chatPollError)}</div>` : ''}${recent.map(item => { const busy = state.chatQueueMutations[`${state.thread}:${item.id}`] || state.chatUnknownSubmission?.payload?.retry_of === item.id; return `<div class="chat-queue-item"><span><small>${item.status === 'pending' ? '待执行' : item.status === 'dispatching' ? '准备执行' : '执行失败'}</small><strong>${esc(item.content)}</strong>${item.error ? `<small class="queue-item-error">${esc(item.error)}</small>` : ''}</span>${item.status === 'pending' ? `<button type="button" data-message-id="${esc(item.id)}" onclick="cancelQueuedChatMessage(this)" aria-label="取消排队任务">×</button>` : item.status === 'failed' || item.run_status === 'failed' ? `<div class="queue-item-actions"><button type="button" data-message-id="${esc(item.id)}" ${busy ? 'disabled' : ''} onclick="retryQueuedChatMessage(this)">重试</button><button type="button" data-message-id="${esc(item.id)}" ${busy ? 'disabled' : ''} onclick="dismissQueuedChatMessage(this)" title="删除这条失败提示，保留执行历史和项目文件">删除</button></div>` : ''}</div>`; }).join('')}`;
}

function stopChatPolling() { state.chatPollEpoch++; if (state.chatPollTimer) clearTimeout(state.chatPollTimer); state.chatPollTimer = null; }

function startChatPolling() {
  stopChatPolling();
  if (state.page !== 'chat' || !state.thread) return;
  const epoch = state.chatPollEpoch; const threadId = state.thread;
  const poll = async () => {
    if (epoch !== state.chatPollEpoch || state.thread !== threadId || state.page !== 'chat') return;
    await refreshPersistentChat(threadId, epoch);
    if (epoch === state.chatPollEpoch && state.thread === threadId && state.page === 'chat') state.chatPollTimer = setTimeout(poll, 1000);
  };
  state.chatPollTimer = setTimeout(poll, 100);
}

async function refreshPersistentChat(threadId = state.thread, epoch = state.chatPollEpoch) {
  if (!threadId) return;
  const started = Date.now();
  try {
    const [thread, queue, interactions] = await Promise.all([conversationApi(`/api/threads/${encodeURIComponent(threadId)}`), conversationApi(`/api/threads/${encodeURIComponent(threadId)}/queue`), conversationApi(`/api/threads/${encodeURIComponent(threadId)}/interactions`)]);
    if (threadId !== state.thread || epoch !== state.chatPollEpoch || started < (state.chatLastMutationAt || 0)) return;
    const priorActive = state.activeTurn?.turn_id;
    const stream = $('#messages');
    const followLatest = stream && stream.scrollHeight - stream.scrollTop - stream.clientHeight < 90;
    const priorArtifacts = JSON.stringify((state.currentThread?.messages || []).map(item => [item.id, item.project_artifacts, item.meta?.artifacts]));
    const runtimeChanged = state.activeProjectId !== (thread.active_project_id || null) || state.currentThread?.agent_id !== thread.agent_id;
    state.currentThread = thread; state.chatQueue = queue.data || thread.queue_messages || []; state.chatInteractions = interactions.data || thread.interactions || []; state.chatPollError = '';
    state.activeProjectId = thread.active_project_id || null; syncActiveChatTurn();
    if (runtimeChanged) refreshChatRuntime().catch(() => {});
    if (state.chatUnknownSubmission) {
      const found = state.chatQueue.find(item => item.submission_id === state.chatUnknownSubmission.submission_id);
      if (found) clearConfirmedChatDraft(state.chatUnknownSubmission);
    }
    applyPersistentChatMessages(thread.messages || []);
    applyPersistentChatInteractions();
    renderChatLiveTurn(); renderChatQueue(); updateComposerControls(); renderProjectChip();
    const title = $('.conversation-title strong'); if (title && thread.name) title.textContent = thread.name;
    if (state.activeTurn?.turn_id) await refreshChatEvents(threadId, state.activeTurn.turn_id, epoch);
    if (threadId !== state.thread || epoch !== state.chatPollEpoch) return;
    if (followLatest) scrollMessages();
    if (priorActive !== state.activeTurn?.turn_id) refreshSidebarThreads();
    const artifacts = JSON.stringify((thread.messages || []).map(item => [item.id, item.project_artifacts, item.meta?.artifacts]));
    if (artifacts !== priorArtifacts) { const strip = $('#conversationAssets'); if (strip) strip.outerHTML = assetStripHtml(thread.messages || []); refreshProjects().then(() => refreshChatFiles()).catch(() => {}); hydrateChatAttachmentPreviews(); }
  } catch (error) {
    if (threadId !== state.thread || epoch !== state.chatPollEpoch) return;
    state.chatPollError = `连接暂时中断，后台任务继续执行：${error.message}`;
    renderChatQueue();
  }
}

function applyPersistentChatMessages(messages) {
  const stream = $('#messages'); if (!stream) return;
  const atBottom = stream.scrollHeight - stream.scrollTop - stream.clientHeight < 90;
  if (messages.length || state.chatInteractions.length || state.chatQueue.length) stream.querySelector?.('.conversation-empty')?.remove();
  messages.forEach((message, index) => {
    const key = message.id || `${message.turn_id || 'history'}_${message.role}_${index}`;
    if (state.userMessageEdit?.threadId === state.thread && state.userMessageEdit.messageId === message.id && document.getElementById(`chatMessage_${key}`)) return;
    const html = messageHtml(message); if (state.chatMessageSignatures[key] === html) return;
    const existing = document.getElementById(`chatMessage_${key}`);
    if (existing) existing.innerHTML = html;
    else { const anchor = stream.querySelector?.('#chatLiveTurn'); if (anchor) anchor.insertAdjacentHTML('beforebegin', `<div class="persisted-chat-message" id="chatMessage_${esc(key)}">${html}</div>`); else stream.insertAdjacentHTML?.('beforeend', `<div class="persisted-chat-message" id="chatMessage_${esc(key)}">${html}</div>`); }
    state.chatMessageSignatures[key] = html;
  });
  if (atBottom) scrollMessages();
}

function applyPersistentChatInteractions() {
  const stream = $('#messages'); if (!stream) return;
  const dock = $('#chatInteractionDock');
  state.chatInteractions.forEach(item => {
    const signature = chatInteractionSignature(item);
    const existing = document.getElementById(`interaction_${item.id}`);
    const target = chatInteractionInDock(item) ? dock : stream;
    if (!target) return;
    if (existing && existing.parentElement && existing.parentElement !== target) target.appendChild(existing);
    if (existing && state.chatInteractionSignatures[item.id] === signature) return;
    const submitting = state.chatInteractionSubmissions[item.id];
    if (existing && item.status === 'pending' && submitting?.pending) return;
    // Preserve an unfinished answer or project choice while a pending card polls.
    if (existing && existing.dataset?.status === 'pending' && item.status === 'pending' && item.kind !== 'decision_cards' && state.chatInteractionSignatures[item.id]) {
      const error = document.getElementById(`interactionError_${item.id}`); if (error) error.textContent = item.error || submitting?.error || '';
    } else if (existing) existing.outerHTML = chatInteractionHtml(item);
    else { const live = target === stream ? document.getElementById('chatLiveTurn') : null; if (live) live.insertAdjacentHTML?.('beforebegin', chatInteractionHtml(item)); else target.insertAdjacentHTML?.('beforeend', chatInteractionHtml(item)); }
    state.chatInteractionSignatures[item.id] = signature;
    if (item.status !== 'pending') delete state.chatInteractionSubmissions[item.id];
  });
  if (dock) dock.hidden = !state.chatInteractions.some(chatInteractionInDock) && !state.pendingProjectTurn;
  persistChatInteractionSubmissions();
}

function renderChatLiveTurn() {
  let live = document.getElementById('chatLiveTurn');
  const active = state.activeTurn;
  if (!active || String(active.status).startsWith('waiting_')) { live?.remove(); return; }
  const events = state.chatEvents[active.turn_id] || [];
  const parts = events.filter(event => ['tool_started','tool_completed','tool_failed','assistant_status','model_fallback'].includes(event.type)).slice(-4).map(event => event.type === 'tool_started' ? `正在使用 ${event.name || '工具'}` : event.type === 'tool_completed' ? `${event.name || '工具'} 已完成` : event.type === 'tool_failed' ? `${event.name || '工具'} 执行失败` : event.type === 'model_fallback' ? '正在切换模型' : '正在整理结果');
  const text = events.filter(event => event.type === 'assistant_delta').map(event => event.content || '').join('');
  const html = `<div class="turn-content"><div class="agent-live-thinking"><span class="thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span><span>${state.chatStopPending ? '正在请求停止…' : '正在运行'}</span></div>${parts.length ? `<div class="agent-live-steps">${parts.map(part => `<div>${esc(part)}</div>`).join('')}</div>` : ''}${text ? `<div class="message-copy">${richText(text)}</div>` : ''}</div>`;
  if (!live) { $('#messages')?.insertAdjacentHTML?.('beforeend', '<article class="message-turn assistant is-pending" id="chatLiveTurn"></article>'); live = document.getElementById('chatLiveTurn'); }
  if (live && live.innerHTML !== html) live.innerHTML = html;
}

async function refreshChatEvents(threadId, turnId, epoch) {
  try {
    const response = await conversationApi(`/api/threads/${encodeURIComponent(threadId)}/events?turn_id=${encodeURIComponent(turnId)}&since=${state.chatEventSequences[turnId] || 0}`);
    if (threadId !== state.thread || epoch !== state.chatPollEpoch) return;
    const events = (response.data || []).map(row => ({ ...row, ...(row.data || {}), sequence: row.sequence }));
    const prior = state.chatEvents[turnId] || [];
    events.forEach(event => { const key = event.sequence ?? event.id; if (key == null || !prior.some(old => (old.sequence ?? old.id) === key)) prior.push(event); });
    state.chatEvents[turnId] = prior;
    state.chatEventSequences[turnId] = Math.max(state.chatEventSequences[turnId] || 0, ...events.map(event => Number(event.sequence) || 0));
    renderChatLiveTurn();
  } catch (_) { /* Thread state remains authoritative; retry events on the next poll. */ }
}

async function sendMessage(options = null) {
  if (!options?.content && ['/skills', '/skill'].includes($('#chatInput')?.value.trim())) { openSkillCommands(); return; }
  if (!options?.content && $('#chatInput')?.value.trim() === '/permissions') { openRuntimeSettings(); return; }
  const input = $('#chatInput'); const agent = options?.agent || $('#chatAgent')?.value;
  if (!input || state.chatSubmitPending || state.modelSaving) return;
  if (state.chatUnknownSubmission) return toast('上次提交结果尚未确认，请先刷新提交状态', true);
  if (state.chatAttachments.some(item => item.status === 'uploading')) return toast('请等待附件上传完成', true);
  const attachments = options?.attachments || state.chatAttachments.filter(item => item.status === 'ready');
  const content = options?.content || input.value.trim() || (attachments.length ? '请分析附件内容。' : '');
  if (!content) return;
  if (!agent) return toast('请先创建并选择智能体', true);
  const payload = { content, agent_id: agent, attachment_ids: attachments.map(item => item.id), interrupt: options?.interrupt === true, submission_id: chatSubmissionId() };
  if (options?.retry_of) payload.retry_of = options.retry_of;
  if (state.activeProjectId) { payload.project_id = state.activeProjectId; payload.save_to_project = true; }
  if (options && Object.hasOwn(options, 'save_to_project')) { payload.save_to_project = options.save_to_project === true; payload.project_id = options.project_id ?? null; }
  state.chatSubmitPending = true; updateComposerControls();
  try {
    await ensureChatThread(agent);
    const threadId = state.thread;
    let result;
    try { result = await conversationApi(`/api/threads/${encodeURIComponent(threadId)}/queue`, { method: 'POST', body: JSON.stringify(payload) }); }
    catch (error) {
      const confirmed = await conversationApi(`/api/threads/${encodeURIComponent(threadId)}/queue?submission_id=${encodeURIComponent(payload.submission_id)}`).catch(() => null);
      const found = confirmed?.data?.find(item => item.submission_id === payload.submission_id);
      if (found) result = { message: found };
      else if (confirmed && [400,401,403,404,409,422].includes(error.status)) throw error;
      else { rememberUnknownChatSubmission({ submission_id: payload.submission_id, payload, preserveDraft: options?.preserveDraft === true, error: error.message }); renderChatQueue(); toast('提交结果尚未确认，已锁定发送；请刷新提交状态，避免重复执行', true); return; }
    }
    const message = result?.message;
    if (!message?.id) { rememberUnknownChatSubmission({ submission_id: payload.submission_id, payload, preserveDraft: options?.preserveDraft === true }); renderChatQueue(); return; }
    state.chatLastMutationAt = Date.now();
    acceptQueuedChatMessage(message);
    if (result.interaction && !state.chatInteractions.some(item => item.id === result.interaction.id)) state.chatInteractions.push(result.interaction);
    if (!options?.preserveDraft) {
      if (input.value.trim() === content || (!input.value.trim() && attachments.length)) input.value = '';
      input.style.height = '64px';
      state.chatAttachments = state.chatAttachments.filter(item => !attachments.some(sent => sent.id === item.id));
    }
    renderChatAttachments(); syncActiveChatTurn(); renderChatQueue();
    startChatPolling();
    toast(payload.interrupt ? '调整指令已提交，停止当前任务后执行' : message.status === 'pending' ? '已加入待执行队列' : '任务已提交');
    return message;
  } catch (error) { toast(`提交失败：${error.message}`, true); }
  finally { state.chatSubmitPending = false; updateComposerControls(); saveComposerDraft(); }
}

async function refreshUnknownChatSubmission() {
  const unknown = state.chatUnknownSubmission; if (!unknown || !state.thread) return;
  const threadId = state.thread;
  try {
    const response = await conversationApi(`/api/threads/${encodeURIComponent(threadId)}/queue?submission_id=${encodeURIComponent(unknown.submission_id)}`);
    if (threadId !== state.thread || unknown.submission_id !== state.chatUnknownSubmission?.submission_id) return;
    const message = response.data?.find(item => item.submission_id === unknown.submission_id);
    if (!message) { rememberUnknownChatSubmission({ ...unknown, retryAllowed: true }); renderChatQueue(); return toast('暂未找到原提交，可继续刷新，或用原提交标识重试；不会创建第二个任务', true); }
    clearConfirmedChatDraft(unknown);
    acceptQueuedChatMessage(message);
    renderChatAttachments(); syncActiveChatTurn(); renderChatQueue(); updateComposerControls(); startChatPolling(); toast('提交已确认，已恢复任务状态');
  } catch (error) { toast(`无法确认提交：${error.message}`, true); }
}

async function retryUnknownChatSubmission() {
  const unknown = state.chatUnknownSubmission;
  if (!unknown?.retryAllowed || state.chatSubmitPending) return;
  state.chatSubmitPending = true; updateComposerControls();
  try {
    const result = await conversationApi(`/api/threads/${encodeURIComponent(state.thread)}/queue`, { method: 'POST', body: JSON.stringify(unknown.payload) });
    if (!result.message?.id || result.message.submission_id !== unknown.submission_id) throw new Error('服务端未返回可确认的原提交状态');
    clearConfirmedChatDraft(unknown);
    state.chatLastMutationAt = Date.now();
    acceptQueuedChatMessage(result.message);
    syncActiveChatTurn(); renderChatQueue(); startChatPolling(); toast('原提交已确认');
  } catch (error) { toast(`原提交仍未确认：${error.message}`, true); }
  finally { state.chatSubmitPending = false; updateComposerControls(); }
}

async function stopGeneration() {
  if (!state.thread || !state.activeTurn || state.chatStopPending) return;
  state.chatStopPending = true; updateComposerControls(); renderChatLiveTurn();
  try {
    await conversationApi(`/api/threads/${encodeURIComponent(state.thread)}/turns/active`, { method: 'DELETE' });
    state.chatLastMutationAt = Date.now();
    await refreshPersistentChat();
    toast('已请求停止当前任务；排队任务已保留');
  } catch (error) { toast(`停止失败：${error.message}；后台任务可能仍在执行，请刷新状态`, true); }
  finally { state.chatStopPending = false; updateComposerControls(); renderChatLiveTurn(); }
}

async function cancelQueuedChatMessage(button) {
  if (!state.thread || button.disabled) return;
  button.disabled = true;
  try { await conversationApi(`/api/threads/${encodeURIComponent(state.thread)}/queue/${encodeURIComponent(button.dataset.messageId)}`, { method: 'DELETE' }); state.chatLastMutationAt = Date.now(); await refreshPersistentChat(); toast('已取消排队任务'); }
  catch (error) { button.disabled = false; toast(`取消失败：${error.message}`, true); }
}

async function retryQueuedChatMessage(button) {
  if (button.disabled || state.chatSubmitPending) return;
  const item = state.chatQueue.find(message => message.id === button.dataset.messageId);
  const key = `${state.thread}:${item?.id}`;
  if (!item || item.dismissed_at || state.chatQueueMutations[key] || !['failed','cancelled'].includes(item.run_status || item.status)) return;
  state.chatQueueMutations[key] = 'retry';
  button.disabled = true;
  try {
    return await sendMessage({ content: item.content, agent: item.agent_id || $('#chatAgent')?.value, attachments: (item.attachment_ids || []).map(id => ({ id, status: 'ready' })), retry_of: item.id });
  } finally { delete state.chatQueueMutations[key]; button.disabled = false; renderChatQueue(); }
}

async function dismissQueuedChatMessage(button) {
  const threadId = state.thread;
  const item = state.chatQueue.find(message => message.id === button.dataset.messageId);
  const key = `${threadId}:${item?.id}`;
  if (!threadId || !item || button.disabled || state.chatQueueMutations[key] || item.dismissed_at || (item.status !== 'failed' && item.run_status !== 'failed')) return;
  if (state.chatUnknownSubmission?.payload?.retry_of === item.id) return toast('请先确认重试提交状态', true);
  state.chatQueueMutations[key] = 'dismiss'; button.disabled = true; renderChatQueue();
  try {
    const result = await conversationApi(`/api/threads/${encodeURIComponent(threadId)}/queue/${encodeURIComponent(item.id)}/dismiss`, { method: 'POST' });
    if (!result.message?.dismissed_at) throw new Error('服务端尚未确认删除，请刷新后重试');
    if (state.thread !== threadId) return;
    state.chatLastMutationAt = Date.now(); acceptQueuedChatMessage(result.message); renderChatQueue();
    toast('已删除失败提示，执行历史和项目文件已保留');
  } catch (error) { if (state.thread === threadId) toast(`删除失败：${error.message}`, true); }
  finally { delete state.chatQueueMutations[key]; button.disabled = false; if (state.thread === threadId) renderChatQueue(); }
}

function answerChatOption(button) { return answerChatInteraction(button, { option_id: button.dataset.optionId }); }
function answerChatQuestion(button) { const answer = document.getElementById(`interactionAnswer_${button.dataset.interactionId}`)?.value.trim(); if (!answer) return toast('请输入回答', true); return answerChatInteraction(button, { answer }); }
function answerChatProject(button, create) { const id = button.dataset.interactionId; const value = document.getElementById(`${create ? 'interactionProjectName' : 'interactionProject'}_${id}`)?.value.trim(); if (!value) return toast(create ? '请输入项目名称' : '请选择项目', true); return answerChatInteraction(button, create ? { new_project_name: value } : { project_id: value }); }
function answerChatDecision(button) { return answerChatInteraction(button, { card_id: button.dataset.cardId, action_id: button.dataset.actionId }); }

async function answerChatInteraction(button, answer) {
  const id = button.dataset.interactionId; const item = state.chatInteractions.find(interaction => interaction.id === id);
  if (!item || item.status !== 'pending' || button.disabled) return;
  const key = answer.card_id ? `${id}:${answer.card_id}` : id;
  const previous = state.chatInteractionSubmissions[key];
  if (previous?.pending || previous?.unknown) return;
  const payload = { ...answer, submission_id: previous?.submission_id || chatSubmissionId() };
  state.chatInteractionSubmissions[key] = { submission_id: payload.submission_id, payload, pending: true };
  state.chatAnswersPendingCount = (state.chatAnswersPendingCount || 0) + 1; state.approvalPending = true;
  persistChatInteractionSubmissions();
  const card = document.getElementById(`interaction_${id}`);
  const controls = answer.card_id ? button.closest?.('.decision-card')?.querySelectorAll('button,input,textarea,select') : card?.querySelectorAll('button,input,textarea,select');
  controls?.forEach(control => { control.disabled = true; });
  try {
    const result = await conversationApi(`/api/threads/${encodeURIComponent(state.thread)}/interactions/${encodeURIComponent(id)}/answer`, { method: 'POST', body: JSON.stringify(payload) });
    state.chatLastMutationAt = Date.now();
    if (result.interaction) state.chatInteractions = state.chatInteractions.map(old => old.id === id ? result.interaction : old);
    state.chatInteractionSubmissions[key] = { ...state.chatInteractionSubmissions[key], pending: false, accepted: true };
    if (card && result.interaction) { card.outerHTML = chatInteractionHtml(result.interaction); state.chatInteractionSignatures[id] = chatInteractionSignature(result.interaction); }
    syncActiveChatTurn(); updateComposerControls(); toast('回答已接收，后台继续执行'); startChatPolling();
  } catch (error) {
    const response = await conversationApi(`/api/threads/${encodeURIComponent(state.thread)}/interactions`).catch(() => null);
    const found = response?.data?.find(interaction => interaction.id === id);
    const accepted = found && (answer.card_id ? !!found.response?.cards?.[answer.card_id] : found.status !== 'pending' || found.submission_id === payload.submission_id || found.response?.submission_id === payload.submission_id);
    if (accepted) { state.chatInteractions = state.chatInteractions.map(old => old.id === id ? found : old); state.chatInteractionSubmissions[key] = { ...state.chatInteractionSubmissions[key], pending: false, accepted: true }; if (card) card.outerHTML = chatInteractionHtml(found); toast('回答已接收，已恢复后台状态'); }
    else {
      const definiteFailure = found && [400,401,403,404,409,422].includes(error.status);
      state.chatInteractionSubmissions[key] = { ...state.chatInteractionSubmissions[key], pending: false, unknown: !definiteFailure, error: definiteFailure ? error.message : '提交结果尚未确认，请刷新状态，避免重复提交。' };
      const errorBox = document.getElementById(`interactionError_${id}`); if (errorBox) errorBox.textContent = state.chatInteractionSubmissions[key].error;
      if (definiteFailure) controls?.forEach(control => { control.disabled = false; });
      else card?.querySelector('.chat-interaction')?.insertAdjacentHTML('beforeend', `<button class="button button-quiet button-small" type="button" data-interaction-id="${esc(id)}" data-card-id="${esc(answer.card_id || '')}" onclick="refreshChatInteractionStatus(this)">刷新提交状态</button>`);
      toast(state.chatInteractionSubmissions[key].error, true);
    }
  } finally { state.chatAnswersPendingCount--; state.approvalPending = state.chatAnswersPendingCount > 0; applyPersistentChatInteractions(); persistChatInteractionSubmissions(); }
}

async function refreshChatInteractionStatus(button) {
  const id = button.dataset.interactionId; const key = button.dataset.cardId ? `${id}:${button.dataset.cardId}` : id;
  const threadId = state.thread;
  try {
    const response = await conversationApi(`/api/threads/${encodeURIComponent(threadId)}/interactions`);
    if (threadId !== state.thread) return;
    const item = response.data?.find(interaction => interaction.id === id); if (!item) return toast('未找到交互状态，请刷新会话', true);
    const submission = state.chatInteractionSubmissions[key];
    const accepted = button.dataset.cardId ? !!item.response?.cards?.[button.dataset.cardId] : item.status !== 'pending' || item.submission_id === submission?.submission_id;
    if (!accepted) {
      if (submission && item.status === 'pending') {
        submission.retryAllowed = true;
        button.disabled = true;
        button.insertAdjacentHTML?.('afterend', `<button type="button" class="button button-quiet button-small" data-interaction-id="${esc(id)}" data-card-id="${esc(button.dataset.cardId || '')}" onclick="retryChatInteractionSubmission(this)" title="复用原回答和原提交标识">重试原回答</button>`);
        return toast('暂未找到已接收状态；可以用原提交标识重试原回答，其他回答保持锁定', true);
      }
      return toast('提交状态仍未确认，原回答保持锁定，请稍后刷新', true);
    }
    state.chatInteractions = state.chatInteractions.map(old => old.id === id ? item : old); delete state.chatInteractionSubmissions[key];
    const card = document.getElementById(`interaction_${id}`); if (card) card.outerHTML = chatInteractionHtml(item);
    applyPersistentChatInteractions();
    persistChatInteractionSubmissions(); syncActiveChatTurn(); updateComposerControls(); startChatPolling(); toast('已确认回答状态');
  } catch (error) { toast(`状态刷新失败：${error.message}`, true); }
}

function retryChatInteractionSubmission(button) {
  const key = button.dataset.cardId ? `${button.dataset.interactionId}:${button.dataset.cardId}` : button.dataset.interactionId;
  const submission = state.chatInteractionSubmissions[key];
  if (!submission?.retryAllowed || submission.pending) return;
  submission.unknown = false;
  return answerChatInteraction(button, submission.payload);
}

async function refreshSidebarThreads() {
  try {
    const result = await api(`/api/threads?archived=${state.threadScope === 'archived'}`);
    state.chatThreads = result.data; renderChatHistory();
    const current = result.data.find(item => item.id === state.thread);
    const title = $('.conversation-title strong'); if (current && title) title.textContent = current.name;
  } catch (_) { /* Current conversation remains usable if history refresh fails. */ }
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
window.addEventListener('resize', syncRailAccessibility);
window.addEventListener('resize', () => {
  if (state.page === 'chat' && state.fileWorkspace && state.filesPanelOpen) applyFileSplit(state.fileWorkspace.ratio, false);
});

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
refreshSidebarThreads();
