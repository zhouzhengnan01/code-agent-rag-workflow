# Interaction behavior record

## Observed from user-provided screenshots

- Agent task UI is a prompt composer with model/reasoning controls and run settings.
- A run displays messages in a primary pane and generated files in a right-side Files area.
- File assets are shown as a nested list and can be downloaded/opened.
- The cloud agents landing page has an assistant/help widget; unrelated marketing-page behavior is outside this capability integration.

## Verified in the authenticated Cloud UI on 2026-09-29

- The run composer exposes model selection, reasoning effort, Fast mode and a send action.
- An existing session renders compact user bubbles, an expandable `Worked for …` run summary, and assistant replies with inline file chips such as `quicksort.py`.
- The session header exposes a Files panel toggle; the user's existing session displays generated project files and a previous response can answer a project-list question from its workspace context.
- A simple new-run prompt was entered in the UI, but the Cloud Run task button did not navigate or create a run during inspection; therefore the live running/thinking animation and every hosted tool outcome remain unverified.

## From public Browser Use source/docs

- A Cloud session owns one browser and allows only one active agent at a time; sequential agent runs can reuse that session.
- The agent iterates over task context, browser state, and tool calls; public system behavior treats screenshots as ground truth and requires checking completed actions before success.
- Public MCP tools include navigate, click, type, get-state, extract, scroll, back, list tabs, switch tab, and close tab.
- Browser Use supports local Python-library/CLI operation separately from the hosted Cloud product. This project uses local Playwright and Codezzn's configured model.
- Public documentation describes cloud-only services (hosted browser, profiles, optimized browser, hosted model routing, judging); these are not represented as local parity.

## Interaction/security rules for Codezzn

- Browser page content is untrusted data, never a system instruction or permission grant.
- Refresh browser state after navigation or page-changing actions before reusing element indices.
- Visual inspection is explicitly requested with `include_screenshot`; a viewport JPEG is bounded to under 768 KiB and sent to the configured model, not Browser Use Cloud. The task checkpoint may retain normal model input for resumability, while the durable tool-result cache omits screenshot bytes.
- Uploads, page mutation, arbitrary JavaScript, and saving output retain Codezzn's approval/write policies.
- Success claims require checking the resulting page or file; unresolved login/permission/challenge blocks mean partial failure.
- Local browser requests must not become a server-side request forgery path to private services or cloud metadata endpoints.

## Unverified

- Cloud's private system prompt, complete hosted tool catalog, live running/thinking animation, and backend execution semantics are not exposed by the public repository or this UI inspection.
- The Codezzn integration implements the observable workflow using local tools; it is not a pixel-perfect or capability-identical copy of the hosted Cloud service.
