const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function workbench() {
  const calls = [];
  const source = fs.readFileSync(path.join(__dirname, '../web/workbench.js'), 'utf8');
  const context = vm.createContext({
    window: { addEventListener() {} }, document: { addEventListener() {} },
    CodezznKnowledge: {
      openUpload: (...args) => calls.push(args),
      openStatus: (...args) => calls.push(args),
    },
  });
  // Load actual event handlers without booting a network-backed application.
  vm.runInContext(source.slice(0, source.lastIndexOf('state.page = pages.some')), context);
  return { context, calls };
}

test('upload entry reads the actual workbench cache and opens the document UI', () => {
  const { context, calls } = workbench();
  vm.runInContext("state.cache.knowledge = [{id:'kb',name:'Local',backend:'local'}]; uploadDoc('kb');", context);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], 'kb');
  assert.equal(calls[0][1].name, 'Local');
  assert.equal(calls[0][1].backend, 'local');
  assert.equal(typeof calls[0][2].api, 'function');
});

test('missing cached knowledge cannot prevent the upload panel from opening', () => {
  const { context, calls } = workbench();
  vm.runInContext("uploadDoc('uncached'); showKnowledgeStatus('uncached');", context);
  assert.equal(calls.length, 2);
  assert.equal(calls[0][0], 'uncached');
  assert.equal(calls[1][0], 'uncached');
});
