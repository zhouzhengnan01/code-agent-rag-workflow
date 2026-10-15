# Desktop QA — 2026-10-15

## Reference evidence

Inspected the user's signed-in Roboflow Agent conversation through Codex Browser: pending public-project question, numbered options, custom-answer row, header controls, actual computed styles, collapse and re-expand. Left all choices unanswered and did not create/share a project. The user explicitly excluded phone/tablet work after inspection; acceptance is desktop-only.

## Implementation and verification

- Existing route /workbench.html#chat and application background/navigation preserved. Pending questions, project confirmations and tool approvals render above the composer; answered/cancelled records stay in the timeline. Nonblocking decision/recommendation cards preserve the old timeline and per-card semantics.
- 45 Node tests passed (chat interactions and queue, coding panel, LSP frontend); includes pending-history separation, collapse without submission, failure dismissal confirmation and unknown-retry locking.
- 163 Python tests passed in an isolated network-disabled Linux Docker container, using temporary data and read-only source mounts, including conversation APIs, tenant/authentication boundaries, model message contracts, approvals/quality gates and real Chromium desktop rendering. Two pre-existing deprecation warnings; no failures/skips.
- Real Windows Edge desktop interaction test passed: card/composer geometry, #ddd6fe border, 8px option padding and 13px labels, polling preserves free-text, expand/collapse, no automatic approval, custom answer Enter submits once, answered card moves to history, failure dismissal survives reload, tool arguments disclosure and explicit close sends denial.
- Frontend workflow build: npm --prefix frontend/workflow-editor run build passed (TypeScript + Vite).
- Screenshot: docs/design-references/app-roboflow-com-f07e3b30/agent-confirmation-dock-19099711/codezzn-desktop.png (fixture UI; no actual user task executed).

## Failure deletion contract

POST /api/threads/{thread_id}/queue/{message_id}/dismiss persists payload.dismissed_at and returns the authoritative message. Only failed terminal records may be dismissed. Existing status/error/result/history, submission fingerprint and retry links stay intact. Duplicate requests are idempotent; wrong thread/tenant returns404, unauthenticated401, invalid states409. No schema migration, task cancellation or file deletion.

## Boundaries

This is a scoped interaction-component clone, not a full Roboflow page clone or its model/training business implementation. Reuses Codezzn's local font stack and message-column width; no third-party font/image download added. Test data is synthetic, and no real model or user approval was submitted during acceptance.

## Release verification

Built codezzn-app:local successfully (991703e18062). Immediately before release, read-only checks found zero pending/dispatching/running queue executions and zero running background tasks. Preserved the previous image as codezzn-app:before-confirmation-dock-20261015, then recreated only the codezzn application (Broker unchanged). Container reports healthy and /healthz returns status=ok. Verified the running image includes versioned confirmation-dock assets and the dismiss endpoint. Existing business approvals were not answered, cancelled or deleted.
