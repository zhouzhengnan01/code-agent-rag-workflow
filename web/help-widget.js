(async () => {
  'use strict';

  // Login/marketing pages never mount the assistant, even with a session cookie.
  if (['/', '/login', '/register'].includes(location.pathname.replace(/\/$/, '') || '/')) return;
  const authenticated = async () => {
    try {
      const response = await fetch('/api/auth/me', { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) return false;
      const result = await response.json();
      return result.authenticated === true && Boolean(result.user?.id);
    } catch (_) { return false; }
  };
  if (!await authenticated()) return;

  const root = document.createElement('div');
  root.className = 'cz-help-widget';
  root.innerHTML = `
    <section class="cz-help-panel" aria-label="Codezzn 帮助助手" hidden>
      <header class="cz-help-head">
        <span class="cz-help-brand"><img src="/assets/codezzn-mark.svg?v=1" alt="Codezzn"></span>
        <button class="cz-help-close" type="button" aria-label="关闭帮助面板">×</button>
        <h2>Welcome 👋<br>How can we help?</h2>
      </header>
      <div class="cz-help-body">
        <div class="cz-help-faq">
          <label class="cz-help-label" for="czHelpSearch">搜索 Codezzn 帮助</label>
          <input class="cz-help-search" id="czHelpSearch" type="search" autocomplete="off" placeholder="输入问题，查找帮助...">
          <div class="cz-help-results" aria-live="polite"></div>
          <div class="cz-help-answer" hidden></div>
        </div>
        <div class="cz-help-divider"></div>
        <button class="cz-help-chat-link" type="button">
          <img src="/assets/codezzn-mark.svg?v=1" alt="">
          <span><strong>Chat with Codezzn AI</strong><small class="cz-help-offline">登录后使用账号配置的模型回答产品问题</small></span>
          <span aria-hidden="true">›</span>
        </button>
        <section class="cz-help-chat" hidden>
          <div class="cz-help-messages" aria-live="polite"></div>
          <form class="cz-help-input-row">
            <input class="cz-help-input" type="text" maxlength="2000" placeholder="Ask Codezzn..." aria-label="向 Codezzn 帮助助手提问">
            <button class="cz-help-send" type="submit" aria-label="发送问题">↑</button>
          </form>
        </section>
      </div>
      <footer class="cz-help-footer">Powered by Codezzn</footer>
    </section>
    <button class="cz-help-toggle" type="button" aria-label="打开 Codezzn 帮助助手" aria-expanded="false">
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 18V5m0 0L6.5 10.5M12 5l5.5 5.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>`;
  document.body.append(root);
  window.addEventListener('pageshow', async () => { if (!await authenticated()) root.remove(); });

  const panel = root.querySelector('.cz-help-panel');
  const toggle = root.querySelector('.cz-help-toggle');
  const close = root.querySelector('.cz-help-close');
  const search = root.querySelector('.cz-help-search');
  const results = root.querySelector('.cz-help-results');
  const answer = root.querySelector('.cz-help-answer');
  const chatLink = root.querySelector('.cz-help-chat-link');
  const chat = root.querySelector('.cz-help-chat');
  const messages = root.querySelector('.cz-help-messages');
  const form = root.querySelector('.cz-help-input-row');
  const input = root.querySelector('.cz-help-input');
  const send = root.querySelector('.cz-help-send');
  let searchTimer;
  let faqCache = [];

  const setOpen = open => {
    panel.hidden = !open;
    toggle.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? '关闭 Codezzn 帮助助手' : '打开 Codezzn 帮助助手');
    if (open) { loadFaq(''); window.setTimeout(() => search.focus(), 0); }
  };
  const addMessage = (text, user = false) => {
    const node = document.createElement('div');
    node.className = `cz-help-message${user ? ' is-user' : ''}`;
    node.textContent = text;
    messages.append(node);
    messages.scrollTop = messages.scrollHeight;
  };
  const loadFaq = async query => {
    if (!query.trim()) { results.replaceChildren(); answer.hidden = true; return; }
    try {
      const response = await fetch(`/api/help/faq?q=${encodeURIComponent(query)}`, { credentials: 'same-origin' });
      const payload = await response.json();
      faqCache = Array.isArray(payload.data) ? payload.data : [];
      results.replaceChildren();
      if (!faqCache.length) {
        const empty = document.createElement('p'); empty.className = 'cz-help-offline';
        empty.textContent = '没有匹配的问题。可以直接向 Codezzn AI 提问。'; results.append(empty); return;
      }
      faqCache.forEach(item => {
        const button = document.createElement('button'); button.className = 'cz-help-result'; button.type = 'button'; button.textContent = item.question;
        button.addEventListener('click', () => { answer.textContent = item.answer; answer.hidden = false; });
        results.append(button);
      });
      answer.hidden = true;
    } catch (_) { results.textContent = '帮助内容暂时无法加载。'; }
  };

  toggle.addEventListener('click', () => setOpen(panel.hidden));
  close.addEventListener('click', () => setOpen(false));
  search.addEventListener('input', () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => loadFaq(search.value.trim()), 140);
  });
  chatLink.addEventListener('click', () => {
    chat.hidden = false; chatLink.hidden = true; panel.classList.add('is-chat-open'); input.focus();
    if (!messages.children.length) addMessage('你好！我可以根据 Codezzn 帮助内容解答产品使用问题。');
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question || send.disabled) return;
    addMessage(question, true); input.value = ''; send.disabled = true; send.textContent = '…';
    const placeholder = document.createElement('div'); placeholder.className = 'cz-help-message'; placeholder.textContent = '正在查找答案…'; messages.append(placeholder);
    messages.scrollTop = messages.scrollHeight;
    try {
      const response = await fetch('/api/help/ask', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      if (response.status === 401) { root.remove(); return; }
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      placeholder.textContent = payload.answer || '暂时没有找到答案。';
    } catch (error) { placeholder.textContent = error.message || '请求失败，请稍后重试。'; }
    finally { send.disabled = false; send.textContent = '↑'; if (root.isConnected) input.focus(); messages.scrollTop = messages.scrollHeight; }
  });
  loadFaq('');
})();
