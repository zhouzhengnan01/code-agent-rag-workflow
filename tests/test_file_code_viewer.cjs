'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const api = require('../web/file-code-viewer.js');

function textContent(html) {
  return html.replace(/<\/?span(?: class="[\w -]*")?>/g, '')
    .replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&gt;/g, '>').replace(/&lt;/g, '<').replace(/&amp;/g, '&');
}
test('Python has distinct keyword, function, docstring, comment, number tokens', () => {
  const source = '\n"""A docstring\nwith blank lines.\n\n"""\n\n# comment\ndef quick_sort(values):\n    return [1, 2.5, "hello"]\n\n';
  const html = api.highlight(source, 'algorithms/quicksort.py');
  for (const type of ['keyword', 'function', 'string', 'comment', 'number']) assert.match(html, new RegExp(`class="token [^"\\n]*${type}[^"\\n]*"`));
  assert.match(html, /class="token triple-quoted-string string"/);
  assert.equal(textContent(html), source);
});
test('JavaScript and JSON tokenize locally', () => {
  for (const [filename, source] of [['main.js', 'function add(a) { return a + 42; }'], ['settings.json', '{"value": 42, "enabled": true}']]) {
    const html = api.highlight(source, filename);
    assert.match(html, /class="token number"/);
    assert.equal(textContent(html), source);
  }
});
test('all included grammars can highlight their respective files', () => {
  const fixtures = {
    'main.ts': 'const a: number = 1;', 'main.jsx': 'const el = <div onClick={run}>hello</div>;',
    'main.tsx': 'const el: JSX.Element = <div>{value}</div>;', 'index.html': '<script>alert("x")</script>',
    'style.css': '.hello { color: red; }', 'config.yaml': 'name: test\ncount: 1',
    'run.sh': 'echo "hello"\nexit 0', 'run.ps1': 'Write-Host "hello"', 'query.sql': 'SELECT * FROM test;',
    'README.md': '# Hello\n\n`code`', 'config.toml': '[table]\ncount = 1',
    'main.c': 'int main() { return 0; }', 'main.cpp': 'int main() { return 0; }',
    'Main.java': 'class Main { public static void main(String[] args) {} }',
    'main.go': 'package main\nfunc main() {}', 'main.rs': 'fn main() { let x = 1; }'
  };
  for (const [filename, source] of Object.entries(fixtures)) {
    const html = api.highlight(source, filename);
    assert.match(html, /class="token /, filename);
    assert.equal(textContent(html), source, filename);
  }
});
test('HTML and script source is escaped, never emitted as active markup', () => {
  const source = '<script>globalThis.pwned = 1</script><img src=x onerror="alert(1)"> &amp;';
  for (const filename of ['index.html', 'unknown.zzz', 'README.md', 'example.py']) {
    const html = api.highlight(source, filename);
    assert.doesNotMatch(html, /<(?:script|img)\b/i);
    assert.equal(textContent(html), source, filename);
  }
  assert.equal(globalThis.pwned, undefined);
});
test('plaintext fallback preserves blank lines, tabs, CRLF, NBSP, unicode and trailing newline', () => {
  const source = '\n\r\n\t<>&\'"\u00a0😀中文\n\n';
  assert.equal(textContent(api.highlight(source, 'file.unknown')), source);
  assert.doesNotMatch(api.highlight(source, 'file.unknown'), /<span/);
  assert.equal(textContent(api.highlight(source, 'file.py')), source);
});
test('200 KiB guard counts UTF-8 bytes and avoids highlighting oversized source', () => {
  for (const source of ['#' + 'a'.repeat(200 * 1024), '#中文'.repeat(35000)]) {
    const html = api.highlight(source, 'large.py');
    assert.doesNotMatch(html, /<span/);
    assert.equal(textContent(html), source);
  }
});
test('extension detection handles Windows paths and case without interpolating input', () => {
  assert.equal(api.languageFor('C:\\work\\MAIN.PY'), 'python');
  assert.equal(api.languageFor('types.d.ts'), 'typescript');
  assert.equal(api.languageFor('example.tsx'), 'tsx');
  assert.equal(api.languageFor('.bashrc'), 'bash');
  assert.equal(api.languageFor('unknown'), 'plain');
  assert.equal(api.languageFor(null), 'plain');
  assert.equal(api.highlight(null, 'main.py'), '');
});
test('icons use exact local Python image and trusted static SVGs', () => {
  assert.match(api.icon('main.py'), /src="\/assets\/vendor\/prism\/python.png"/);
  assert.match(api.icon('main.py'), /width="14" height="14"/);
  assert.match(api.icon('folder-open'), /stroke="#f97316"/);
  assert.match(api.icon('folder'), /width="16" height="16"/);
  assert.match(api.icon('README.md'), /code-file-icon--markdown/);
  assert.match(api.icon('requirements.txt'), /code-file-icon--text/);
  assert.equal(api.icon('file-text'), api.icon('text'));
  for (const name of ['chevron', 'download', 'close']) assert.match(api.icon(name), /<svg /);
  assert.equal(api.icon('<img onerror=alert(1)>.xxx'), api.icon('file'));
  assert.ok(fs.statSync(path.join(__dirname, '../web/vendor/prism/python.png')).size > 0);
});
test('browser scripts work offline without CommonJS or automatic DOM highlighting', () => {
  const context = vm.createContext({});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/vendor/prism/prism.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/file-code-viewer.js'), 'utf8'), context);
  assert.equal(typeof context.CodezznFileCode.highlight, 'function');
  assert.match(context.CodezznFileCode.highlight('def run():\n    return 1', 'run.py'), /token keyword/);
});
