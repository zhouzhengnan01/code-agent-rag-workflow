'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const { quotePS, origin, options, command } = require('../integrations/vscode/bridge');
test('bridge only accepts explicit origins and LAN HTTP opt-in', () => {
  assert.equal(origin('http://localhost:8080'), 'http://localhost:8080');
  assert.throws(() => origin('http://192.168.1.10'), /requires/);
  assert.equal(origin('http://192.168.1.10', true), 'http://192.168.1.10');
  assert.throws(() => origin('https://user:pass@example.com'), /origin/);
  assert.throws(() => origin('https://example.com/path'), /origin/);
});
test('bridge builds direct absolute Node invocation and literal PowerShell arguments', () => {
  const config = options({ server: 'https://codezzn.example', nodeExecutable: 'C:\\Program Files\\nodejs\\node.exe', cliScript: "C:\\Users\\O'Neil\\codezzn.js" }, { SystemRoot: 'C:\\Windows' }, () => true);
  const value = command(config, { attachment: "C:\\Temp\\x'; $(whoami); #.txt", review: true });
  assert.ok(value.startsWith("& 'C:\\Program Files\\nodejs\\node.exe'"));
  assert.ok(value.includes("O''Neil"));
  assert.ok(value.includes("'C:\\Temp\\x''; $(whoami); #.txt'"));
  assert.ok(!value.includes('codezzn.cmd'));
  assert.equal(quotePS('$env:SECRET; `calc`'), "'$env:SECRET; `calc`'");
  assert.throws(() => quotePS('bad\ncommand'), /Invalid/);
});
test('bridge rejects relative executable paths, missing runtimes and shell wrappers', () => {
  assert.throws(() => options({ nodeExecutable: 'node.exe' }, {}, () => true), /absolute/);
  assert.throws(() => options({ nodeExecutable: 'C:\\bad.cmd', cliScript: 'C:\\codezzn.js' }, {}, () => true), /Expected/);
  assert.throws(() => options({}, { APPDATA: 'C:\\Users\\Tester\\AppData\\Roaming' }, () => false), /Missing/);
});
test('real PowerShell preserves hostile-looking selected paths as Node arguments', { skip: process.platform !== 'win32' }, () => {
  const values = ["C:\\Temp\\x'; Write-Output INJECTED; #.txt", '$(Get-Date); $env:SECRET `whoami` %PATH%', '中文目录'];
  const script = '& ' + [process.execPath, '-e', 'process.stdout.write(JSON.stringify(process.argv.slice(1)))', '--', ...values].map(quotePS).join(' ');
  const shell = path.join(process.env.SystemRoot, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
  const result = spawnSync(shell, ['-NoProfile', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')], { encoding: 'utf8', windowsHide: true, timeout: 15000 });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), values);
});
