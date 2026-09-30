/* Locally hosted Markdown rendering. Never trust model-generated HTML. */
function richText(value, artifacts = []) {
  if (!window.marked || !window.DOMPurify) return esc(value).replace(/\n/g, '<br>');
  const fragment = DOMPurify.sanitize(marked.parse(String(value ?? ''), { gfm: true, breaks: true }), {
    RETURN_DOM_FRAGMENT: true,
    ALLOWED_TAGS: ['p', 'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em', 'del', 's', 'blockquote', 'ul', 'ol', 'li', 'pre', 'code', 'a', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'input'],
    ALLOWED_ATTR: ['href', 'title', 'class', 'start', 'align', 'type', 'checked', 'disabled'],
    ALLOW_DATA_ATTR: false,
    ALLOW_ARIA_ATTR: false,
  });
  fragment.querySelectorAll('[class]').forEach(node => {
    const language = node.tagName === 'CODE' ? [...node.classList].find(name => /^language-[\w+-]+$/.test(name)) : null;
    node.removeAttribute('class');
    if (language) node.className = language;
  });
  fragment.querySelectorAll('input').forEach(input => {
    if (input.type !== 'checkbox') { input.remove(); return; }
    input.disabled = true;
  });
  fragment.querySelectorAll('a').forEach(link => {
    const href = link.getAttribute('href') || '';
    if (!/^(https?:|mailto:|\/|#)/i.test(href) || href.startsWith('//')) link.removeAttribute('href');
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
  });
  fragment.querySelectorAll('pre').forEach(pre => {
    const code = pre.querySelector('code');
    if (!code) return;
    const frame = document.createElement('section');
    frame.className = 'markdown-code-block';
    const toolbar = document.createElement('div');
    toolbar.className = 'markdown-code-toolbar';
    const language = document.createElement('span');
    language.textContent = [...code.classList].find(name => name.startsWith('language-'))?.slice(9) || '代码';
    const copy = document.createElement('button');
    copy.type = 'button';
    copy.className = 'markdown-code-copy';
    copy.dataset.copyCode = 'true';
    copy.setAttribute('aria-label', '复制代码');
    copy.textContent = '复制';
    toolbar.append(language, copy);
    pre.className = 'message-code';
    pre.replaceWith(frame);
    frame.append(toolbar, pre);
  });
  fragment.querySelectorAll('code').forEach(code => {
    if (code.closest('pre')) return;
    code.className = 'inline-code';
    const label = code.textContent;
    const matches = artifacts.filter(item => item.path === label || item.path?.split('/').at(-1) === label);
    const file = matches.find(item => item.path === label) || (matches.length === 1 ? matches[0] : null);
    if (!file) return;
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'file-reference-chip';
    chip.dataset.projectId = file.project_id;
    chip.dataset.artifactId = file.id;
    chip.dataset.openChatArtifact = 'true';
    chip.setAttribute('aria-label', `在 Files 中打开 ${file.path}`);
    chip.textContent = `▤ ${label}`;
    code.replaceWith(chip);
  });
  fragment.querySelectorAll('table').forEach(table => {
    const wrapper = document.createElement('div');
    wrapper.className = 'markdown-table-scroll';
    table.replaceWith(wrapper);
    wrapper.append(table);
  });
  const container = document.createElement('div');
  container.append(fragment);
  return container.innerHTML;
}

async function copyMessageCode(button) {
  if (button.disabled) return;
  const code = button.closest('.markdown-code-block')?.querySelector('pre code');
  if (!code) return;
  button.disabled = true;
  try {
    let copied = false;
    if (navigator.clipboard?.writeText) {
      try { await navigator.clipboard.writeText(code.textContent); copied = true; } catch (_) { /* HTTP/permissions fallback below. */ }
    }
    if (!copied) {
      const focused = document.activeElement;
      const selection = window.getSelection();
      const ranges = selection ? Array.from({ length: selection.rangeCount }, (_, i) => selection.getRangeAt(i).cloneRange()) : [];
      const buffer = document.createElement('textarea');
      buffer.value = code.textContent;
      buffer.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0';
      document.body.append(buffer);
      try { buffer.select(); copied = document.execCommand('copy'); }
      finally {
        buffer.remove();
        focused?.focus({ preventScroll: true });
        if (selection) { selection.removeAllRanges(); ranges.forEach(range => selection.addRange(range)); }
      }
      if (!copied) throw new Error('浏览器不允许复制，请手动选中代码复制');
    }
    button.textContent = '已复制';
    button.setAttribute('aria-label', '代码已复制');
  } catch (error) { toast(error.message || '复制失败', true); }
  finally {
    button.disabled = false;
    window.setTimeout(() => { button.textContent = '复制'; button.setAttribute('aria-label', '复制代码'); }, 1800);
  }
}

document.addEventListener('click', event => {
  const copy = event.target.closest('[data-copy-code]');
  if (copy) { copyMessageCode(copy); return; }
  const artifact = event.target.closest('[data-open-chat-artifact]');
  if (artifact) openChatArtifact(artifact);
});
