/* Document upload and processing views share the workbench's authentication and theme. */
(() => {
  const stageLabels = { ready: '待上传', uploading: '文件传输中', queued: '等待处理', reading: '解析文档',
    splitting: '清洗与分块', embedding: '生成向量', indexing: '写入索引', completed: '可检索',
    submitted: '已提交 RAGFlow，等待解析', submitting: '提交到 RAGFlow', failed: '处理失败', cancelled: '已取消' };
  const extensions = ['.txt', '.md', '.markdown', '.pdf', '.docx', '.json', '.csv'];
  const sizeLabel = bytes => bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  const pathFor = id => `/api/knowledge/${encodeURIComponent(id)}`;
  const stateFor = job => ['failed', 'cancelled', 'queued'].includes(job.status) ? job.status : job.stage || job.status;

  async function request(ui, path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try { return await ui.api(path, { ...options, signal: controller.signal }); }
    catch (error) { if (error.name === 'AbortError') throw new Error('请求超时，请检查服务连接'); throw error; }
    finally { clearTimeout(timer); }
  }

  function transfer(id, file, ui, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${pathFor(id)}/documents?background=true`);
      xhr.withCredentials = true;
      xhr.timeout = 90000;
      for (const [key, value] of Object.entries(ui.headers(false))) xhr.setRequestHeader(key, value);
      xhr.upload.onprogress = event => { if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100)); };
      xhr.onerror = () => reject(new Error('文件传输失败，请检查服务连接后重试'));
      xhr.ontimeout = () => reject(new Error('文件传输超时，请先查看文档状态，确认是否已提交'));
      xhr.onload = () => {
        let body;
        try { body = JSON.parse(xhr.responseText); } catch { reject(new Error('服务返回了无效响应')); return; }
        if (xhr.status < 200 || xhr.status >= 300) { reject(new Error(typeof body.detail === 'string' ? body.detail : `上传失败（HTTP ${xhr.status}）`)); return; }
        resolve(body);
      };
      const data = new FormData();
      data.append('file', file);
      xhr.send(data);
    });
  }

  function openUpload(id, knowledge, ui) {
    let config = { max_upload_bytes: 10 * 1024 * 1024, max_batch_files: 20, extensions: knowledge.backend === 'ragflow' ? [] : extensions };
    let rows = [], uploading = false, timer, polling = false;
    const backend = knowledge.backend === 'ragflow' ? 'RAGFlow' : '本地 Milvus';
    const esc = ui.esc;
    ui.modal(`上传文档 · ${knowledge.name || '知识库'}`, `
      <div id="knowledgeUpload" class="kb-documents">
        <div class="kb-intro"><span class="kb-backend">${backend}</span><h3>把文档变成可检索的资料</h3>
          <p>选择文件后提交，后台会完成解析、分块和索引。处理进度与失败记录会保存。</p></div>
        <label class="kb-drop" id="knowledgeDrop"><input id="knowledgeFiles" type="file" multiple aria-label="选择知识文档" ${config.extensions.length ? `accept="${config.extensions.join(',')}"` : ''}>
          <strong>点击选择或拖入文档</strong><span id="knowledgeLimits"></span></label>
        <p class="kb-notice">${knowledge.backend === 'ragflow' ? '上传成功仅代表已提交到 RAGFlow，需等待远端解析完成。' : '解析 → 清洗与分块 → 生成向量 → 写入索引。扫描 PDF 需先完成 OCR。'}</p>
        <div id="knowledgeUploadError" class="kb-error" role="alert"></div>
        <div id="knowledgeUploadRows" class="kb-file-list" aria-live="polite"></div>
      </div>`, submitFiles, true, '上传并入库');
    const root = document.getElementById('knowledgeUpload');
    const picker = root.querySelector('#knowledgeFiles');
    const drop = root.querySelector('#knowledgeDrop');
    const save = document.getElementById('modalSave');
    const errorBox = root.querySelector('#knowledgeUploadError');
    function render() {
      root.querySelector('#knowledgeLimits').textContent = `${config.extensions.length ? config.extensions.map(x => x.slice(1).toUpperCase()).join(' / ') : '使用 RAGFlow 支持的文档格式'} · 单文件最多 ${sizeLabel(config.max_upload_bytes)} · 最多 ${config.max_batch_files} 份`;
      root.querySelector('#knowledgeUploadRows').innerHTML = rows.map((row, index) => `
        <article class="kb-file-row ${row.state}"><div class="kb-file-heading"><strong title="${esc(row.file.name)}">${esc(row.file.name)}</strong><span>${esc(stageLabels[row.state] || row.state)}</span></div>
          <div class="kb-file-meta">${sizeLabel(row.file.size)}${row.chunks ? ` · ${row.chunks} 个片段` : ''}${row.completedChunks ? ` · 已向量化 ${row.completedChunks} 个片段` : ''}</div>
          ${['uploading','queued','reading','splitting','embedding','indexing','submitting'].includes(row.state) ? `<progress max="100" value="${Number(row.percent || 0)}" aria-label="${esc(row.file.name)}处理进度"></progress>` : ''}
          ${row.error ? `<p class="kb-error">${esc(row.error)}</p>` : ''}
          <div class="kb-row-actions">${row.state === 'failed' && row.taskId ? `<button type="button" class="button button-quiet button-small" data-retry="${index}">重试处理</button>` : ''}
          ${row.state === 'completed' && row.documentId ? `<button type="button" class="button button-quiet button-small" data-preview="${index}">查看片段</button>` : ''}
          ${!uploading && !row.taskId ? `<button type="button" class="button button-quiet button-small" data-remove="${index}">移除</button>` : ''}</div></article>`).join('');
      const pending = rows.some(row => row.state === 'ready' || (row.state === 'failed' && !row.taskId && !row.validationError));
      save.disabled = uploading || !pending;
      save.textContent = uploading ? '正在上传…' : rows.some(row => row.taskId) ? pending ? '上传剩余文件' : '已提交后台处理' : '上传并入库';
      picker.disabled = uploading;
      root.closest('.drawer').dataset.busy = String(uploading);
      root.closest('.drawer').querySelector('.drawer-footer .button-quiet').textContent = '关闭';
    }
    function select(files) {
      if (uploading) return;
      errorBox.textContent = '';
      for (const file of files) {
        if (rows.length >= config.max_batch_files) { errorBox.textContent = `一次最多选择 ${config.max_batch_files} 份文档`; break; }
        if (rows.some(row => row.file.name === file.name && row.file.size === file.size && row.file.lastModified === file.lastModified)) continue;
        const extension = '.' + file.name.split('.').pop().toLowerCase();
        const error = !file.size ? '文件为空' : file.size > config.max_upload_bytes ? `超过 ${sizeLabel(config.max_upload_bytes)} 大小限制` : config.extensions.length && !config.extensions.includes(extension) ? '不支持此格式，请使用列表中的文档格式' : '';
        rows.push({ file, state: error ? 'failed' : 'ready', error, validationError: !!error });
      }
      picker.value = '';
      render();
    }
    picker.onchange = () => select(Array.from(picker.files));
    for (const event of ['dragenter', 'dragover']) drop.addEventListener(event, e => { e.preventDefault(); drop.classList.add('is-dragging'); });
    for (const event of ['dragleave', 'drop']) drop.addEventListener(event, e => { e.preventDefault(); drop.classList.remove('is-dragging'); });
    drop.addEventListener('drop', e => select(Array.from(e.dataTransfer.files)));
    root.addEventListener('click', async event => {
      const button = event.target.closest('button');
      if (!button || uploading) return;
      if (button.dataset.remove !== undefined) { rows.splice(Number(button.dataset.remove), 1); render(); }
      if (button.dataset.preview !== undefined) { const row = rows[Number(button.dataset.preview)]; openPreview(id, row.documentId, ui); }
      if (button.dataset.retry !== undefined) {
        const row = rows[Number(button.dataset.retry)];
        button.disabled = true;
        try {
          await request(ui, `${pathFor(id)}/uploads/${encodeURIComponent(row.taskId)}/retry`, { method: 'POST', body: '{}' });
          row.state = 'queued'; row.percent = 0; row.error = ''; render(); schedulePoll();
        } catch (error) { errorBox.textContent = error.message; button.disabled = false; }
      }
    });
    async function submitFiles() {
      if (uploading) return;
      const pending = rows.filter(row => row.state === 'ready' || (row.state === 'failed' && !row.taskId && !row.validationError));
      if (!pending.length) { errorBox.textContent = '请先选择有效的文档'; return; }
      uploading = true; errorBox.textContent = ''; render();
      for (const row of pending) {
        row.state = 'uploading'; row.error = ''; row.percent = 0; render();
        try {
          const result = await transfer(id, row.file, ui, percent => { row.percent = percent; render(); });
          if (result.task_id) { row.taskId = result.task_id; row.state = 'queued'; row.percent = 0; }
          else if (result.status === 'done') { Object.assign(row, { state: 'completed', documentId: result.document_id, chunks: result.chunks }); }
          else if (result.status === 'processing') { row.state = 'submitted'; }
          else throw new Error('上传响应缺少任务信息，请确认服务已更新');
        } catch (error) { row.state = 'failed'; row.error = error.message; }
        render();
      }
      uploading = false; render(); schedulePoll();
    }
    function schedulePoll() {
      if (!root.isConnected || polling) return;
      clearTimeout(timer); timer = setTimeout(poll, 800);
    }
    async function poll() {
      if (!root.isConnected) return;
      polling = true;
      try {
        const result = await request(ui, `${pathFor(id)}/documents/status`);
        if (!root.isConnected) return;
        for (const job of result.uploads || []) {
          const row = rows.find(row => row.taskId === job.task_id);
          if (row) Object.assign(row, { state: stateFor(job), percent: job.percent, chunks: job.chunks,
            completedChunks: job.completed_chunks, error: job.error || '', documentId: job.document_id });
        }
        errorBox.textContent = ''; render();
        if (rows.some(row => row.state === 'completed')) void ui.loadPage();
      } catch (error) { if (root.isConnected) errorBox.textContent = `进度查询失败：${error.message}；将自动重试，也可稍后打开“文档状态”。`; }
      finally { polling = false; }
      if (rows.some(row => row.taskId && !['completed','failed','cancelled','submitted'].includes(row.state))) schedulePoll();
    }
    render();
    request(ui, `${pathFor(id)}/upload-config`).then(value => {
      if (!root.isConnected) return;
      config = value; picker.accept = value.extensions.join(','); render();
    }).catch(error => { if (root.isConnected) errorBox.textContent = `上传配置加载失败：${error.message}`; });
  }

  function openStatus(id, ui) {
    ui.modal('文档与处理记录', '<div id="knowledgeStatus" class="kb-documents"><p>正在读取文档状态…</p></div>', null, true);
    const root = document.getElementById('knowledgeStatus');
    let timer, refreshing = false;
    async function refresh() {
      if (!root.isConnected || refreshing) return;
      refreshing = true;
      try {
        const result = await request(ui, `${pathFor(id)}/documents/status`);
        if (!root.isConnected) return;
        const documents = result.documents || [], jobs = result.uploads || [];
        const pending = jobs.filter(job => job.status !== 'completed' || !documents.some(doc => doc.id === job.document_id));
        root.innerHTML = `<div class="kb-status-heading"><div><h3>文档与处理记录</h3><p>${documents.length} 份文档 · ${result.backend === 'local' ? `${Number(result.chunk_count || 0)} 个片段 · 本地 Milvus` : 'RAGFlow'}</p></div><button type="button" class="button button-quiet button-small" data-refresh>刷新状态</button></div>
          <div class="kb-error" id="knowledgeStatusError" role="alert"></div>
          ${pending.length ? `<h4>处理任务</h4><div class="kb-file-list">${pending.map(job => `<article class="kb-file-row ${job.status}"><div class="kb-file-heading"><strong>${ui.esc(job.source)}</strong><span>${ui.esc(stageLabels[stateFor(job)] || job.status)}</span></div>
            <div class="kb-file-meta">${sizeLabel(job.upload_bytes)}${job.chunks ? ` · ${job.chunks} 个片段` : ''}</div>
            ${['queued','running'].includes(job.status) ? `<progress max="100" value="${Number(job.percent || 0)}" aria-label="处理进度"></progress>` : ''}
            ${job.error ? `<p class="kb-error">${ui.esc(job.error)}</p>` : ''}
            ${['failed','cancelled'].includes(job.status) ? `<button type="button" class="button button-quiet button-small" data-retry="${ui.esc(job.task_id)}">重试处理</button>` : ''}</article>`).join('')}</div>` : ''}
          <h4>${result.backend === 'local' ? '已入库文档' : '远端文档'}</h4><div class="kb-file-list">${documents.map(doc => `<article class="kb-file-row completed"><div class="kb-file-heading"><strong>${ui.esc(doc.source || doc.name || doc.id)}</strong><span>${result.backend === 'local' ? '可检索' : ui.esc(doc.run || '未知状态')}</span></div>
            <div class="kb-file-meta">${Number(doc.chunks || doc.chunk_count || 0)} 个片段 · ${Number(doc.token_count || 0)} ${result.backend === 'local' ? '估算 Token' : 'Token'}${doc.revision ? ` · 第 ${Number(doc.revision)} 版` : ''}</div>
            ${doc.progress_msg ? `<p>${ui.esc(doc.progress_msg)}</p>` : ''}
            ${result.backend === 'local' ? `<button type="button" class="button button-quiet button-small" data-preview="${ui.esc(doc.id)}">查看片段</button>` : ''}</article>`).join('') || '<div class="kb-empty">还没有可检索的文档，请先上传并等待处理完成。</div>'}</div>`;
        const remoteActive = result.backend === 'ragflow' && documents.some(doc => ['UNSTART','RUNNING','SCHEDULE','0','1','5'].includes(String(doc.run)));
        if (jobs.some(job => ['queued','running'].includes(job.status)) || remoteActive) timer = setTimeout(refresh, 1500);
        else void ui.loadPage();
      } catch (error) {
        if (root.isConnected) {
          root.innerHTML = `<p class="kb-error" role="alert">状态查询失败：${ui.esc(error.message)}</p><button type="button" class="button button-quiet" data-refresh>重新加载</button>`;
        }
      } finally { refreshing = false; }
    }
    root.addEventListener('click', async event => {
      const button = event.target.closest('button');
      if (!button) return;
      if (button.hasAttribute('data-refresh')) { clearTimeout(timer); await refresh(); }
      if (button.dataset.preview) openPreview(id, button.dataset.preview, ui);
      if (button.dataset.retry) {
        button.disabled = true;
        try { await request(ui, `${pathFor(id)}/uploads/${encodeURIComponent(button.dataset.retry)}/retry`, { method: 'POST', body: '{}' }); await refresh(); }
        catch (error) { root.querySelector('#knowledgeStatusError').textContent = error.message; button.disabled = false; }
      }
    });
    void refresh();
  }

  function openPreview(id, documentId, ui) {
    ui.modal('文档片段', '<div id="knowledgePreview" class="kb-documents"><p>正在读取片段…</p></div>', null, true);
    const root = document.getElementById('knowledgePreview');
    let offset = 0;
    async function read() {
      try {
        const result = await request(ui, `${pathFor(id)}/documents/${encodeURIComponent(documentId)}/chunks?offset=${offset}&limit=20`);
        if (!root.isConnected) return;
        root.innerHTML = `<h3>${ui.esc(result.source)}</h3><p>共 ${result.total} 个片段 · 显示 ${result.total ? offset + 1 : 0}–${Math.min(offset + 20, result.total)}</p>
          ${result.data.map(chunk => `<details class="kb-chunk" open><summary>片段 ${chunk.position + 1}</summary><pre>${ui.esc(chunk.content)}</pre></details>`).join('')}
          <div class="kb-pagination"><button type="button" class="button button-quiet" data-back ${offset === 0 ? 'disabled' : ''}>上一页</button><button type="button" class="button button-quiet" data-next ${offset + 20 >= result.total ? 'disabled' : ''}>下一页</button></div>`;
      } catch (error) { if (root.isConnected) root.innerHTML = `<p class="kb-error">${ui.esc(error.message)}</p>`; }
    }
    root.addEventListener('click', event => {
      const button = event.target.closest('button');
      if (!button) return;
      if (button.hasAttribute('data-back')) offset = Math.max(0, offset - 20);
      else if (button.hasAttribute('data-next')) offset += 20;
      else return;
      void read();
    });
    void read();
  }
  window.CodezznKnowledge = { openUpload, openStatus };
})();
