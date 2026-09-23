(() => {
  'use strict';
  const mode = document.body.dataset.authMode === 'register' ? 'register' : 'login';
  const providerView = document.getElementById('providerView');
  const emailStep = document.getElementById('emailStep');
  const form = document.getElementById('authForm');
  const emailEntry = document.getElementById('emailEntry');
  const emailInput = document.getElementById('email');
  const selectedEmail = document.getElementById('selectedEmail');
  const submitButton = document.getElementById('submitButton');
  const feedback = document.getElementById('authFeedback');
  const githubButton = document.getElementById('githubButton');
  const switchLink = document.getElementById('switchLink');
  const sessionBox = document.getElementById('currentSession');
  const params = new URLSearchParams(location.search);
  let githubConfigured = true;
  let selectedProvider = 'email';

  function safeNext(value) { return value && value.startsWith('/') && !value.startsWith('//') ? value : '/workbench.html'; }
  const next = safeNext(params.get('next'));
  githubButton.href = `/api/auth/github/start?next=${encodeURIComponent(next)}`;
  switchLink.href = `${mode === 'login' ? '/register' : '/login'}?next=${encodeURIComponent(next)}`;

  function setFeedback(message, success = false) {
    feedback.textContent = message || '';
    feedback.classList.toggle('is-success', success);
  }
  function show(view) {
    providerView.hidden = view !== 'providers'; emailStep.hidden = view !== 'email'; form.hidden = view !== 'credentials'; setFeedback('');
    if (view === 'email') requestAnimationFrame(() => emailEntry.focus());
    if (view === 'credentials') requestAnimationFrame(() => form.elements.password.focus());
  }
  function setPending(pending) {
    submitButton.disabled = pending; submitButton.classList.toggle('is-loading', pending); submitButton.setAttribute('aria-busy', String(pending));
    form.querySelectorAll('input, button').forEach(element => { if (element !== selectedEmail) element.disabled = pending; });
  }
  function invalidate(input, message) { input.setAttribute('aria-invalid', 'true'); input.focus(); setFeedback(message); }
  async function request(path, options = {}) {
    const response = await fetch(path, { credentials: 'same-origin', ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.message || `请求失败 (${response.status})`);
    return data;
  }
  async function inspectSession() {
    try {
      const result = await request('/api/auth/me', { method: 'GET', headers: {} });
      githubConfigured = result.github_configured !== false;
      if (!githubConfigured) githubButton.title = 'GitHub 登录尚未配置';
      if (!result.authenticated || !result.user) return;
      const displayName = result.user.name || result.user.email || '当前用户';
      sessionBox.hidden = false; sessionBox.replaceChildren();
      const copy = document.createElement('p'); copy.textContent = `你已以 ${displayName} 登录。`;
      const link = document.createElement('a'); link.className = 'continue-button'; link.href = next; link.textContent = 'Continue to Workbench →';
      sessionBox.append(copy, link);
    } catch (_) { /* Keep authentication usable if the session probe fails. */ }
  }

  const callbackErrors = { github_denied: '你已取消 GitHub 授权，请重试或使用邮箱登录。', github_invalid: 'GitHub 登录状态已失效，请重新尝试。', github_400: 'GitHub 登录请求无效，请重新尝试。', github_503: 'GitHub 登录尚未配置，请联系管理员或使用邮箱登录。' };
  const callbackError = params.get('error');
  if (callbackError) setFeedback(callbackErrors[callbackError] || 'GitHub 登录未完成，请重试或使用邮箱登录。');
  githubButton.addEventListener('click', event => { if (githubConfigured) return; event.preventDefault(); setFeedback('GitHub 登录尚未配置，请联系管理员或使用邮箱登录。'); });
  document.querySelector('[data-provider="google"]').addEventListener('click', () => setFeedback('Google 登录尚未配置。请使用 GitHub 或邮箱继续。'));
  document.querySelector('[data-provider="email"]').addEventListener('click', () => { selectedProvider = 'email'; show('email'); });
  document.querySelector('[data-provider="sso"]').addEventListener('click', () => { selectedProvider = 'sso'; show('email'); });

  function continueFromEmail() {
    const email = emailEntry.value.trim();
    if (!email || !emailEntry.checkValidity()) return invalidate(emailEntry, '请输入有效的邮箱地址。');
    if (selectedProvider === 'sso') { setFeedback('企业 SSO 尚未配置。请使用 GitHub 或邮箱继续。'); return; }
    emailInput.value = email; selectedEmail.textContent = email; show('credentials');
  }
  document.getElementById('emailNext').addEventListener('click', continueFromEmail);
  emailEntry.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); continueFromEmail(); } });
  document.getElementById('emailCancel').addEventListener('click', () => show('providers'));
  document.getElementById('formCancel').addEventListener('click', () => show('providers'));
  selectedEmail.addEventListener('click', () => show('email'));
  document.querySelectorAll('input').forEach(input => input.addEventListener('input', () => { input.removeAttribute('aria-invalid'); if (feedback.textContent) setFeedback(''); }));

  form.addEventListener('submit', async event => {
    event.preventDefault(); setFeedback(''); if (!form.reportValidity()) return;
    const values = Object.fromEntries(new FormData(form).entries());
    if (mode === 'register') {
      if (String(values.name || '').trim().length < 2) return invalidate(form.elements.name, '姓名至少需要 2 个字符。');
      if (String(values.password || '').length < 10) return invalidate(form.elements.password, '密码至少需要 10 个字符。');
      if (values.password !== values.confirmPassword) return invalidate(form.elements.confirmPassword, '两次输入的密码不一致。');
      delete values.confirmPassword; values.name = String(values.name).trim();
    }
    values.email = String(values.email || '').trim(); setPending(true);
    try {
      await request(`/api/auth/${mode}`, { method: 'POST', body: JSON.stringify(values) });
      setFeedback(mode === 'login' ? '登录成功，正在进入工作台…' : '账号已创建，正在进入工作台…', true); location.assign(next);
    } catch (error) { setFeedback(error.message || '暂时无法完成请求，请稍后重试。'); setPending(false); }
  });
  inspectSession();
})();
