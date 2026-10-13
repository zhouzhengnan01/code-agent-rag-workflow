# Codezzn CLI

A Node.js 20+ terminal client for Codezzn, with a Windows npm executable named
`codezzn`. Its command shape follows the observed public Claude Code help for
interactive prompts, print output, continuation and named sessions. It connects
to Codezzn's own API and does not claim compatibility with private Claude services.

From the repository root in PowerShell:

```powershell
node cli/bin/codezzn.js --help
node cli/bin/codezzn.js auth login --server http://localhost:8080
node cli/bin/codezzn.js
node cli/bin/codezzn.js -p "Explain the selected server project"
node cli/bin/codezzn.js -p --output-format json "Explain this file" --attach "D:\\work\\notes.txt"
node cli/bin/codezzn.js -c
node cli/bin/codezzn.js -r SESSION_ID
node cli/bin/codezzn.js auth status
node cli/bin/codezzn.js auth logout
```

To install the local npm executable explicitly:

```powershell
npm install --global ./cli
codezzn --help
```

The CLI requires a running Codezzn server with CLI browser authorization enabled.
The selected server must match its configured public URL. Remote HTTP requires an
explicit `--allow-insecure-http` on each invocation; HTTPS is the default
requirement outside loopback. Authentication opens a browser approval page, polls
for a device token, and binds the credential to that exact server origin. The
client refuses redirects, including same-origin redirects, for API calls.

Tools execute in the server's configured project / Docker boundary. The terminal's
current Windows directory is a session-selection context, not a mounted project
or authorization to read or execute local files. `--attach` and `/files` explicitly
upload local files as prompt context; `/project` chooses an existing server
project. Native Windows tool execution is not implemented by this client.

Windows credentials are encrypted with DPAPI CurrentUser through the installed
Windows PowerShell executable. The static utility receives secrets on stdin and
uses the machine's current PowerShell execution policy. If PowerShell or DPAPI
is unavailable, storage fails; there is no plaintext fallback. Other platforms
store credentials in a private directory with mode 0600. The default state
directory is `%USERPROFILE%\\.codezzn`; `CODEZZN_CONFIG_DIR` selects another
directory. Saved sessions contain server/user/directory metadata, unfinished
prompts and exact outstanding interaction answers, but no login token. Treat
these files as private conversation data. Logout clears the local credential and
attempts server revocation.

`--agent` accepts a configured agent ID or an unambiguous name. `--model` accepts
an unambiguous configured model or `PROVIDER_ID/MODEL`; `/model` lists available
models and `/model default` restores the agent default. `/skills` and `/mcp` list
configured server resources; they do not install local MCP processes.

`-p` never answers questions or authorizes tools. A waiting task returns
`requires_action` and exit code 2; resume interactively to answer it. Exit code 0
means completion, 1 means failure, and 130 means cancellation. JSON stdout holds
one result object per completed/resumed turn; stream-json uses newline-delimited
public event objects plus a final `type: "result"` object. Diagnostics go to
stderr. Assistant text streams with a short safety tail for split credential
redaction; hidden reasoning and raw tool results are omitted. Terminal control
sequences and recognizable credentials are sanitized. Redaction is a best-effort
display safeguard, not a guarantee that arbitrary sensitive prose can be detected.

Queue submission IDs and exact payloads are saved before transmission. After an
uncertain response, the client queries the server for the same ID before retrying.
Resuming recovers unfinished work. Interaction answers likewise retain their
original ID and payload across an uncertain connection; print mode never replays
an approval. Ctrl+C asks the server to cancel the current durable task; pressing
it again exits immediately. Leaving a question blank denies/cancels it, and a
tool approval requires an explicit `y` or `yes` after showing its actual arguments.

Run the mock HTTP and Windows credential tests from the repository root:

```powershell
node --test tests/test_windows_cli.cjs
```
