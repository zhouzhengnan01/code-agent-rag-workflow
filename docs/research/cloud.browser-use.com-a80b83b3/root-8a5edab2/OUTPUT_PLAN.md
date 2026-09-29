# Browser Use Cloud Agent — capability integration plan

## Target and destination

- Source: `https://cloud.browser-use.com/` (normalized origin `https://cloud.browser-use.com`, path `/`)
- Site key: `cloud.browser-use.com-a80b83b3`
- Page key: `root-8a5edab2`
- App root: repository root (`D:\code-agent-rag-workflow`)
- Destination: existing Codezzn workbench conversation/agent runtime, not a new Next.js route.
- Reason for route deviation: this repository is a FastAPI + static HTML application, and the requested work is capability/tool integration. Replacing or adding a Next.js scaffold would conflict with the existing product.
- Existing workbench and prior Browser Use panel/Files work are preserved.

## Evidence limits

- Live Codex in-app browser session lists the target page, but binding/reading that tab timed out repeatedly; no live DOM, screenshots, responsive sweep, or authenticated interaction claims are made.
- Product behavior is based on Browser Use's public OSS docs and manifest, plus the user's supplied screenshots and the current Codezzn source.
- This plan covers the locally implementable agent/tool behavior. Browser Use Cloud's hosted browser, proprietary optimizations, hosted model routing, profiles, and independent judge service are not copied or called.

## Build scope

1. Keep the existing Codezzn LLM tool-call loop and expose Browser Use-compatible local browser actions.
2. Preserve per-tenant/per-thread session boundaries and Codezzn's existing write/upload approval and project artifact rules.
3. Harden navigation, downloads, tab counts, and browser session resource use for a server deployment.
4. Extend tests around official MCP tool aliases, page inspection/actions, downloads, approvals, and unsafe destinations.
5. Keep cloud-only features explicitly outside the local implementation boundary.

## Implementation and verification status

- Implemented the public MCP core action names in the existing local tool registry, plus local hover/double-click/right-click/drag/wait/element/download helpers.
- Added opt-in screenshot-to-model visual observation, bounded data URLs/downloads/uploads, fresh DOM metadata, tenant/thread session locking, tab/session/idle caps, and SSRF-oriented URL/subresource checks.
- Preserved Codezzn's existing model/tool loop, approval semantics, project artifacts, and Files panel; no Browser Use Cloud API or credentials are introduced.
- `python -m pytest -q`: 114 passed, 1 upstream Starlette deprecation warning. Tests used isolated temporary DB/workspace paths.
- Live authenticated Cloud UI inspection was not possible in the Codex browser tab; this is an OSS-based capability adaptation, not a pixel-exact clone or Cloud parity certification.

## Planned artifacts

- `PAGE_TOPOLOGY.md`: product flow and local mapping.
- `CAPABILITY_MATRIX.md`: public Browser Use capabilities mapped to Codezzn, with gaps.
- `BEHAVIORS.md`: interaction and security behaviors, evidence sources, and unknowns.
- `TECH_STACK_ANALYSIS.md`: reference/runtime choices and non-goals.
- `components/agent-tools.spec.md`: implementation contract for the existing tool/runtime surface (not a visual component clone).
- `docs/design-references/cloud.browser-use.com-a80b83b3/root-8a5edab2/`: reserved screenshot location; no screenshot captured because the browser session could not be read.
