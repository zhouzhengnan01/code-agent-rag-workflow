'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawn } = require('node:child_process');
function dpapi(operation, input) {
  return new Promise((resolve, reject) => {
    const systemRoot = process.env.SystemRoot;
    if (!systemRoot || !path.win32.isAbsolute(systemRoot)) { reject(new Error('Trusted Windows PowerShell location unavailable; credentials were not stored.')); return; }
    const executable = path.win32.join(systemRoot, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
    if (!require('node:fs').existsSync(executable)) { reject(new Error('Windows PowerShell unavailable; credentials were not stored.')); return; }
    const child = spawn(executable, ['-NoLogo', '-NoProfile', '-NonInteractive', '-File', path.join(__dirname, 'dpapi.ps1'), '-Operation', operation], { cwd: path.dirname(executable), windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
    let result = '';
    child.stdout.setEncoding('utf8'); child.stdout.on('data', value => { result += value; });
    child.stderr.resume(); child.stdin.on('error', () => {});
    child.once('error', () => reject(new Error('Windows DPAPI unavailable. Credentials were not stored.')));
    child.once('close', code => code === 0 ? resolve(result) : reject(new Error('Windows DPAPI failed. Credentials were not stored or decrypted.')));
    child.stdin.end(input);
  });
}
class Store {
  constructor(directory = process.env.CODEZZN_CONFIG_DIR || path.join(os.homedir(), '.codezzn'), platform = process.platform) { this.directory = directory; this.platform = platform; }
  async read(name, fallback = {}) {
    try { return JSON.parse(await fs.readFile(path.join(this.directory, name), 'utf8')); }
    catch (error) { if (error.code === 'ENOENT') return fallback; throw new Error(`Cannot read Codezzn ${name}; repair this file before continuing.`); }
  }
  async write(name, value) {
    await fs.mkdir(this.directory, { recursive: true, mode: 0o700 });
    const target = path.join(this.directory, name), temporary = `${target}.${crypto.randomUUID()}.tmp`;
    try {
      await fs.writeFile(temporary, JSON.stringify(value), { mode: 0o600, flag: 'wx' });
      await fs.rename(temporary, target);
      if (this.platform !== 'win32') await fs.chmod(target, 0o600);
    } finally { await fs.unlink(temporary).catch(error => { if (error.code !== 'ENOENT') throw error; }); }
  }
  async credentials() {
    const saved = await this.read('credentials.json');
    if (!Object.keys(saved).length) return {};
    if (this.platform === 'win32') {
      if (saved.scheme !== 'dpapi-current-user' || typeof saved.data !== 'string') throw new Error('Unprotected Windows credentials refused. Run auth login to replace them.');
      return JSON.parse(await dpapi('unprotect', saved.data));
    }
    return saved;
  }
  async credential(origin) { return (await this.credentials())[origin]; }
  async saveCredential(origin, value) {
    const saved = await this.credentials();
    if (value) saved[origin] = value; else delete saved[origin];
    await this.write('credentials.json', this.platform === 'win32' ? { scheme: 'dpapi-current-user', data: await dpapi('protect', JSON.stringify(saved)) } : saved);
  }
  async forgetCredential(origin) {
    // Logout clears even an unreadable credential file; it never falls back to plaintext.
    try { await this.saveCredential(origin, null); }
    catch (error) {
      await fs.unlink(path.join(this.directory, 'credentials.json')).catch(e => { if (e.code !== 'ENOENT') throw e; });
      throw new Error('Credential store could not be decrypted; cleared local credentials for all servers.');
    }
  }
  async sessions(scope) { return (await this.read('sessions.json', [])).filter(item => item.origin === scope.origin && item.user === scope.user && item.cwd === scope.cwd); }
  async saveSession(scope, thread, pending = null) {
    const sessions = await this.read('sessions.json', []);
    const previous = sessions.find(row => row.origin === scope.origin && row.user === scope.user && row.cwd === scope.cwd && row.id === thread.id);
    const item = { ...scope, id: thread.id, name: thread.name, updated: new Date().toISOString(), pending, answers: previous?.answers || {} };
    const keep = sessions.filter(row => !(row.origin === scope.origin && row.user === scope.user && row.cwd === scope.cwd && row.id === thread.id));
    await this.write('sessions.json', [item, ...keep].slice(0, 500));
    return item;
  }
  async saveAnswer(scope, thread, interactionId, body) {
    const sessions = await this.read('sessions.json', []);
    const item = sessions.find(row => row.origin === scope.origin && row.user === scope.user && row.cwd === scope.cwd && row.id === thread.id);
    if (!item) throw new Error('Session is not saved; cannot durably answer an interaction');
    item.answers ||= {};
    item.answers[`${interactionId}:${body.card_id || ''}`] = { interactionId, body };
    await this.write('sessions.json', sessions);
  }
  async clearAnswer(scope, thread, interactionId, cardId = '') {
    const sessions = await this.read('sessions.json', []);
    const item = sessions.find(row => row.origin === scope.origin && row.user === scope.user && row.cwd === scope.cwd && row.id === thread.id);
    if (item?.answers) delete item.answers[`${interactionId}:${cardId}`];
    await this.write('sessions.json', sessions);
  }
}
module.exports = { Store, dpapi };
