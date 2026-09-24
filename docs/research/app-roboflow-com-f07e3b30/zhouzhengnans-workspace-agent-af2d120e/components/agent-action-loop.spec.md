# Agent action loop interaction specification

## Reference and scope

- Source: `https://app.roboflow.com/zhouzhengnans-workspace/agent` and an existing `solutions/chat/...` conversation inspected on 2026-09-24.
- Target: Codezzn's existing `web/workbench.html` chat. Preserve its routes, authentication, and native JS/CSS stack.
- Interaction model: model-driven conversation, inline choice cards, asynchronous working-session updates, linked assets. No training/upload business features are cloned.

## Observed structure

- Conversation content is centered in a wide white canvas, with user/assistant turns in sequence.
- A consequential choice appears inline immediately after the assistant explains the proposed operation. The card contains a short question and one or more option rows, each with a concise title and a secondary explanation. After selection, the option is checked and disabled while the conversation continues.
- Work sessions are collapsible rows, named by elapsed work. Background tasks are distinct status rows; they progress to completion without users resubmitting the same action.
- Created assets are real persistent objects, linked from the assistant's result and counted in a compact `N Assets` strip above the composer. Asset links can open the corresponding resource.
- The agent can adjust an existing result after user follow-up; it does not create a fresh disconnected resource for every request.

## Codezzn equivalent states

1. User goal received. Read-only intent classification determines whether it requests a persistent artifact/project/workflow or ordinary Q&A. Do not use a frontend keyword regex as the source of truth.
2. If a project choice is material, show an inline choice card: create a project, select an existing one (modal picker), or answer without saving. The selected choice is persisted to the turn; completed cards render as checked/disabled.
3. The agent selects built-in project/workflow tools. A write tool requests an explicit approval when policy requires it. Display the exact action, target project/workflow and consequences rather than only raw JSON.
4. Execution emits tool/workflow progress. On success, show a linked asset card in the assistant result and update the asset strip. On failure, show a recoverable error and do not claim an asset was created.
5. Workflow edits first create a validated draft. Show draft changes and permit save or discard; discarded edits must not modify the active workflow.

## Styling contract for this repository

- Reuse the existing Roboflow-inspired variables, buttons and inline-card styling in `web/roboflow-theme.css`. Avoid introducing a second global design system.
- Existing project picker is a modal and remains the selection UI. Keep cards keyboard reachable and display the selected state explicitly.
- Long filenames and workflow names wrap or truncate without expanding the chat column. Mobile layout uses one column.

## Out of scope

- Roboflow model training, dataset upload, paid operations, and proprietary backend APIs.
- A new Next.js route or an independent frontend application.
