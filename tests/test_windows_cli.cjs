'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { Store } = require('../cli/lib/config');
const { Transport, serverOrigin } = require('../cli/lib/transport');
const { Client } = require('../cli/lib/client');
const { Output, redact, safeInteraction } = require('../cli/lib/output');
const { parse } = require('../cli/lib/args');
const { login, openBrowser } = require('../cli/lib/auth');
const { engineeringCommand } = require('../cli/lib/main');
const capture = () => ({ text: '', write(value) { this.text += value; } });
async function fixture(t, options = {}) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'codezzn-cli-test-'));
  const store = new Store(directory);
  const state = { submissions: [], answers: [], deletes: 0, gets: 0, thread: { id: 'thr_test', name: 'Test', agent_id: 'agt_test', messages: [] }, message: null, interactions: [], events: [] };
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost'); let body = '';
    for await (const chunk of req) body += chunk;
    let data = {}; try { data = JSON.parse(body || '{}'); } catch {}
    const reply = (value, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(value)); };
    if (url.pathname === '/api/auth/cli/status') return reply({ user: { id: 'usr_test', name: 'Tester' }, expires_at: Math.floor(Date.now() / 1000) + 600 });
    if (url.pathname === '/api/resources/agents') return reply({ data: [{ id: 'agt_test', name: 'Tester', enabled: true }] });
    if (url.pathname === '/api/threads' && req.method === 'POST') return reply(state.thread);
    if (url.pathname === '/api/threads/thr_test') return reply(state.thread);
    if (url.pathname.endsWith('/queue') && req.method === 'POST') {
      state.submissions.push(data);
      state.message = { id: 'cqm_test', thread_id: 'thr_test', submission_id: data.submission_id, status: 'consumed', run_status: options.pending ? 'waiting_for_approval' : options.running ? 'running' : options.failed ? 'failed' : 'completed', turn_id: 'turn_test' };
      if (!options.pending && !options.running) state.thread.messages = [{ id: 'msg_test', role: 'assistant', turn_id: 'turn_test', content: 'Hello from server', meta: { secret: 'never dump meta' } }];
      if (options.loseSubmit && state.submissions.length === 1) return req.socket.destroy();
      return reply({ accepted: true, message: state.message });
    }
    if (url.pathname.endsWith('/queue')) return reply({ data: state.message ? [state.message] : [] });
    if (url.pathname.endsWith('/queue/cqm_test')) {
      if (req.method === 'DELETE') { state.deletes++; state.message.run_status = 'cancelled'; return reply({ message: state.message }); }
      state.gets++;
      if (options.breakPoll && state.gets === 1) return req.socket.destroy();
      if (options.finishAfter && state.gets >= options.finishAfter) { state.message.run_status = 'completed'; state.thread.messages = [{ role: 'assistant', turn_id: 'turn_test', content: 'Hello from server' }]; }
      return reply({ message: state.message });
    }
    if (url.pathname.endsWith('/events')) return reply({ data: state.events.filter(e => e.sequence > Number(url.searchParams.get('since'))) });
    if (url.pathname.endsWith('/interactions')) return reply({ data: state.interactions });
    if (url.pathname.endsWith('/interactions/int_test/answer')) {
      state.answers.push(data);
      if (options.loseUnacceptedAnswer && state.answers.length === 1) return req.socket.destroy();
      Object.assign(state.interactions[0], { status: 'answered', submission_id: data.submission_id, response: { decision: data.decision } });
      if (options.loseAnswer) return req.socket.destroy();
      return reply({ accepted: true, interaction: state.interactions[0] });
    }
    reply({ detail: 'Missing mock route' }, 404);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  t.after(async () => { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await fs.rm(directory, { recursive: true, force: true }); });
  const scope = { origin, user: 'usr_test', cwd: process.cwd() };
  const stdout = capture(), stderr = capture(), output = new Output(options.format || 'json', stdout, stderr);
  const client = new Client(new Transport(origin, 'czz_cli_' + 'a'.repeat(43)), store, scope, output, { pollInterval: 1, wait: async () => {}, noninteractive: options.interactive !== true, ask: options.ask || (async () => '') });
  if (options.pending) state.interactions = [{ id: 'int_test', kind: 'tool_approval', status: 'pending', question: 'Run command?', queue_message_id: 'cqm_test', turn_id: 'turn_test', payload: { tool_name: 'shell', arguments: { command: 'Get-ChildItem D:\\project', api_key: 'super-secret' } } }];
  return { directory, origin, store, scope, state, client, stdout, stderr, output };
}
function childCLI(args, env) {
  const child = spawn(process.execPath, [path.resolve(__dirname, '../cli/bin/codezzn.js'), ...args], { env: { ...process.env, ...env }, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
  child.stdin.end(); let stdout = '', stderr = '';
  child.stdout.on('data', chunk => { stdout += chunk; }); child.stderr.on('data', chunk => { stderr += chunk; });
  return new Promise((resolve, reject) => { child.once('error', reject); child.once('close', code => resolve({ code, stdout, stderr })); });
}
test('supported flags, positional prompts, explicit rejection, and server TLS policy', () => {
  assert.deepEqual(parse(['-p', '-n', 'Session', '--resume=thr_123', '--output-format=json', 'hello']).prompt, 'hello');
  assert.equal(parse(['-r']).resume, true);
  assert.throws(() => parse(['--dangerously-skip-permissions']), /Unsupported/);
  assert.throws(() => parse(['--output-format', 'bad']), /Invalid/);
  assert.throws(() => serverOrigin('http://192.168.1.3'), /HTTPS/);
  assert.equal(serverOrigin('http://192.168.1.3', true), 'http://192.168.1.3');
  assert.equal(serverOrigin('http://[::1]:8080'), 'http://[::1]:8080');
  assert.throws(() => serverOrigin('https://user:pass@example.com'), /origin/);
});
test('redirects never send bearer credentials to another server', async t => {
  let leaked = false;
  const other = http.createServer((req, res) => { leaked = !!req.headers.authorization; res.end('{}'); });
  await new Promise(resolve => other.listen(0, '127.0.0.1', resolve));
  const source = http.createServer((req, res) => { res.writeHead(307, { Location: `http://127.0.0.1:${other.address().port}/capture` }); res.end(); });
  await new Promise(resolve => source.listen(0, '127.0.0.1', resolve));
  t.after(() => { other.closeAllConnections(); source.closeAllConnections(); other.close(); source.close(); });
  const api = new Transport(`http://127.0.0.1:${source.address().port}`, 'private_token');
  await assert.rejects(api.request('/redirect'), /redirect refused/);
  await assert.rejects(api.request(`http://127.0.0.1:${other.address().port}/capture`), /Cross-origin/);
  assert.equal(leaked, false);
  assert.throws(() => openBrowser('https://evil.invalid/auth', api.origin), /cross-origin/);
});
test('real Windows DPAPI store roundtrip, origin isolation, logout, and session scope', async t => {
  const f = await fixture(t);
  await f.store.saveCredential(f.origin, { access_token: 'czz_cli_' + 's'.repeat(43), user: { id: 'usr_test' } });
  assert.equal((await f.store.credential(f.origin)).user.id, 'usr_test');
  assert.equal(await f.store.credential('https://different.example'), undefined);
  const raw = await fs.readFile(path.join(f.directory, 'credentials.json'), 'utf8');
  if (process.platform === 'win32') { assert.equal(raw.includes('ssssssss'), false); assert.equal(JSON.parse(raw).scheme, 'dpapi-current-user'); }
  else assert.equal((await fs.stat(path.join(f.directory, 'credentials.json'))).mode & 0o777, 0o600);
  await f.store.saveSession(f.scope, f.state.thread);
  assert.equal((await f.store.sessions({ ...f.scope, user: 'other' })).length, 0);
  assert.equal((await f.store.sessions({ ...f.scope, cwd: 'D:/other' })).length, 0);
  await f.store.forgetCredential(f.origin); assert.equal(await f.store.credential(f.origin), undefined);
});
test('device login matches actual backend numeric expiry; no bearer on polling', async t => {
  const f = await fixture(t), calls = [];
  const api = new Transport(f.origin, 'must-not-send', { fetch: async (url, request) => {
    calls.push(request);
    const result = url.pathname.endsWith('/device') ? { device_code: 'd'.repeat(43), user_code: 'ABCDE-FGHIJ', verification_uri_complete: f.origin + '/cli/authorize?user_code=ABCDE-FGHIJ', expires_in: 600, interval: 3 } : { access_token: 'czz_cli_' + 't'.repeat(43), expires_at: Math.floor(Date.now() / 1000) + 600, user: { id: 'usr_test', name: 'Tester' } };
    return new Response(JSON.stringify(result), { status: 200 });
  } });
  await login(api, f.store, f.output, { noBrowser: true, wait: async () => {} });
  assert.equal(calls.every(c => c.headers.Authorization === undefined), true);
  assert.equal((await f.store.credential(f.origin)).user.id, 'usr_test');
  assert.equal(f.stdout.text.includes('tttttttttt'), false);
});
test('a committed submission with a lost response is recovered without resubmission', async t => {
  const f = await fixture(t, { loseSubmit: true }); await f.client.open();
  const result = await f.client.send('hello');
  assert.equal(result.status, 'completed'); assert.equal(f.state.submissions.length, 1);
  assert.ok(f.state.submissions[0].submission_id);
  assert.equal((await f.store.sessions(f.scope))[0].pending, null);
});
test('poll reconnect keeps same submission and skips previously seen events', async t => {
  const f = await fixture(t, { running: true, breakPoll: true, finishAfter: 3, format: 'stream-json' });
  f.state.events = [{ sequence: 1, data: { type: 'assistant_delta', content: 'one two three four five six seven eight nine ' } }, { sequence: 2, data: { type: 'tool_started', name: 'read_file', arguments: { api_key: 'no' } } }, { sequence: 3, data: { type: 'reasoning_delta', content: 'hidden thought' } }];
  await f.client.open(); await f.client.send('hello');
  const rows = f.stdout.text.trim().split('\n').map(JSON.parse);
  assert.equal(rows.filter(r => r.type === 'tool_started').length, 1);
  assert.equal(rows.at(-1).type, 'result'); assert.equal(f.state.submissions.length, 1);
  assert.equal(f.stdout.text.includes('hidden thought'), false); assert.equal(f.stdout.text.includes('api_key'), false);
});
test('incremental assistant output redacts credentials split across chunks and terminal controls', () => {
  const stdout = capture(), stderr = capture(), output = new Output('stream-json', stdout, stderr);
  output.event({ type: 'assistant_delta', content: 'Normal response words arrive in real time now ' });
  assert.ok(stdout.text.includes('assistant_delta'));
  output.event({ type: 'assistant_delta', content: '正在实时输出中文内容。' });
  assert.ok(stdout.text.includes('中文内容'));
  output.event({ type: 'assistant_delta', content: ' czz_cli_' });
  output.event({ type: 'assistant_delta', content: 's'.repeat(43) + ' api_key = super-secret more safe ordinary words complete ' });
  output.result({ status: 'completed', content: 'done' });
  assert.equal(stdout.text.includes('ssssssss'), false); assert.equal(stdout.text.includes('super-secret'), false);
  assert.equal(redact('\x1b[2Jreplace\r\x08\x1b]52;c;secret\x07'), 'replace');
  const safe = safeInteraction({ kind: 'tool_approval', payload: { tool_name: 'shell', arguments: { command: 'Remove-Item D:\\project\\x.txt', api_key: 'secret', nested: { password: 'hidden' } } } });
  assert.ok(safe.arguments.command.includes('Remove-Item')); assert.equal(safe.arguments.api_key, '[REDACTED]'); assert.equal(safe.arguments.nested.password, '[REDACTED]');
});
test('Chinese streaming retains incomplete credential labels across text and JSON chunks', () => {
  const cases = [
    ['中文 api_key = ', 'super-secret second third fourth fifth sixth seventh '],
    ['中文 Bearer ', 'opaque-credential second third fourth fifth sixth seventh '],
    ['中文 Authorization: Bearer ', 'opaque-credential second third fourth fifth sixth seventh '],
    ['中文 api_key ', '= super-secret second third fourth fifth sixth seventh '],
    ['中文 "api_key": "', 'super-secret" second third fourth fifth sixth seventh '],
    ['中文 api_key = \n', 'super-secret second third fourth fifth sixth seventh '],
    ['中文 api_', 'key = ', 'super-secret second third fourth fifth sixth seventh '],
  ];
  for (const format of ['text', 'stream-json']) for (const chunks of cases) {
    const stdout = capture(), output = new Output(format, stdout, capture());
    for (const content of chunks) output.event({ type: 'assistant_delta', content });
    assert.ok(stdout.text.includes('中文'), `Chinese content should stream for ${format}`);
    output.result({ status: 'completed', content: 'done' });
    assert.equal(stdout.text.includes('super-secret'), false, `${format}: ${chunks.join('|')}`);
    assert.equal(stdout.text.includes('opaque-credential'), false, `${format}: ${chunks.join('|')}`);
    assert.ok(stdout.text.includes('[REDACTED]'));
  }
});
test('print mode exits requires_action and never autoapproves', async t => {
  const f = await fixture(t, { pending: true }); await f.client.open();
  const result = await f.client.send('run');
  assert.equal(result.status, 'requires_action'); assert.equal(f.state.answers.length, 0);
  assert.ok(f.stdout.text.includes('Get-ChildItem')); assert.equal(f.stdout.text.includes('super-secret'), false);
});
test('interactive default deny shows actual target and recovers accepted lost answer', async t => {
  const f = await fixture(t, { pending: true, interactive: true, loseAnswer: true }); await f.client.open();
  await f.client.interactions(f.state.interactions);
  assert.equal(f.state.answers[0].decision, 'denied');
  assert.ok(f.stderr.text.includes('D:\\\\project')); assert.equal(f.stderr.text.includes('super-secret'), false);
  assert.deepEqual((await f.store.sessions(f.scope))[0].answers, {});
});
test('uncertain answer persists its original ID; resume replays only that exact authorized answer', async t => {
  const f = await fixture(t, { pending: true, interactive: true, loseUnacceptedAnswer: true, ask: async () => 'yes' }); await f.client.open();
  await assert.rejects(f.client.interactions(f.state.interactions), /acceptance unknown/);
  const saved = (await f.store.sessions(f.scope))[0];
  assert.equal(saved.answers['int_test:'].body.decision, 'approved');
  assert.equal(f.state.answers.length, 1);
  const original = f.state.answers[0];
  f.client.noninteractive = true;
  await f.client.open({ resume: 'thr_test' });
  assert.equal(f.client.recoveredResult.status, 'requires_action'); assert.equal(f.state.answers.length, 1);
  f.client.noninteractive = false;
  await f.client.open({ resume: 'thr_test' });
  assert.equal(f.state.answers.length, 2); assert.deepEqual(f.state.answers[1], original);
  assert.deepEqual((await f.store.sessions(f.scope))[0].answers, {});
});
test('cancel uses durable queue deletion and terminal result', async t => {
  const f = await fixture(t, { running: true }); await f.client.open();
  const payload = { content: 'run', agent_id: 'agt_test', attachment_ids: [], submission_id: 'cancel-test-id' };
  const message = await f.client.submitDurable(payload); f.client.activeMessage = message;
  await f.client.cancel(); const result = await f.client.runMessage(message);
  assert.equal(result.status, 'cancelled'); assert.ok(f.state.deletes >= 1);
});
test('real bin returns 2 on approval, including --continue recovery, 1 on failure, 130 on cancellation', async t => {
  for (const mode of ['pending', 'failed', 'cancelled']) {
    const f = await fixture(t, { pending: mode === 'pending', failed: mode === 'failed' });
    await f.store.saveCredential(f.origin, { access_token: 'czz_cli_' + 'q'.repeat(43), user: { id: 'usr_test' } });
    if (mode === 'cancelled') {
      f.state.message = { id: 'cqm_test', submission_id: 'prior-test-id', status: 'consumed', run_status: 'cancelled', turn_id: 'turn_test' };
      await f.store.saveSession(f.scope, f.state.thread, { content: 'old', agent_id: 'agt_test', attachment_ids: [], submission_id: 'prior-test-id' });
    }
    const args = ['--server', f.origin, '-p', '--output-format', 'json', ...(mode === 'cancelled' ? ['-c'] : ['hello'])];
    const result = await childCLI(args, { CODEZZN_CONFIG_DIR: f.directory });
    assert.equal(result.code, mode === 'pending' ? 2 : mode === 'failed' ? 1 : 130, result.stderr);
    const rows = result.stdout.trim().split('\n').map(JSON.parse); assert.equal(rows.at(-1).status, mode === 'pending' ? 'requires_action' : mode);
    if (mode === 'pending') {
      const resumed = await childCLI(['--server', f.origin, '-p', '--output-format', 'json', '-c'], { CODEZZN_CONFIG_DIR: f.directory });
      assert.equal(resumed.code, 2, resumed.stderr); assert.equal(f.state.submissions.length, 1); assert.equal(f.state.answers.length, 0);
    }
  }
});
test('real bin keeps JSON stdout parseable on an early authentication failure', async t => {
  const f = await fixture(t);
  const result = await childCLI(['--server', f.origin, '-p', '--output-format', 'json', 'hello'], { CODEZZN_CONFIG_DIR: f.directory });
  assert.equal(result.code, 1); assert.equal(JSON.parse(result.stdout).status, 'failed');
});

test('engineering slash commands use read-only inspection and never silently approve', async () => {
  const requests = [], sent = [], output = capture();
  const client = { route: suffix => '/api/threads/t' + suffix, send: async prompt => sent.push(prompt) };
  const checkpoint = 'chk_' + 'a'.repeat(16);
  const api = { request: async (route, options) => {
    requests.push({ route, options });
    return options ? { checkpoint_id: checkpoint, changes: [], expected_hashes: { 'x.py': null } } : { engineering: { plan: { status: 'proposed' } }, context: { budget: 123 }, checkpoints: [{ id: checkpoint }] };
  } };
  const diagnostics = { diagnostic: text => output.write(text) };
  assert.equal(await engineeringCommand('context', '', client, api, diagnostics), true);
  assert.ok(output.text.includes('123'));
  await engineeringCommand('plan', '', client, api, diagnostics);
  assert.ok(output.text.includes('proposed'));
  assert.equal(sent.length, 0);
  await engineeringCommand('diff', checkpoint, client, api, diagnostics);
  assert.equal(requests.at(-1).options.body.name, 'task_diff');
  await engineeringCommand('rewind', checkpoint, client, api, diagnostics);
  assert.ok(sent.at(-1).includes('task_rewind'));
  assert.ok(sent.at(-1).includes('明确工具审批'));
  assert.ok(sent.at(-1).includes('expected_hashes'));
  await engineeringCommand('review', '', client, api, diagnostics);
  assert.ok(sent.at(-1).includes('engineering_review'));
  await assert.rejects(engineeringCommand('rewind', '', client, api, diagnostics), /Usage/);
  await assert.rejects(engineeringCommand('diff', '../../secret', client, api, diagnostics), /Invalid/);
  assert.equal(await engineeringCommand('unknown', '', client, api, diagnostics), false);
});
