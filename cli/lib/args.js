'use strict';
const HELP = `Usage: codezzn [options] [prompt]
       codezzn auth login|status|logout [options]

Codezzn opens an interactive session by default. -p prints one turn and exits.
This HTTP client runs tools on the selected server / Docker project boundary.
Your local working directory identifies sessions; it grants no Windows file or
command execution permission. Local files are sent only with --attach or /files.

Options:
  -p, --print                 Print a response (never approve interactions)
  --output-format FORMAT      text, json, or stream-json (requires --print)
  -c, --continue              Continue the last session for this server/user/cwd
  -r, --resume [ID]           Resume an ID, or choose a saved session
  --agent ID_OR_NAME          Select a configured server agent
  --model MODEL               Configured model, or PROVIDER_ID/MODEL
  -n, --name NAME             Session name
  --server URL                Server origin (default http://localhost:8080)
  --allow-insecure-http       Explicitly allow HTTP to a non-loopback server
  --attach PATH               Upload a local file (repeatable; max 8)
  --no-browser                Display login URL without opening a browser
  -h, --help                  Show this help
  -v, --version               Show CLI version

Interactive commands:
  /help /new /resume [ID] /model [MODEL] /agent [ID_OR_NAME]
  /project [ID_OR_NAME] /status /stop /files [PATH] /skills /mcp /exit
  /SKILL_NAME [TASK] or /skill NAME [TASK]   Load a Skill on demand
  /permissions [default|acceptEdits|plan|inherit]
  /plan [GOAL] /diff [CHECKPOINT_ID] /context /review [SCOPE]
  /rewind CHECKPOINT_ID       Preview then request server approval; never force

Authentication uses browser approval and a server-scoped credential. Windows
credentials use DPAPI CurrentUser. No token arguments or permission bypass flags
are supported. Ctrl+C cancels the current server task; a second press exits.
`;
function parse(argv) {
  const o = { attachments: [], format: 'text' }, positional = [];
  const values = { '--output-format': 'format', '--server': 'server', '--agent': 'agent', '--model': 'model', '-n': 'name', '--name': 'name', '--attach': 'attachments' };
  const booleans = { '-p': 'print', '--print': 'print', '-c': 'continue', '--continue': 'continue', '--allow-insecure-http': 'insecure', '--no-browser': 'noBrowser', '-h': 'help', '--help': 'help', '-v': 'version', '--version': 'version' };
  for (let i = 0; i < argv.length; i++) {
    const raw = argv[i];
    if (raw === '--') { positional.push(...argv.slice(i + 1)); break; }
    const equal = raw.indexOf('='), key = equal > 0 ? raw.slice(0, equal) : raw;
    if (values[key]) {
      const value = equal > 0 ? raw.slice(equal + 1) : argv[++i];
      if (!value || value.startsWith('--')) throw new Error(`${key} requires a value`);
      if (key === '--attach') o.attachments.push(value); else o[values[key]] = value;
    } else if (booleans[key]) {
      if (equal > 0) throw new Error(`${key} does not take a value`);
      o[booleans[key]] = true;
    } else if (key === '-r' || key === '--resume') {
      o.resume = equal > 0 ? raw.slice(equal + 1) : argv[i + 1] && !argv[i + 1].startsWith('-') ? argv[++i] : true;
    } else if (raw.startsWith('-')) throw new Error(`Unsupported option: ${key}. Run codezzn --help.`);
    else positional.push(raw);
  }
  if (positional[0] === 'auth') {
    if (positional.length !== 2 || !['login', 'status', 'logout'].includes(positional[1])) throw new Error('Usage: codezzn auth login|status|logout');
    o.auth = positional[1];
  } else o.prompt = positional.join(' ');
  if (!['text', 'json', 'stream-json'].includes(o.format)) throw new Error('Invalid output format; choose text, json, or stream-json');
  if (o.format !== 'text' && !o.print) throw new Error('--output-format requires --print');
  if (o.continue && o.resume) throw new Error('--continue and --resume cannot be combined');
  if (o.attachments.length > 8) throw new Error('At most 8 attachments are allowed');
  return o;
}
module.exports = { HELP, parse };
