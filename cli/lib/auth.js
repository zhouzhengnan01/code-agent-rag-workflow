'use strict';
const { spawn } = require('node:child_process');
const { delay } = require('./client');
function openBrowser(value, origin, platform = process.platform) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.origin !== origin || url.username || url.password) throw new Error('Unsafe or cross-origin login URL refused');
  const path = require('node:path');
  if (platform === 'win32' && (!process.env.SystemRoot || !path.win32.isAbsolute(process.env.SystemRoot))) throw new Error('Trusted Windows browser launcher unavailable; open the URL manually.');
  const command = platform === 'win32' ? path.win32.join(process.env.SystemRoot, 'explorer.exe') : platform === 'darwin' ? '/usr/bin/open' : '/usr/bin/xdg-open';
  return new Promise((resolve, reject) => {
    const child = spawn(command, [url.href], { cwd: path.dirname(command), shell: false, windowsHide: true, detached: true, stdio: 'ignore' });
    child.once('error', () => reject(new Error('Could not open the browser; open the displayed URL manually.')));
    child.once('spawn', () => { child.unref(); resolve(); });
  });
}
async function login(api, store, output, options = {}) {
  const device = await api.request('/api/auth/cli/device', { method: 'POST', auth: false, body: { name: options.name || `Codezzn CLI (${process.platform})` } });
  const verification = new URL(device.verification_uri_complete);
  if (!['http:', 'https:'].includes(verification.protocol) || verification.origin !== api.origin || verification.username || verification.password) throw new Error('Unsafe or cross-origin login URL refused');
  if (typeof device.device_code !== 'string' || !device.device_code || !Number.isFinite(device.expires_in) || device.expires_in <= 0 || device.expires_in > 3600) throw new Error('Invalid device login response');
  output.diagnostic(`Open ${verification.href}\nVerification code: ${device.user_code}\nApprove this CLI in your browser.`);
  if (!options.noBrowser) await (options.openBrowser || openBrowser)(verification.href, api.origin).catch(error => output.diagnostic(error.message));
  const deadline = Date.now() + device.expires_in * 1000;
  let interval = Math.max(1, Math.min(Number(device.interval) || 3, 30));
  while (Date.now() < deadline) {
    await (options.wait || delay)(interval * 1000);
    const response = await api.request('/api/auth/cli/token', { method: 'POST', auth: false, body: { device_code: device.device_code }, statuses: [202, 403, 410, 429], withStatus: true });
    if (response.status === 202) continue;
    if (response.status === 429) { interval = Math.min(30, interval + 5); continue; }
    if (response.status === 403) throw new Error('Browser authorization denied');
    if (response.status === 410) throw new Error('Login expired; run auth login again');
    const data = response.data;
    if (typeof data.access_token !== 'string' || !/^[\x21-\x7e]+$/.test(data.access_token) || !data.user?.id || !Number.isFinite(data.expires_at) || data.expires_at <= Date.now() / 1000) throw new Error('Invalid login token response');
    await store.saveCredential(api.origin, { access_token: data.access_token, expires_at: data.expires_at, user: { id: data.user.id, name: data.user.name, email: data.user.email } });
    const config = await store.read('config.json'); await store.write('config.json', { ...config, server: api.origin });
    output.result({ status: 'authenticated', user: { id: data.user.id, name: data.user.name, email: data.user.email }, server: api.origin });
    if (output.format === 'text') output.diagnostic(`Authenticated as ${data.user.name || data.user.email || data.user.id}`);
    return data.user;
  }
  throw new Error('Login expired; run auth login again');
}
async function logout(api, store, output) {
  let remoteError;
  try { if (api.token) await api.request('/api/auth/cli/logout', { method: 'POST', body: {} }); }
  catch (error) { remoteError = error; }
  finally { await store.forgetCredential(api.origin); }
  output.result({ status: 'logged_out', server: api.origin, remote_revoked: !remoteError });
  if (remoteError) output.diagnostic('Local credentials cleared. Server revocation could not be confirmed; revoke the device in the browser.');
  else if (output.format === 'text') output.diagnostic('Logged out; local credentials cleared.');
}
module.exports = { login, logout, openBrowser };
