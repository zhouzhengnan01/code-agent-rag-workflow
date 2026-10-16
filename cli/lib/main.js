'use strict';
const readline = require('node:readline/promises');
const path = require('node:path');
const { parse, HELP } = require('./args');
const { Store } = require('./config');
const { Transport, serverOrigin } = require('./transport');
const { Output, redact } = require('./output');
const { Client } = require('./client');
const { login, logout } = require('./auth');
async function readStdin(input) {
  let content = '';
  for await (const chunk of input) { content += chunk; if (content.length > 32000) throw new Error('Stdin prompt exceeds the 32000 character limit'); }
  return content;
}
async function engineeringCommand(command, value, client, api, output) {
  if (!['plan', 'diff', 'context', 'review', 'rewind'].includes(command)) return false;
  if (command === 'review') {
    await client.send(`请调用 engineering_review 独立审查当前项目的真实变更，输出有路径、行号、证据和严重程度的问题，并明确未覆盖和模型失败。不要修改文件或声称测试已运行。${value ? `审查范围：${value}` : ''}`);
  } else if (command === 'plan' && value) {
    await client.send(`请使用 plan_manage 为以下目标创建工程计划并提出必要的质量检查，等待我批准计划后再执行：${value}`);
  } else if (command === 'diff' || command === 'rewind') {
    if (!value && command === 'rewind') throw new Error('Usage: /rewind CHECKPOINT_ID. Use /diff to list checkpoints.');
    if (!value) {
      const current = await api.request(client.route('/coding/state'));
      output.diagnostic(JSON.stringify(current.checkpoints || [], null, 2));
    } else {
      if (!/^chk_[a-f0-9]{16}$/.test(value)) throw new Error('Invalid checkpoint ID; use /diff to list server checkpoints');
      const preview = await api.request(client.route('/coding/inspect'), { method: 'POST', body: { name: 'task_diff', args: { checkpoint_id: value } } });
      output.diagnostic(JSON.stringify(preview, null, 2));
      if (command === 'rewind') {
        const data = preview.result || preview;
        if (!data.expected_hashes || typeof data.expected_hashes !== 'object') throw new Error('Server did not return preview hashes; no rewind was requested');
        await client.send(`请回退任务快照。以下是服务器刚预览的完整参数，请调用 task_rewind，并等待我的明确工具审批；如果文件已变化则拒绝覆盖，不能强制回退。参数：${JSON.stringify({ checkpoint_id: value, expected_hashes: data.expected_hashes })}`);
      }
    }
  } else {
    const current = await api.request(client.route('/coding/state'));
    output.diagnostic(JSON.stringify(command === 'context' ? current.context || {} : current.engineering?.plan || { status: 'none' }, null, 2));
  }
  return true;
}
async function main(argv = process.argv.slice(2), injected = {}) {
  const options = parse(argv), stdout = injected.stdout || process.stdout, stderr = injected.stderr || process.stderr, stdin = injected.stdin || process.stdin;
  if (options.help) { stdout.write(HELP); return 0; }
  if (options.version) { stdout.write(`${require('../package.json').version}\n`); return 0; }
  const output = new Output(options.format, stdout, stderr), store = injected.store || new Store();
  const config = await store.read('config.json'), origin = serverOrigin(options.server || config.server || 'http://localhost:8080', options.insecure);
  let credential;
  if (options.auth !== 'login') {
    try { credential = await store.credential(origin); }
    catch (error) { if (options.auth !== 'logout') throw error; output.diagnostic(error.message); }
  }
  const api = injected.api || new Transport(origin, credential?.access_token);
  if (options.auth === 'login') { await login(api, store, output, options); return 0; }
  if (options.auth === 'logout') { await logout(api, store, output); return 0; }
  if (!credential?.access_token) {
    if (options.auth === 'status') { output.result({ status: 'unauthenticated', server: origin }); if (options.format === 'text') output.diagnostic(`Not authenticated for ${origin}`); return 1; }
    throw new Error(`Not authenticated for ${origin}. Run codezzn auth login --server ${origin}`);
  }
  let status;
  try { status = await api.request('/api/auth/cli/status'); }
  catch (error) { if (error.status === 401) throw new Error(`Session expired or revoked. Run codezzn auth login --server ${origin}`); throw error; }
  const user = status.user;
  if (!user?.id || user.id !== credential.user?.id) throw new Error('Authenticated user does not match the saved credential; run auth login');
  if (options.auth === 'status') {
    output.result({ status: 'authenticated', user: { id: user.id, name: user.name, email: user.email }, server: origin });
    if (options.format === 'text') output.diagnostic(`${user.name || user.email || user.id} · ${origin}`);
    return 0;
  }
  const interactive = !options.print && Boolean(stdin.isTTY);
  if (!interactive && !options.print) options.print = true;
  let rl, questionInterrupted = false;
  if (interactive) rl = readline.createInterface({ input: stdin, output: stderr, terminal: true });
  const ask = injected.ask || (async question => {
    if (!rl || questionInterrupted) return '';
    try { return await rl.question(question); } catch { return ''; }
  });
  const scope = { origin, user: user.id, cwd: path.resolve(injected.cwd || process.cwd()) };
  const client = new Client(api, store, scope, output, { noninteractive: !interactive, ask, ...(injected.clientOptions || {}) });
  let interrupts = 0;
  const onSignal = () => {
    if (++interrupts > 1) { rl?.close(); if (!injected.noExit) process.exit(130); return; }
    questionInterrupted = true;
    output.diagnostic('Cancelling the current server task; press Ctrl+C again to exit.');
    client.cancel().catch(error => output.diagnostic(`Cancellation not confirmed: ${error.message}`));
    if (rl) rl.close();
  };
  if (!injected.noSignals) process.on('SIGINT', onSignal);
  if (rl) rl.on('SIGINT', onSignal);
  try {
    await client.open(options);
    if (client.recoveredResult?.status === 'requires_action') return 2;
    if (!interactive && client.recoveredResult && !options.prompt && !options.attachments.length) return client.recoveredResult.status === 'completed' ? 0 : client.recoveredResult.status === 'cancelled' ? 130 : 1;
    if (!interactive) {
      const prompt = options.prompt || (options.attachments.length ? '' : await readStdin(stdin));
      if (!prompt.trim() && !options.attachments.length) {
        if (client.thread && (options.resume || options.continue)) return 0;
        throw new Error('Print mode requires a prompt or stdin input');
      }
      const result = await client.send(prompt, await client.attachments(options.attachments));
      return result.status === 'requires_action' ? 2 : result.status === 'completed' ? 0 : result.status === 'cancelled' ? 130 : 1;
    }
    output.diagnostic(`Codezzn · ${origin}\nSession ${client.thread.id} · local context ${scope.cwd}\nTools execute within the server / Docker project boundary. /help lists commands.`);
    let attached = await client.attachments(options.attachments);
    if (options.prompt) { await client.send(options.prompt, attached); attached = []; }
    while (!questionInterrupted) {
      const line = (await ask('codezzn> ')).trim();
      if (!line) { if (stdin.destroyed || rl?.closed) break; continue; }
      interrupts = 0;
      try {
        if (!line.startsWith('/')) { await client.send(line, attached); attached = []; continue; }
        const match = line.match(/^\/(\S+)(?:\s+([\s\S]*))?$/), command = match[1], value = match[2] || '';
        if (command === 'exit' || command === 'quit') break;
        if (command === 'help') output.diagnostic(HELP);
        else if (command === 'new') { await client.open({ name: value || 'CLI session' }); attached = []; output.diagnostic(`Session ${client.thread.id}`); }
        else if (command === 'resume') { await client.open({ resume: value || true }); attached = []; output.diagnostic(`Session ${client.thread.id}`); }
        else if (command === 'model') { await client.selectModel(value); await client.save(); }
        else if (command === 'agent') {
          if (!value) output.diagnostic((await client.agents()).map(a => `${a.id} · ${a.name}`).join('\n'));
          else { const agent = await client.resolveAgent(value); client.thread = await api.request(client.route(), { method: 'PATCH', body: { agent_id: agent.id } }); await client.save(); }
        } else if (command === 'project') {
          const projects = (await api.request('/api/projects')).data || [];
          if (!value) output.diagnostic(projects.map(p => `${p.id} · ${p.name}`).join('\n') || 'No server projects');
          else {
            const matches = projects.filter(p => p.id === value || p.name === value);
            if (matches.length !== 1) throw new Error('Project not found or ambiguous; select its ID');
            client.thread = await api.request(client.route(), { method: 'PATCH', body: { active_project_id: matches[0].id } });
            await client.save(); output.diagnostic(`Server project: ${matches[0].name}`);
          }
        } else if (command === 'status') {
          const thread = await api.request(client.route());
          output.diagnostic(JSON.stringify({ id: thread.id, name: thread.name, status: thread.status, agent_id: thread.agent_id, model: thread.model_override, project_id: thread.active_project_id }, null, 2));
        } else if (command === 'stop') { await client.cancel(); output.diagnostic('Stop requested'); }
        else if (command === 'files') {
          if (!value) output.diagnostic(`Pending attachment IDs: ${attached.join(', ') || '(none)'}. Use /files "C:\\path with spaces\\file.txt" to upload a file for the next prompt.`);
          else {
            const filename = value.replace(/^"(.*)"$/, '$1');
            if (attached.length >= 8) throw new Error('At most 8 attachments are allowed');
            attached.push(...await client.attachments([filename])); output.diagnostic('File uploaded; attached to the next prompt.');
          }
        } else if (command === 'skills') {
          const runtime = await api.request(`/api/chat/runtime?thread_id=${encodeURIComponent(client.thread.id)}`);
          output.diagnostic((runtime.skills || []).filter(s => s.user_invocable).map(s => `/${s.command} · ${s.id} · ${s.description || s.name}`).join('\n') || '(no available skills)');
        } else if (command === 'permissions') {
          if (value && !['default', 'acceptEdits', 'plan', 'inherit'].includes(value)) throw new Error('Use /permissions default|acceptEdits|plan|inherit');
          if (value) {
            const overrides = { ...(client.thread.capability_overrides || {}) };
            if (value === 'inherit') delete overrides.permission_mode; else overrides.permission_mode = value;
            client.thread = await api.request(client.route(), { method: 'PATCH', body: { capability_overrides: overrides } });
          }
          const runtime = await api.request(`/api/chat/runtime?thread_id=${encodeURIComponent(client.thread.id)}`);
          output.diagnostic(`Permission mode: ${runtime.permission_mode}. Sandbox and deny policies still apply.`);
        } else if (command === 'mcp') {
          const data = (await api.request('/api/resources/mcp_servers')).data || [];
          output.diagnostic(data.map(item => `${item.id} · ${item.name || ''}`).join('\n') || '(none configured)');
        } else if (await engineeringCommand(command, value, client, api, output)) { /* Existing server approvals apply. */ }
        else { await client.send(line, attached); attached = []; } // Server validates /skill-name and /skill name.
      } catch (error) { output.diagnostic(error.message); }
    }
    return questionInterrupted ? 130 : 0;
  } finally { rl?.close(); if (!injected.noSignals) process.off('SIGINT', onSignal); }
}
if (require.main === module) main().then(code => { process.exitCode = code; }).catch(error => { process.stderr.write(`${redact(error.message)}\n`); process.exitCode = 1; });
module.exports = { main, readStdin, engineeringCommand };
