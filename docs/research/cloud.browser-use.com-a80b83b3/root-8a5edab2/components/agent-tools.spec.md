# Local browser agent tool surface specification

## Overview

- **Target files:** `backend/app/agent.py`, `backend/app/browser.py`, `backend/app/capabilities.py`, `tests/test_browser_use_integration.py`.
- **Interaction model:** LLM-selected tool calls in a bounded observe → plan → act → verify loop.
- **Visual screenshot:** optional bounded viewport JPEG, delivered as model image input only when the agent requests it; not saved as a project artifact unless the separate screenshot-to-file tool is used.

## Tool families

- Page/session: get state, list/open/switch/close tabs, navigate/search/back/forward/reload/wait.
- Interaction: click/input, hover, double/right click, drag, scroll, keypress, dropdown, file upload.
- Inspection: extract, search page, find elements/text, read element text/value/attributes/bounds, wait for selector/text.
- Artifacts: screenshot/PDF and browser downloads, always confined to current workspace/project and subject to save approval.

## Safety and correctness requirements

- Every index is tied to the latest page snapshot and invalidated when page structure changes.
- Navigation and subresources must honor admin-configured allowed domains and reject unsafe private-network targets by default.
- One tenant/thread gets its own local context; concurrent operations on the same context are serialized.
- Enforce tab/session/download size bounds to prevent resource exhaustion.
- Upload and output file behavior continues using Codezzn's approval and project artifact registry.
- Website DOM/text is untrusted input. Page content cannot alter system instructions or authorization.
- Screenshot model input is opt-in; it is sent to the configured provider and may be present in the normal resumable task checkpoint. The durable tool-result cache excludes screenshot bytes.

## Required tests

- Official public MCP aliases are registered and routed to local Playwright.
- Inspection and multi-tab operations work in an isolated local browser.
- Downloaded and screenshot files stay within workspace and can be registered as project artifacts.
- Invalid/stale indices and unsafe URLs are rejected.
- Upload/write actions remain approval-gated; tenant/thread sessions do not collide.
