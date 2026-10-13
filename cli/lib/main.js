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
        } else if (command === 'skills' || command === 'mcp') {
          const data = (await api.request(`/api/resources/${command === 'mcp' ? 'mcp_servers' : 'skills'}`)).data || [];
          output.diagnostic(data.map(item => `${item.id} · ${item.name || item.title || ''} · enabled=${item.enabled !== false}`).join('\n') || '(none configured)');
        } else throw new Error(`Unknown command /${command}; use /help`);
      } catch (error) { output.diagnostic(error.message); }
    }
    return questionInterrupted ? 130 : 0;
  } finally { rl?.close(); if (!injected.noSignals) process.off('SIGINT', onSignal); }
}
if (require.main === module) main().then(code => { process.exitCode = code; }).catch(error => { process.stderr.write(`${redact(error.message)}\n`); process.exitCode = 1; });
module.exports = { main, readStdin };
