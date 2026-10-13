'use strict';
class HttpError extends Error {
  constructor(status, message) { super(`HTTP ${status}: ${message}`); this.status = status; }
}
function serverOrigin(value, insecure = false) {
  let url;
  try { url = new URL(value); } catch { throw new Error('Invalid server URL'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || !['', '/'].includes(url.pathname)) throw new Error('--server must be an HTTP(S) origin without credentials, path, query, or fragment');
  const host = url.hostname.toLowerCase();
  const loopback = host === 'localhost' || host === '[::1]' || /^127(?:\.\d{1,3}){3}$/.test(host);
  if (url.protocol === 'http:' && !loopback && !insecure) throw new Error('HTTPS is required for remote servers. Use --allow-insecure-http only if you explicitly accept this risk.');
  return url.origin;
}
class Transport {
  constructor(origin, token, options = {}) { this.origin = origin; this.token = token; this.fetch = options.fetch || globalThis.fetch; this.timeout = options.timeout || 30000; }
  async request(route, options = {}) {
    const url = new URL(route, this.origin);
    if (url.origin !== this.origin) throw new Error('Cross-origin request refused');
    const headers = { Accept: 'application/json' };
    if (this.token && options.auth !== false) headers.Authorization = `Bearer ${this.token}`;
    let body;
    if (options.form) body = options.form;
    else if (options.body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(options.body); }
    const response = await this.fetch(url, { method: options.method || 'GET', headers, body, redirect: 'manual', signal: AbortSignal.timeout(this.timeout) });
    if (response.status >= 300 && response.status < 400) throw new Error('Server redirect refused; bearer credentials were not forwarded');
    const raw = await response.text();
    let data; try { data = raw ? JSON.parse(raw) : {}; } catch { throw new Error(`Server returned non-JSON (HTTP ${response.status})`); }
    if (!response.ok && !options.statuses?.includes(response.status)) throw new HttpError(response.status, typeof data.detail === 'string' ? data.detail : 'Request failed');
    return options.withStatus ? { status: response.status, data } : data;
  }
}
module.exports = { Transport, serverOrigin, HttpError };
