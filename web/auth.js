(() => {
  'use strict';
  const mode = document.body.dataset.authMode === 'register' ? 'register' : 'login';
  const providerView = document.getElementById('providerView');
  const emailStep = document.getElementById('emailStep');
  const emailCodeForm = document.getElementById('emailCodeForm');
  const emailCode = document.getElementById('emailCode');
  const codeSelectedEmail = document.getElementById('codeSelectedEmail');
  const emailNext = document.getElementById('emailNext');
  const codeSubmit = document.getElementById('codeSubmit');
  const resendCode = document.getElementById('resendCode');
  const form = document.getElementById('authForm');
  const emailEntry = document.getElementById('emailEntry');
  const emailInput = document.getElementById('email');
  const selectedEmail = document.getElementById('selectedEmail');
  const submitButton = document.getElementById('submitButton');
  const feedback = document.getElementById('authFeedback');
  const githubButton = document.getElementById('githubButton');
  const googleButton = document.getElementById('googleButton');
  const switchLink = document.getElementById('switchLink');
  const sessionBox = document.getElementById('currentSession');
  const params = new URLSearchParams(location.search);
  let githubConfigured = true;
  let googleConfigured = true;
  let emailCodeConfigured = false;
  let selectedProvider = 'email';
  let codeEmail = '';
  let resendAt = 0;
  let resendTimer = null;

  function safeNext(value) { return value && value.startsWith('/') && !value.startsWith('//') ? value : '/workbench.html'; }
  const next = safeNext(params.get('next'));
  githubButton.href = `/api/auth/github/start?next=${encodeURIComponent(next)}`;
  googleButton.href = `/api/auth/google/start?next=${encodeURIComponent(next)}`;
  switchLink.href = `${mode === 'login' ? '/register' : '/login'}?next=${encodeURIComponent(next)}`;

  function setFeedback(message, success = false) {
    feedback.textContent = message || '';
    feedback.classList.toggle('is-success', success);
  }
  function show(view) {
    providerView.hidden = view !== 'providers'; emailStep.hidden = view !== 'email'; emailCodeForm.hidden = view !== 'code'; form.hidden = view !== 'credentials'; setFeedback('');
    if (view === 'email') requestAnimationFrame(() => emailEntry.focus());
    if (view === 'code') requestAnimationFrame(() => emailCode.focus());
    if (view === 'credentials') requestAnimationFrame(() => form.elements.password.focus());
  }
  function updateResend() {
    const seconds = Math.max(0, Math.ceil((resendAt - Date.now()) / 1000));
    resendCode.disabled = seconds > 0;
    resendCode.textContent = seconds ? `${seconds} 秒后可重新发送` : '重新发送验证码';
    if (!seconds && resendTimer) { clearInterval(resendTimer); resendTimer = null; }
  }
  function startResendCooldown(seconds) {
    resendAt = Date.now() + seconds * 1000;
    if (resendTimer) clearInterval(resendTimer);
    resendTimer = setInterval(updateResend, 1000);
    updateResend();
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
      googleConfigured = result.google_configured !== false;
      if (!googleConfigured) googleButton.title = 'Google 登录尚未配置';
      emailCodeConfigured = result.email_code_configured === true;
      emailNext.textContent = emailCodeConfigured ? (mode === 'register' ? '发送注册验证码' : '发送登录验证码') : '下一步';
      if (!result.authenticated || !result.user) return;
      const displayName = result.user.name || result.user.email || '当前用户';
      sessionBox.hidden = false; sessionBox.replaceChildren();
      const copy = document.createElement('p'); copy.textContent = `你已以 ${displayName} 登录。`;
      const link = document.createElement('a'); link.className = 'continue-button'; link.href = next; link.textContent = 'Continue to Workbench →';
      sessionBox.append(copy, link);
    } catch (_) { /* Keep authentication usable if the session probe fails. */ }
  }

  const callbackErrors = { github_denied: '你已取消 GitHub 授权，请重试或使用邮箱登录。', github_invalid: 'GitHub 登录状态已失效，请重新尝试。', github_400: 'GitHub 登录请求无效，请重新尝试。', github_409: '此邮箱已绑定其他 GitHub 账号，请使用原账号登录或联系管理员。', github_502: '暂时无法连接 GitHub，请稍后重新登录。', github_503: 'GitHub 登录尚未配置，请联系管理员或使用邮箱登录。', github_504: 'GitHub 响应超时，请稍后重新登录。', google_denied: '你已取消 Google 授权，请重试或使用其他方式登录。', google_invalid: 'Google 登录状态已失效，请重新尝试。', google_400: 'Google 身份校验未通过，请重新尝试。', google_409: '该邮箱已有账号。为保护数据，不会自动合并；请使用原登录方式。', google_502: '暂时无法连接 Google，请稍后重新登录。', google_503: 'Google 登录配置不可用，请联系管理员。', google_504: 'Google 响应超时，请稍后重新登录。' };
  const callbackError = params.get('error');
  if (callbackError) setFeedback(callbackErrors[callbackError] || '第三方登录未完成，请重试或使用邮箱登录。');
  else if (params.get('logged_out') === '1') setFeedback('已退出 Codezzn。再次使用第三方账号时请在账号选择器中确认账号；共用设备还应退出第三方网站本身。');
  githubButton.addEventListener('click', event => { if (githubConfigured) return; event.preventDefault(); setFeedback('GitHub 登录尚未配置，请联系管理员或使用邮箱登录。'); });
  googleButton.addEventListener('click', event => { if (googleConfigured) return; event.preventDefault(); setFeedback('Google 登录尚未配置，请联系管理员或使用其他方式登录。'); });
  document.querySelector('[data-provider="email"]').addEventListener('click', () => { selectedProvider = 'email'; show('email'); });
  document.querySelector('[data-provider="sso"]').addEventListener('click', () => { selectedProvider = 'sso'; show('email'); });

  async function sendCode(email) {
    emailNext.disabled = true; resendCode.disabled = true;
    try {
      const result = await request('/api/auth/email/code', { method: 'POST', body: JSON.stringify({ email }) });
      codeEmail = email; codeSelectedEmail.textContent = email; emailCode.value = '';
      show('code'); startResendCooldown(result.resend_after || 60);
      setFeedback('验证码已发送，请检查收件箱和垃圾邮件文件夹。', true);
    } catch (error) { setFeedback(error.message || '邮件发送失败，请稍后重试。'); }
    finally { emailNext.disabled = false; updateResend(); }
  }
  async function continueFromEmail() {
    const email = emailEntry.value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return invalidate(emailEntry, '请输入有效的邮箱地址。');
    if (selectedProvider === 'sso') { setFeedback('企业 SSO 尚未配置。请使用 GitHub 或邮箱继续。'); return; }
    emailInput.value = email; selectedEmail.textContent = email;
    if (emailCodeConfigured) await sendCode(email);
    else { show('credentials'); setFeedback('邮件验证码尚未配置，当前使用密码方式。'); }
  }
  emailNext.addEventListener('click', continueFromEmail);
  const emailUsePassword = document.getElementById('emailUsePassword');
  if (emailUsePassword) emailUsePassword.addEventListener('click', () => {
    const email = emailEntry.value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return invalidate(emailEntry, '请输入有效的邮箱地址。');
    emailInput.value = email; selectedEmail.textContent = email; show('credentials');
  });
  emailEntry.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); continueFromEmail(); } });
  document.getElementById('emailCancel').addEventListener('click', () => show('providers'));
  document.getElementById('codeCancel').addEventListener('click', () => show('providers'));
  codeSelectedEmail.addEventListener('click', () => show('email'));
  document.getElementById('usePassword').addEventListener('click', () => { emailInput.value = codeEmail; selectedEmail.textContent = codeEmail; show('credentials'); });
  resendCode.addEventListener('click', () => { if (Date.now() >= resendAt && codeEmail) sendCode(codeEmail); });
  emailCodeForm.addEventListener('submit', async event => {
    event.preventDefault(); setFeedback('');
    if (!emailCodeForm.reportValidity()) return;
    codeSubmit.disabled = true; codeSubmit.setAttribute('aria-busy', 'true');
    try {
      await request('/api/auth/email/verify', { method: 'POST', body: JSON.stringify({ email: codeEmail, code: emailCode.value.trim() }) });
      setFeedback('验证成功，正在进入工作台…', true); location.assign(next);
    } catch (error) { setFeedback(error.message || '验证码验证失败，请重试。'); codeSubmit.disabled = false; codeSubmit.setAttribute('aria-busy', 'false'); }
  });
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
