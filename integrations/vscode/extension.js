'use strict';
const vscode = require('vscode');
const crypto = require('node:crypto');
const { options, command } = require('./bridge');
function userConfig() {
  const config = vscode.workspace.getConfiguration('codezzn');
  return Object.fromEntries(['server', 'allowInsecureHttp', 'nodeExecutable', 'cliScript'].map(name => {
    const field = config.inspect(name);
    return [name, field?.globalValue ?? field?.defaultValue];
  }));
}
function activate(context) {
  const selections = new Set();
  const launch = async review => {
    try {
      if (process.platform !== 'win32') throw new Error('This bridge currently supports Windows only. Other platforms can use the HTTP CLI directly.');
      if (!vscode.workspace.isTrusted) throw new Error('Trust this workspace before launching Codezzn.');
      const settings = options(userConfig());
      let attachment;
      if (review) {
        const editor = vscode.window.activeTextEditor;
        const source = editor?.document.getText(editor.selection);
        if (!source) throw new Error('Select code in an editor first.');
        const bytes = Buffer.from(source, 'utf8');
        if (bytes.length > 1024 * 1024) throw new Error('Selected code exceeds 1 MiB.');
        const approval = await vscode.window.showWarningMessage(`Send ${bytes.length} bytes of selected code to ${settings.server}? Codezzn executes only on its server, not in your local repository.`, { modal: true }, 'Send selected code');
        if (approval !== 'Send selected code') return;
        await vscode.workspace.fs.createDirectory(context.globalStorageUri);
        const filename = `selection-${crypto.randomUUID()}.txt`;
        const uri = vscode.Uri.joinPath(context.globalStorageUri, filename);
        await vscode.workspace.fs.writeFile(uri, bytes);
        attachment = uri.fsPath;
        selections.add(uri);
      }
      const cwd = context.globalStorageUri.fsPath;
      await vscode.workspace.fs.createDirectory(context.globalStorageUri);
      const terminal = vscode.window.createTerminal({ name: review ? 'Codezzn · Selection review' : 'Codezzn · Server CLI', shellPath: settings.shell, shellArgs: ['-NoLogo', '-NoProfile'], cwd });
      context.subscriptions.push(terminal);
      terminal.show();
      terminal.sendText(command(settings, { attachment, review }), true);
      // The caller explicitly supplied this selection. No workspace scan, secret
      // token read, shell wrapper, repository config, or automatic local mutation.
    } catch (error) { vscode.window.showErrorMessage(`Codezzn: ${error.message}`); }
  };
  context.subscriptions.push(vscode.commands.registerCommand('codezzn.openCLI', () => launch(false)));
  context.subscriptions.push(vscode.commands.registerCommand('codezzn.reviewSelection', () => launch(true)));
  context.subscriptions.push({ dispose() { for (const uri of selections) vscode.workspace.fs.delete(uri, { useTrash: false }).then(() => {}, () => {}); } });
}
module.exports = { activate, deactivate() {}, userConfig };
