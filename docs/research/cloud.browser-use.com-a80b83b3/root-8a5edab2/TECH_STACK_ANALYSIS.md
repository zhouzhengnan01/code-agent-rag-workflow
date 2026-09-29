# Technical reference and implementation choices

## Reference

- Browser Use OSS repository: `https://github.com/browser-use/browser-use` (MIT-licensed Python/TypeScript browser-agent framework).
- Public Cloud description: `https://github.com/browser-use/browser-use/blob/main/CLOUD.md`.
- Public default agent behavior: `https://github.com/browser-use/browser-use/blob/main/browser_use/agent/system_prompts/system_prompt.md`.
- Public MCP manifest: `https://github.com/browser-use/browser-use/blob/main/browser_use/mcp/manifest.json`.

## Codezzn runtime

- FastAPI backend, existing chat-completion/Responses tool loop, local Playwright Chromium, existing tenant/workspace/project scopes, user approvals, run checkpoints, and Files artifacts.
- Extend the existing runtime instead of inserting Browser Use Cloud credentials or calling their hosted API. This keeps the configured Codezzn model and local approval/workspace policy in control.
- Reference the public behavior patterns, not private Cloud prompt text; do not expose chain-of-thought. The implementation prompt asks for concise task progress, actions, and verification rather than private reasoning.

## Not a clone

- Browser Use Cloud's hosted browser fork, stealth/anti-bot stack, profile service, Cloud API, hosted model gateway, usage billing, and independent evaluator are proprietary service behavior and are out of this local integration's scope.
- No new Next.js application or replacement of existing Codezzn routes is planned.

