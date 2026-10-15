const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function form(item = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../web/workbench.js'), 'utf8');
  const nodes = new Map([
    ['#editForm', {}], ['#editForm [name=enabled]', { checked: true }],
    ['#editForm [name=transport]', { value: item.transport || 'sandbox', addEventListener(name, callback) { this.change = callback; } }],
    ['#lspSandboxFields', {}], ['#lspHttpFields', {}], ['#lspStdioFields', {}],
  ]);
  const values = { name: 'Python', transport: item.transport || 'sandbox', sandbox_server_id: item.sandbox_server_id || 'python', endpoint: 'http://unused', command: 'untrusted', args: '["--stdio"]' };
  const writes = [], errors = [];
  let content = '', saveCallback;
  const context = vm.createContext({
    $: selector => nodes.get(selector),
    esc: value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;'),
    field: (label, name, value) => `${label}:${name}:${value}`,
    selectField: (label, name, options, full, help) => `${label}:${name}:${options}:${help}`,
    toggleField: () => '', formData: () => ({ ...values }),
    modal: (title, html, callback) => { content = html; saveCallback = callback; },
    save: (...args) => writes.push(args), toast: message => errors.push(message),
  });
  const start = source.indexOf('function lspForm(item) {');
  const end = source.indexOf('\nasync function agentTeamForm', start);
  vm.runInContext(source.slice(start, end), context);
  context.lspForm(item);
  return { nodes, values, writes, errors, get html() { return content; }, save() { saveCallback(); } };
}

test('new LSP resources default to tenant-isolated Docker mode and explain admin mapping', () => {
  const app = form();
  assert.match(app.html, /value="sandbox" selected/);
  assert.match(app.html, /CODEZZN_LSP_SERVERS_JSON/);
  assert.match(app.html, /sandbox_server_id/);
  assert.match(app.html, /本机 stdio（仅单用户）/);
});

test('sandbox save persists server alias, never persists an arbitrary execution command', () => {
  const app = form({ sandbox_server_id: 'private-pyright' });
  app.save();
  const saved = app.writes[0][2];
  assert.equal(saved.transport, 'sandbox');
  assert.equal(saved.sandbox_server_id, 'private-pyright');
  assert.equal(saved.command, undefined);
  assert.equal(saved.args, undefined);
  assert.equal(saved.endpoint, undefined);
});

test('transport changes show only the relevant configuration group', () => {
  const app = form();
  const selector = app.nodes.get('#editForm [name=transport]');
  selector.value = 'http'; selector.change();
  assert.equal(app.nodes.get('#lspSandboxFields').hidden, true);
  assert.equal(app.nodes.get('#lspHttpFields').hidden, false);
  assert.equal(app.nodes.get('#lspStdioFields').hidden, true);
});

test('existing stdio stays explicit and malformed argv cannot be saved', () => {
  const app = form({ id: 'old-lsp', transport: 'stdio' });
  assert.match(app.html, /value="stdio" selected/);
  app.values.args = '[1]'; app.save();
  assert.equal(app.writes.length, 0);
  assert.match(app.errors[0], /字符串数组/);
});
