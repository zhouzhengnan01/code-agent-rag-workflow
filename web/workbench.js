const pages = [
  { id: 'dashboard', label: '概览', short: 'HOME' },
  { id: 'chat', label: '对话调试', short: 'CHAT' },
  { id: 'agents', label: '智能体', short: 'AGENT' },
  { id: 'providers', label: '模型接入', short: 'MODEL' },
  { id: 'skills', label: '技能', short: 'SKILL' },
  { id: 'mcp_servers', label: 'MCP 服务', short: 'MCP' },
  { id: 'knowledge', label: '知识库', short: 'RAG' },
  { id: 'workflows', label: '工作流', short: 'FLOW' },
];

const navGroups = [
  ['工作区', ['dashboard', 'chat']],
  ['构建', ['agents', 'providers', 'skills', 'mcp_servers', 'knowledge']],
  ['编排', ['workflows']],
];

const labels = {
  agents: ['智能体', '将模型、提示词、知识与工具组合成可运行的智能体。'],
  providers: ['模型接入', '管理 OpenAI-compatible 推理端点和模型凭据。'],
  skills: ['技能', '维护可插拔的 SKILL.md 指令包。'],
  mcp_servers: ['MCP 服务', '连接外部工具、服务和数据源。'],
  knowledge: ['知识库', '上传文档，构建可检索的 RAG 上下文。'],
  workflows: ['工作流', '把智能体和工具编排成可重复运行的流程。'],
};

const resourceKinds = Object.keys(labels);
let state = { page: 'dashboard', cache: {}, thread: null, threadScope: 'active', chatThreads: [] };

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

function nav() {
  const byId = Object.fromEntries(pages.map(page => [page.id, page]));
  $('#nav').innerHTML = navGroups.map(([group, ids]) => `
    <section class="nav-group" aria-label="${esc(group)}">
      <div class="nav-group-label">${esc(group)}</div>
      ${ids.map(id => {
        const page = byId[id];
        const active = state.page === id;
        return `
          <button class="nav-item ${active ? 'is-active' : ''}" type="button" onclick="go('${id}')" ${active ? 'aria-current="page"' : ''}>
            <span class="nav-label">${page.label}</span><span class="nav-short">${page.short}</span>
          </button>`;
      }).join('')}
    </section>`).join('');
}

function go(page) {
  state.page = page;
  toggleRail(false);
  if (location.hash !== `#${page}`) history.replaceState(null, '', `#${page}`);
  nav();
  $('#pageTitle').textContent = pages.find(item => item.id === page)?.label || page;
  loadPage();
}

function quickCreate() {
  if (state.page === 'chat') return newThread();
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
  content.classList.toggle('viewport-chat', state.page === 'chat');
  content.innerHTML = loading();
  try {
    if (state.page === 'dashboard') return dashboard();
    if (state.page === 'chat') return chat();
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
  const kinds = ['agents', 'providers', 'skills', 'mcp_servers', 'knowledge', 'workflows'];
  const [all, recent, rag] = await Promise.all([
    Promise.all(kinds.map(load)),
    api('/api/threads'),
    api('/api/rag/status').catch(() => ({ ok: false, backend: '未连接', collections: 0 })),
  ]);
  const map = Object.fromEntries(kinds.map((kind, index) => [kind, all[index]]));
  const configured = map.providers.filter(item => item.api_key_configured).length;
  const documents = map.knowledge.reduce((sum, item) => sum + Number(item.document_count || 0), 0);
  const stats = [
    ['智能体', map.agents.length, '可运行配置'],
    ['模型', map.providers.length, `${configured} 个密钥已就绪`],
    ['技能', map.skills.length, '可插拔指令'],
    ['知识文档', documents, `${rag.collections || 0} 个向量集合`],
  ];
  const setup = [
    ['连接模型', '配置百炼或其他兼容模型', 'providers', 'MODEL'],
    ['装配智能体', '选择模型、技能、知识和工具', 'agents', 'AGENT'],
    ['导入知识', '上传资料并验证检索结果', 'knowledge', 'RAG'],
    ['编排流程', '组合节点并运行自动化任务', 'workflows', 'FLOW'],
  ];

  $('#content').innerHTML = `
    <div class="dashboard-page page-enter">
      <section class="dashboard-lead">
        <div class="lead-copy">
          <span class="overline">本地智能体工作区</span>
          <h1>智能体，从构建到运行。</h1>
          <p>组合 Qwen、技能、MCP、知识库和工作流，直接在本地验证结果。</p>
          <div class="lead-actions">
            <button class="button button-primary button-large" type="button" onclick="go('chat')">开始对话</button>
            <button class="button button-quiet button-large" type="button" onclick="go('agents')">配置智能体</button>
          </div>
        </div>
        <aside class="runtime-panel">
          <div class="runtime-heading"><span>系统运行状态</span><strong>${rag.ok ? '就绪' : '检查配置'}</strong></div>
          <dl>
            <div><dt>推理提供方</dt><dd>${configured}/${map.providers.length}</dd></div>
            <div><dt>向量后端</dt><dd>${esc(rag.backend || '未连接')}</dd></div>
            <div><dt>工作流</dt><dd>${map.workflows.length}</dd></div>
          </dl>
          <button class="text-action" type="button" onclick="go('providers')">查看运行配置</button>
        </aside>
      </section>

      <section class="stat-ribbon" aria-label="工作区统计">
        ${stats.map(([name, value, note]) => `
          <div class="stat-item"><span>${name}</span><strong>${value}</strong><small>${note}</small></div>`).join('')}
      </section>

      <div class="dashboard-work">
        <section class="launch-panel">
          <header class="block-heading"><div><h2>构建路径</h2><p>按能力链路继续配置。</p></div></header>
          <div class="launch-grid">
            ${setup.map(([name, note, page, code]) => `
              <button class="launch-item" type="button" onclick="go('${page}')">
                <span class="launch-code">${code}</span><span><strong>${name}</strong><small>${note}</small></span><b aria-hidden="true">打开</b>
              </button>`).join('')}
          </div>
        </section>
        <aside class="activity-panel">
          <header class="block-heading"><div><h2>最近对话</h2><p>${recent.data.length} 个活跃会话</p></div><button class="text-action" type="button" onclick="go('chat')">全部</button></header>
          ${recent.data.length ? `
            <div class="activity-list">
              ${recent.data.slice(0, 5).map(thread => `
                <button class="activity-item" type="button" onclick="state.threadScope='active';state.thread='${thread.id}';go('chat')">
                  <span><strong>${esc(thread.name)}</strong><small>${esc(thread.status)}</small></span><b>打开</b>
                </button>`).join('')}
            </div>` : `
            <div class="state-inline"><p>还没有对话记录。</p><button class="text-action" type="button" onclick="go('chat')">创建第一个会话</button></div>`}
        </aside>
      </div>
    </div>`;
}

async function resources(kind) {
  const list = await load(kind);
  const enabled = list.filter(item => item.enabled !== false).length;
  $('#content').innerHTML = `
    <div class="collection-page page-enter">
      <header class="collection-header">
        <div><span class="overline">能力管理</span><h1>${labels[kind][0]}</h1><p>${labels[kind][1]}</p></div>
        <div class="header-actions">
          ${kind === 'skills' ? '<button class="button button-quiet" type="button" onclick="importSkill()">导入 SKILL.md</button>' : ''}
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
  if (kind === 'providers') facts = [item.type === 'bailian' ? '阿里云百炼' : 'OpenAI compatible', `${(item.models || []).length} 个模型`, item.api_key_configured ? '密钥已配置' : '等待密钥'];
  if (kind === 'knowledge') facts = [`${item.document_count || 0} 个文档`, `${item.chunk_count || 0} 个片段`, item.embedding_model || 'qwen3.7-text-embedding'];
  if (kind === 'mcp_servers') facts = [(item.transport || 'stdio').toUpperCase()];
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
        ${kind === 'knowledge' ? `<button class="button button-quiet button-small" type="button" onclick="uploadDoc('${item.id}')">上传文档</button><button class="button button-quiet button-small" type="button" onclick="testKnowledge('${item.id}')">测试检索</button>` : ''}
        ${kind === 'mcp_servers' ? `<button class="button button-quiet button-small" type="button" onclick="testMcp('${item.id}')">测试服务</button>` : ''}
        ${kind === 'workflows' ? `<button class="button button-quiet button-small" type="button" onclick="runWorkflow('${item.id}')">运行</button>` : ''}
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
  if (kind === 'knowledge') return knowledgeForm(item || {});
  if (kind === 'agents') return agentForm(item || {});
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
    </form>`, () => {
      const data = formData($('#editForm'));
      delete data.preset;
      data.models = data.models.split(',').map(value => value.trim()).filter(Boolean);
      data.timeout = Number(data.timeout);
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
  modal(item.id ? '编辑知识库' : '新建知识库', `
    <form id="editForm" class="form-layout">
      ${field('名称', 'name', item.name)}${field('描述', 'description', item.description)}
      <section class="form-section control-full"><header><h3>向量索引</h3><p>修改模型或维度后，需要重新上传文档。</p></header></section>
      ${selectField('Embedding 提供方', 'embedding_provider_id', providers.map(value => `<option value="${value.id}" ${provider === value.id ? 'selected' : ''}>${esc(value.name)}</option>`).join(''))}
      ${field('Embedding 模型', 'embedding_model', item.embedding_model || 'qwen3.7-text-embedding')}
      ${field('向量维度', 'embedding_dimension', item.embedding_dimension || 1024, 'number')}
      ${field('重排序模型', 'rerank_model', item.rerank_model || 'qwen3-rerank')}
      ${toggleField('启用知识库', 'enabled', item.enabled !== false, true)}
    </form>`, () => {
      const data = formData($('#editForm'));
      data.embedding_dimension = Number(data.embedding_dimension);
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

async function agentForm(item) {
  const sandboxModes = [
    { value: 'read-only', label: '只读（read-only）' },
    { value: 'workspace-write', label: '工作区可写（workspace-write）' },
  ];
  const selectedSandbox = item.sandbox_mode ?? 'read-only';
  const unsupportedSandbox = !sandboxModes.some(mode => mode.value === selectedSandbox);
  const sandboxOptions = (unsupportedSandbox ? '<option value="" selected disabled>旧配置不受支持，请重新选择</option>' : '')
    + sandboxModes.map(mode => `<option value="${mode.value}" ${selectedSandbox === mode.value ? 'selected' : ''}>${mode.label}</option>`).join('');
  const [providers, skills, knowledge, mcps] = await Promise.all(['providers', 'skills', 'knowledge', 'mcp_servers'].map(load));
  const tools = [{ id: 'knowledge_search', name: '知识检索' }, { id: 'list_files', name: '列目录' }, { id: 'read_file', name: '读文件' }, { id: 'write_file', name: '写文件' }, { id: 'apply_patch', name: '应用补丁' }, { id: 'run_shell', name: 'Shell' }, { id: 'git_status', name: 'Git 状态' }, { id: 'git_diff', name: 'Git 差异' }, { id: 'git_log', name: 'Git 日志' }, { id: 'review', name: '代码审查' }];
  modal(item.id ? '编辑智能体' : '新建智能体', `
    <form id="editForm" class="form-layout">
      <section class="form-section control-full"><header><h3>身份与模型</h3><p>定义智能体的职责和推理模型。</p></header></section>
      ${field('名称', 'name', item.name)}${field('描述', 'description', item.description)}
      ${selectField('模型提供方', 'provider_id', providers.map(value => `<option value="${value.id}" ${item.provider_id === value.id ? 'selected' : ''}>${esc(value.name)}</option>`).join(''))}
      ${field('模型名称', 'model', item.model || providers[0]?.default_model || '')}
      ${field('系统提示词', 'system_prompt', item.system_prompt || '你是一个可靠的智能体。', 'textarea', true)}
      ${field('Temperature', 'temperature', item.temperature ?? 0.2, 'number')}${field('最大工具轮次', 'max_tool_rounds', item.max_tool_rounds || 6, 'number')}
      <section class="form-section control-full"><header><h3>能力装配</h3><p>选择这个智能体可以访问的能力。</p></header></section>
      ${choiceGroup('技能', 'skill_ids', skills, item.skill_ids)}
      ${choiceGroup('知识库', 'knowledge_ids', knowledge, item.knowledge_ids)}
      ${choiceGroup('MCP 服务', 'mcp_server_ids', mcps, item.mcp_server_ids)}
      ${choiceGroup('内置工具', 'builtin_tools', tools, item.builtin_tools || [])}
      <section class="form-section control-full"><header><h3>执行权限与沙箱</h3><p>沙箱模式不会自动开启 Shell、自动批准或启动沙箱服务。</p></header></section>
      ${selectField('沙箱模式', 'sandbox_mode', sandboxOptions, true, '只读：容器不能写入工作区；工作区可写：容器可修改工作区文件。两种模式均禁止联网，Git 查询始终只读。MCP 不受此沙箱模式隔离。旧配置未指定模式时，保存会设为只读；不支持 danger-full-access。')}
      ${toggleField('允许执行 Shell', 'allow_shell', item.allow_shell === true)}${toggleField('自动批准写入、Shell 和 MCP', 'auto_approve', item.auto_approve === true)}${toggleField('启用智能体', 'enabled', item.enabled !== false)}
    </form>`, () => {
      const data = formData($('#editForm'));
      if (!sandboxModes.some(mode => mode.value === data.sandbox_mode)) {
        toast('请选择有效的沙箱模式：只读或工作区可写', true);
        return;
      }
      for (const name of ['skill_ids', 'knowledge_ids', 'mcp_server_ids', 'builtin_tools']) {
        data[name] = $$(`#editForm [name=${name}]:checked`).map(input => input.value);
      }
      data.temperature = Number(data.temperature);
      data.max_tool_rounds = Number(data.max_tool_rounds);
      data.allow_shell = $('#editForm [name=allow_shell]').checked;
      data.auto_approve = $('#editForm [name=auto_approve]').checked;
      data.enabled = $('#editForm [name=enabled]').checked;
      save('agents', item.id, data);
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
      ${field('工作流 JSON', 'definition', JSON.stringify({ nodes: sample.nodes, edges: sample.edges }, null, 2), 'textarea', true, '节点类型：input / prompt / agent / knowledge / mcp / output')}
      ${toggleField('启用工作流', 'enabled', sample.enabled, true)}
    </form>`, () => {
      try {
        const data = formData($('#editForm'));
        const definition = JSON.parse(data.definition);
        save('workflows', item.id, { name: data.name, description: data.description, enabled: $('#editForm [name=enabled]').checked, nodes: definition.nodes || [], edges: definition.edges || [] });
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
  modal('导入 SKILL.md', `
    <form id="uploadForm"><label class="drop-field"><input type="file" name="file" accept=".md,text/markdown" required><span class="drop-title">选择 Markdown 文件</span><span>文件会保存为可选择的技能配置。</span></label></form>`, async () => {
      try {
        await api('/api/skills/import', { method: 'POST', body: new FormData($('#uploadForm')) });
        closeModal(); toast('技能已导入'); loadPage();
      } catch (error) { toast(error.message, true); }
    }, false, '导入');
}

function uploadDoc(id) {
  modal('上传知识文档', `
    <form id="uploadForm"><label class="drop-field"><input type="file" name="file" required><span class="drop-title">选择 TXT、MD、JSON、CSV 或 PDF</span><span>文档会被分块、向量化并写入 Milvus。</span></label></form>`, async () => {
      const button = $('#modalSave');
      try {
        button.disabled = true; button.textContent = '向量化中';
        const result = await api(`/api/knowledge/${id}/documents`, { method: 'POST', body: new FormData($('#uploadForm')) });
        closeModal(); toast(`已写入 ${result.chunks} 个 ${result.embedding_dimension} 维片段`); loadPage();
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
    modal('MCP 连接成功', `<div class="result-summary"><strong>${result.tools.length}</strong><span>个可用工具</span></div><pre class="code-output">${esc(JSON.stringify(result.tools, null, 2))}</pre>`);
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
  return ({ idle: '就绪', running: '运行中', error: '出错' })[status] || status || '就绪';
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
  const [agents, threadResult] = await Promise.all([load('agents'), api(`/api/threads?archived=${archived}`)]);
  const threads = threadResult.data;
  state.chatThreads = threads;
  if (!threads.some(thread => thread.id === state.thread)) state.thread = threads[0]?.id || null;
  const current = state.thread ? await api(`/api/threads/${state.thread}`).catch(() => null) : null;
  const selectedAgent = current?.agent_id || agents[0]?.id || '';
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
        <header class="conversation-bar">
          <div class="conversation-title"><span>当前会话</span><strong>${esc(current?.name || '新对话')}</strong></div>
          <label class="agent-selector"><span>运行智能体</span><select id="chatAgent" aria-label="选择智能体">${agents.map(agent => `<option value="${agent.id}" ${selectedAgent === agent.id ? 'selected' : ''}>${esc(agent.name)}</option>`).join('')}</select></label>
        </header>
        <div class="message-stream" id="messages" aria-live="polite">
          ${current?.messages?.length ? current.messages.map(messageHtml).join('') : `
            <div class="conversation-empty"><span class="empty-mark" aria-hidden="true">Z</span><h2>开始调试智能体</h2><p>输入任务，查看模型、工具和知识库如何协同运行。</p></div>`}
        </div>
        <footer class="prompt-dock">
          <textarea id="chatInput" aria-label="消息" rows="1" placeholder="向智能体发送任务"></textarea>
          <div class="prompt-footer"><span>Enter 发送　Shift+Enter 换行</span><button class="button button-primary" id="sendBtn" type="button" onclick="sendMessage()">发送</button></div>
        </footer>
      </section>
    </div>`;
  window.setTimeout(bindComposer, 0);
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

async function sendMessage() {
  let input = $('#chatInput');
  let button = $('#sendBtn');
  let agentSelect = $('#chatAgent');
  if (!input || !button || button.disabled) return;
  const content = input.value.trim();
  const agent = agentSelect?.value;
  if (!content) return;
  if (!agent) { toast('请先创建并选择智能体', true); return; }
  if (!state.thread) {
    const thread = await api('/api/threads', { method: 'POST', body: JSON.stringify({ name: '新对话', agent_id: agent }) });
    state.thread = thread.id;
  }
  const messages = $('#messages');
  const pendingId = `pending_${Date.now()}`;
  messages?.querySelector('.conversation-empty')?.remove();
  messages?.insertAdjacentHTML('beforeend', messageHtml({ role: 'user', content }) + `
    <article class="message-turn assistant is-pending" id="${pendingId}"><div class="turn-avatar" aria-hidden="true">Z</div><div class="turn-content"><header><strong>Codezzn</strong></header><div class="thinking-line"><span></span><span></span><span></span><b>正在检索知识并运行</b></div></div></article>`);
  input.value = '';
  input.style.height = '54px';
  button.disabled = true;
  button.textContent = '运行中';
  agentSelect.disabled = true;
  scrollMessages(true);
  try {
    const response = await fetch(`/api/threads/${state.thread}/turns/stream`, { method: 'POST', headers: headers(), body: JSON.stringify({ content, agent_id: agent }) });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''; let answer = ''; const events = [];
    const renderPending = () => { const pending = document.getElementById(pendingId); if (pending) pending.querySelector('.turn-content').innerHTML = `<header><strong>Codezzn</strong></header><div class="message-copy">${richText(answer)}</div><div class="thinking-line"><b>${esc(events.at(-1)?.status || events.at(-1)?.type || '运行中')}</b></div>`; scrollMessages(); };
    while (true) { const { value, done } = await reader.read(); buffer += decoder.decode(value || new Uint8Array(), { stream: !done }); const parts = buffer.split(/\n\n/); buffer = parts.pop(); for (const part of parts) { const line = part.split('\n').find(item => item.startsWith('data:')); if (!line) continue; const event = JSON.parse(line.slice(5)); events.push(event); if (event.type === 'assistant_delta') answer += event.content || ''; if (event.type === 'turn_result') answer = event.content || answer; renderPending(); } if (done) break; }
    const pending = document.getElementById(pendingId);
    if (pending) pending.outerHTML = messageHtml({ role: 'assistant', content: answer || '模型返回了空响应。', meta: { events, usage: {}, runtime: {}, sources: [] } });
    scrollMessages(true);
  } catch (error) {
    const pending = document.getElementById(pendingId);
    if (pending) pending.outerHTML = messageHtml({ role: 'assistant', content: `请求失败：${error.message}`, error: true });
    toast(error.message, true);
    scrollMessages(true);
  } finally {
    button = $('#sendBtn'); input = $('#chatInput'); agentSelect = $('#chatAgent');
    if (button) { button.disabled = false; button.textContent = '发送'; }
    if (agentSelect) agentSelect.disabled = false;
    if (input) { input.disabled = false; input.focus(); }
  }
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
nav();
$('#pageTitle').textContent = pages.find(item => item.id === state.page).label;
checkHealth();
loadPage();
