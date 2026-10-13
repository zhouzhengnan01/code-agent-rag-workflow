(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  let userCode = (params.get('user_code') || '').trim().toUpperCase();
  let csrfToken = '';
  const feedback = byId('feedback');
  const approve = byId('approve');
  const deny = byId('deny');

  function describe(result, status) {
    if (typeof result.detail === 'string') return result.detail;
    if (status === 410) return '授权码已过期，请在终端重新运行登录命令。';
    if (status === 409) return '此授权请求已处理，请返回终端查看结果。';
    if (status === 404) return '没有找到此授权码，请核对终端中的授权码。';
    if (status === 429) return '请求过于频繁，请稍后再试。';
    return '暂时无法处理授权，请稍后重试。';
  }

  async function load() {
    byId('login').hidden = true;
    byId('consent').hidden = true;
    if (!userCode) {
      byId('codeForm').hidden = false;
      feedback.textContent = '在这里输入终端显示的授权码。';
      return;
    }
    byId('codeDisplay').textContent = userCode;
    byId('codeDisplay').hidden = false;
    feedback.textContent = '正在检查授权请求…';
    try {
      const response = await fetch(`/api/auth/cli/device-info?user_code=${encodeURIComponent(userCode)}`, {
        credentials: 'same-origin', cache: 'no-store'
      });
      const result = await response.json();
      if (response.status === 401) {
        const next = `/cli/authorize?user_code=${encodeURIComponent(userCode)}`;
        byId('loginLink').href = `/login?next=${encodeURIComponent(next)}`;
        byId('login').hidden = false;
        feedback.textContent = '需要浏览器登录后确认。';
        return;
      }
      if (!response.ok) {
        feedback.textContent = describe(result, response.status);
        return;
      }
      csrfToken = result.csrf_token;
      byId('deviceName').textContent = result.name;
      byId('account').textContent = `${result.user.name} (${result.user.email})`;
      byId('consent').hidden = false;
      feedback.textContent = '请确认授权码与终端一致。';
    } catch {
      feedback.textContent = '无法连接服务器，请刷新页面重试。';
    }
  }

  async function decide(decision) {
    approve.disabled = deny.disabled = true;
    feedback.textContent = '正在提交…';
    try {
      const response = await fetch('/api/auth/cli/approve', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-CLI-CSRF': csrfToken },
        body: JSON.stringify({ user_code: userCode, decision })
      });
      const result = await response.json();
      if (!response.ok) {
        feedback.textContent = describe(result, response.status);
        return;
      }
      byId('consent').hidden = true;
      feedback.textContent = decision === 'approved' ? '授权成功。请返回终端继续；此页面可以关闭。' : '已拒绝授权。此页面可以关闭。';
    } catch {
      feedback.textContent = '提交失败，请刷新页面检查授权状态后重试。';
    } finally {
      approve.disabled = deny.disabled = false;
    }
  }

  byId('codeForm').addEventListener('submit', event => {
    event.preventDefault();
    userCode = byId('codeInput').value.trim().toUpperCase();
    history.replaceState(null, '', `/cli/authorize?user_code=${encodeURIComponent(userCode)}`);
    byId('codeForm').hidden = true;
    load();
  });
  approve.addEventListener('click', () => decide('approved'));
  deny.addEventListener('click', () => decide('denied'));
  load();
})();
