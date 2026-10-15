'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
class Element {
  constructor() { this.children = []; this.handlers = {}; this.nodes = {}; this.innerHTML = ''; this.value = ''; }
  addEventListener(name, handler) { this.handlers[name] = handler; }
  setAttribute(name, value) { this[name] = value; }
  querySelector(selector) { if (selector === '.coding-launch') return this.children.find(x => x.className === 'coding-launch') || null; return this.nodes[selector] ||= new Element(); }
  querySelectorAll() { return []; }
  append(...items) { this.children.push(...items); }
  prepend(item) { this.children.unshift(item); }
  replaceChildren(...items) { this.children = items; }
  insertAdjacentHTML(_, value) { this.innerHTML += value; }
  focus() { this.focused = true; }
  remove() { this.removed = true; }
}
function fixture(responder) {
  const header = new Element(), content = new Element(), body = new Element(), input = new Element(), prompts = [], calls = [];
  const nodes = { '.conversation-header-actions': header, '#content': content, '#chatInput': input };
  const state = { thread: 'thr_test', page: 'chat' };
  const context = { module: { exports: {} }, state, document: { body, activeElement: new Element(), createElement: () => new Element(), querySelector: selector => nodes[selector] }, window: { confirm: () => true }, MutationObserver: class { observe() {} }, fillChatPrompt: prompt => prompts.push(prompt), api: async (url, options) => { calls.push({ url, options }); return responder ? responder(url, options) : { workspace: 'server/worktree', engineering: { plan: { status: 'proposed', steps: [{ content: '<script>bad()</script>', status: 'pending' }] } }, checkpoints: [], context: { budget: 123 } }; } };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/coding-panel.js'), 'utf8'), context);
  return { context, state, header, body, input, prompts, calls, exports: context.module.exports, dialog: () => body.children.at(-1) };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
test('engineering button mounts once and readonly state escapes model/project text', async () => {
  const f = fixture();
  assert.equal(f.header.children.length, 1);
  f.exports.mount(); assert.equal(f.header.children.length, 1);
  f.exports.open(); await tick();
  const dialog = f.dialog();
  const html = dialog.querySelector('.coding-panel-body').innerHTML;
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('<script>'));
  assert.equal(f.calls[0].url, '/api/threads/thr_test/coding/state');
  assert.equal(f.calls[0].options, undefined);
  assert.equal(f.prompts.length, 0);
});
test('rewind preview only reads server diff, then fills a visible approval draft', async () => {
  const checkpoint = 'chk_' + 'a'.repeat(16);
  const f = fixture((url, options) => options ? { changes: [{ path: 'x.py', diff: '-bad\n+safe' }], expected_hashes: { 'x.py': '123' } } : { engineering: {}, checkpoints: [{ id: checkpoint }] });
  f.exports.open(); await tick();
  await f.exports.showDiff(checkpoint);
  assert.equal(JSON.parse(f.calls.at(-1).options.body).name, 'task_diff');
  const footer = f.dialog().querySelector('footer');
  footer.children.at(-1).handlers.click();
  assert.equal(f.prompts.length, 1);
  assert.ok(f.prompts[0].includes('expected_hashes'));
  assert.ok(f.prompts[0].includes('必须等待我的工具审批'));
  assert.equal(f.calls.filter(c => c.options).length, 1); // Never a POST that mutates files.
});
test('switching conversation prevents action on a stale engineering panel', async () => {
  const f = fixture(); f.exports.open(); await tick();
  f.state.thread = 'another_thread';
  f.exports.propose('mutate files');
  assert.equal(f.prompts.length, 0);
  assert.ok(f.dialog().querySelector('.coding-panel-body').innerHTML.includes('当前对话已切换'));
  f.exports.mount(); assert.ok(f.dialog().removed);
});
test('read failure remains visible and does not submit an automatic conversation', async () => {
  const f = fixture(() => { throw new Error('HTTP 401 <unsafe>'); });
  f.exports.open(); await tick();
  assert.ok(f.dialog().querySelector('.coding-panel-body').innerHTML.includes('&lt;unsafe&gt;'));
  assert.equal(f.prompts.length, 0);
});
