# Windows CLI acceptance — 2026-10-13

## Verified

- Backend/account/isolation/conversation tests: 48 passed, including a real Node process, real temporary HTTP server, browser consent, Windows DPAPI, stream-json, continuation and logout. Rerun after the final CLI fix: 48 passed.
- Windows CLI test groups: 14 passed, including explicit default-deny approval, durable retry and answer recovery, credentials split across output chunks, redirect refusal, cancellation and actual executable exit codes.
- Existing web chat tests: 30 passed. No previous retry-banner behavior was reverted.
- npm package dry run: 11 runtime/package files, no bundled dependencies. User-global installation succeeded; `codezzn.cmd --version` returns `0.1.0`.
- Source diff whitespace check and authorization JavaScript syntax check passed.
- Security review initially found a split credential-label leak; repaired and rechecked in text and stream-json. No remaining blocker in that focused review. Display redaction remains best-effort, not a guarantee against arbitrary sensitive prose.

## Running service

- Queue checks before redeployment: zero running, pending or submitting tasks.
- Existing runtime image extended locally with only the CLI authorization backend and consent page; no registry downloads. Prior compiled frontend and unrelated service files retained. Rollback image tag: `codezzn-app:before-windows-cli-20261013`.
- Only the `codezzn` container recreated, without dependency recreation; container healthy.
- `/healthz`, `/cli/authorize`, `/assets/cli-authorize.js`: 200.
- Anonymous `/api/auth/cli/status`: 401.
- Configured public server `http://192.168.35.69:8080/healthz`: 200.
- Login through noncanonical localhost refused with 409 and the configured public server address.

## Coverage limits

- Paid model calls, real GitHub/Google login and user approval were not performed on behalf of the user. Tests use an isolated fake identity and controlled agent; first real CLI browser authorization remains a user action.
- No native Windows project execution, Claude proprietary model/backend, private prompts, IDE features or permission bypass. Existing server tool and Docker policies apply unchanged.
- Native reverse-engineering limitations are recorded in README.md; the implementation follows observed public command interfaces, not recovered proprietary source.
