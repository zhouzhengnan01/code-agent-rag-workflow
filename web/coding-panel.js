(function () {
  'use strict';
  let layer, activeThread, selectedTab = 'plan', snapshot = {}, previousFocus, requestId = 0;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const stringify = value => JSON.stringify(value ?? {}, null, 2);
  const current = () => typeof state !== 'undefined' ? state : null;
  const request = (path, options) => api(path, options); // Existing cookie/admin/CSRF handling, no new credentials.
  const route = suffix => `/api/threads/${encodeURIComponent(activeThread)}${suffix}`;
  const tabs = { plan: '计划', quality: '质量门', checkpoints: '快照 / Diff', context: '上下文' };
  function close() { requestId++; layer?.remove(); layer = null; previousFocus?.focus?.(); }
  function action(label, handler) { const b = document.createElement('button'); b.type = 'button'; b.className = 'coding-action'; b.textContent = label; b.addEventListener('click', handler); return b; }
  function propose(prompt) {
    if (current()?.thread !== activeThread) { showError('当前对话已切换，请重新打开工程面板。'); return; }
    const input = document.querySelector('#chatInput');
    if (!input || input.disabled) { showError('当前无法编辑消息，请等待提交完成。'); return; }
    if (input.value.trim() && !window.confirm('替换当前尚未发送的草稿？')) return;
    close();
    fillChatPrompt(prompt);
    // Only fills a visible draft. User still sends and explicitly approves tool actions.
  }
  function showError(message) { const node = layer?.querySelector('.coding-panel-body'); if (node) node.innerHTML = `<p class="coding-error">${escape(message)}</p>`; }
  function draw() {
    if (!layer) return;
    const body = layer.querySelector('.coding-panel-body');
    const engineering = snapshot.engineering || {};
    layer.querySelectorAll('[role=tab]').forEach(tab => tab.setAttribute('aria-selected', String(tab.dataset.tab === selectedTab)));
    const footer = layer.querySelector('footer'); footer.replaceChildren();
    if (selectedTab === 'plan') {
      const plan = engineering.plan || {};
      body.innerHTML = `<p class="coding-note">工作区：${escape(snapshot.workspace?.path || snapshot.workspace || '未选择')}。计划批准与文件写入仍通过原对话审批。</p><p class="coding-status">${escape(plan.status || '尚无计划')}</p>${(plan.steps || []).map(step => `<div class="coding-item">${escape(step.status)} · ${escape(step.content)}</div>`).join('')}<p>必要检查：${escape((plan.required_checks || []).join(', ') || '未设置')}</p>`;
      footer.append(action('在对话中制定计划', () => propose('请为当前任务使用 plan_manage 制定工程计划与明确的测试/lint/类型检查验收条件，等待我确认计划后再执行。')));
      if (plan.status === 'proposed') footer.append(action('请求批准此计划', () => propose(`请重新读取当前 plan_manage 计划，用 expected_revision=${plan.revision} 请求我审批批准此版本；如果版本已经变化则重新展示计划，不要把此消息当作自动授予文件或 Shell 权限。`)));
    } else if (selectedTab === 'quality') {
      const quality = engineering.quality || {};
      body.innerHTML = `<p class="coding-note">检查结果绑定源文件指纹。代码再次变化后必须重跑，未执行不等于通过。</p><p class="coding-status">${escape(quality.status || '尚未执行检查')}</p>${(quality.checks || []).map(check => `<section class="coding-item"><strong>${escape(check.name)} · exit ${escape(check.exit_code ?? 'unknown')}</strong><pre>${escape(check.command)}\n${escape(check.stdout)}\n${escape(check.stderr)}</pre></section>`).join('')}${quality.baseline_comparison ? `<pre>${escape(stringify(quality.baseline_comparison))}</pre>` : ''}`;
      footer.append(action('发现并运行检查', () => propose('请先使用 quality_discover 识别当前项目合适的测试、lint 与类型检查，解释命令后经我审批使用 quality_run 执行，输出真实 exit_code，禁止把未执行视为通过。')));
      footer.append(action('独立代码审查', () => propose('请调用 engineering_review 对当前项目真实变更执行独立审查，报告路径、行号、严重程度和证据，明确 partial/未覆盖项，不要仅返回 Git diff。')));
      footer.append(action('配置完成前 Hook', () => propose('请展示现有 hook_manage 配置并帮助配置 Stop 质量检查 Hook。先说明完整命令、在现有 Docker 沙箱执行及失败阻止完成的行为，等待我明确批准，禁止自动加载仓库 Hooks。')));
    } else if (selectedTab === 'checkpoints') {
      const checkpoints = snapshot.checkpoints || [];
      body.innerHTML = `<p class="coding-note">快照仅包含显式选择的文件。回退必须预览 Diff 并审批；预览后文件发生变化会拒绝覆盖，不恢复外部系统或会话历史。</p>`;
      if (!checkpoints.length) body.insertAdjacentHTML('beforeend', '<p>当前任务尚无文件快照。</p>');
      for (const item of checkpoints) {
        const row = document.createElement('section'); row.className = 'coding-item';
        const title = document.createElement('strong'); title.textContent = item.label || item.id || item.checkpoint_id; row.append(title);
        const id = item.id || item.checkpoint_id;
        const meta = document.createElement('p'); meta.className = 'coding-note'; meta.textContent = id; row.append(meta);
        row.append(action('查看 Diff', () => showDiff(id))); body.append(row);
      }
      footer.append(action('请求创建快照', () => propose('请列出当前任务即将修改的真实文件，使用 task_checkpoint 保存这些显式路径的原始字节（尚不存在但将创建的文件也列入），再进行后续写入审批。不要快照整个磁盘。')));
    } else {
      body.innerHTML = `<p class="coding-note">这里只展示上下文预算、摘要与执行状态，不展示模型私有思维链。</p><pre>${escape(stringify(snapshot.context))}</pre>`;
    }
  }
  async function showDiff(id) {
    const ticket = ++requestId;
    try {
      layer.querySelector('.coding-panel-body').textContent = '正在读取真实文件差异…';
      const response = await request(route('/coding/inspect'), { method: 'POST', body: JSON.stringify({ name: 'task_diff', args: { checkpoint_id: id } }) });
      if (!layer || ticket !== requestId) return;
      const data = response.result || response;
      const body = layer.querySelector('.coding-panel-body'); body.innerHTML = '<p class="coding-note">当前真实文件与快照之间的差异；此操作没有修改任何文件。</p>';
      for (const item of data.changes || []) {
        const box = document.createElement('section'); box.className = 'coding-diff';
        const title = document.createElement('h4'); title.textContent = item.path; box.append(title);
        for (const line of String(item.diff || '').split('\n')) { const node = document.createElement('span'); node.className = line.startsWith('+') ? 'added' : line.startsWith('-') ? 'removed' : ''; node.textContent = line + '\n'; box.append(node); }
        body.append(box);
      }
      if (!(data.changes || []).length) body.insertAdjacentHTML('beforeend', '<p>没有差异。</p>');
      const footer = layer.querySelector('footer'); footer.replaceChildren(action('返回快照列表', draw));
      if (data.expected_hashes && (data.changes || []).length) footer.append(action('在对话中请求回退', () => propose(`请按已预览的参数调用 task_rewind，必须等待我的工具审批。如果哈希不匹配，拒绝覆盖并重新预览，不要强制回退。参数：${JSON.stringify({ checkpoint_id: id, expected_hashes: data.expected_hashes })}`)));
    } catch (error) { if (layer && ticket === requestId) showError(error.message); }
  }
  async function refresh() {
    const ticket = ++requestId;
    try {
      const data = await request(route('/coding/state'));
      if (!layer || ticket !== requestId) return;
      snapshot = data; draw();
    } catch (error) { if (layer && ticket === requestId) showError(error.message); }
  }
  function open() {
    if (!current()?.thread) return;
    close(); activeThread = current().thread; previousFocus = document.activeElement;
    layer = document.createElement('div'); layer.className = 'coding-panel-layer';
    layer.innerHTML = `<section class="coding-panel" role="dialog" aria-modal="true" aria-labelledby="codingPanelTitle"><header><h2 id="codingPanelTitle">工程工作台</h2><button type="button" class="coding-action" data-close>关闭</button></header><div class="coding-tabs" role="tablist">${Object.entries(tabs).map(([id, label]) => `<button type="button" role="tab" data-tab="${id}" aria-selected="${id === selectedTab}">${label}</button>`).join('')}</div><div class="coding-panel-body" role="tabpanel">正在加载…</div><footer></footer></section>`;
    layer.addEventListener('click', event => { if (event.target === layer || event.target.closest('[data-close]')) close(); const tab = event.target.closest('[data-tab]'); if (tab) { selectedTab = tab.dataset.tab; draw(); } });
    layer.addEventListener('keydown', event => { if (event.key === 'Escape') close(); if (event.key === 'Tab') { const list = [...layer.querySelectorAll('button:not([disabled])')]; const first = list[0], last = list.at(-1); if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); } } });
    document.body.append(layer); layer.querySelector('[data-close]').focus(); refresh();
  }
  function mount() {
    const host = document.querySelector('.conversation-header-actions');
    if (host && current()?.thread && !host.querySelector('.coding-launch')) { const button = document.createElement('button'); button.type = 'button'; button.className = 'coding-launch'; button.textContent = '工程'; button.setAttribute('aria-haspopup', 'dialog'); button.addEventListener('click', open); host.prepend(button); }
    if (layer && (current()?.thread !== activeThread || current()?.page !== 'chat')) close();
  }
  const target = document.querySelector('#content');
  if (target) new MutationObserver(mount).observe(target, { childList: true, subtree: true });
  mount();
  if (typeof module !== 'undefined' && module.exports) module.exports = { escape, open, close, showDiff, propose, mount };
})();
