export async function api<T = any>(
  path: string,
  body?: unknown,
  method = body === undefined ? 'GET' : 'POST',
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 30000);
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const key = localStorage.getItem('codezznKey');
  if (key) headers['X-Codezzn-Key'] = key;
  try {
    const response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      credentials: 'same-origin',
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) throw new Error('登录已过期，请返回工作台重新登录。当前变更可先导出。');
      throw new Error(typeof data.detail === 'string' ? data.detail : `请求失败（${response.status}）`);
    }
    return data as T;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw new Error('请求超时，请检查服务器连接');
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}
