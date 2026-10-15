# Desktop interaction dock — 2026-10-15

- Reference origin: https://app.roboflow.com
- Reference entry: /zhouzhengnans-workspace/agent; inspected the user's existing Create Cat Detector YOLO Project conversation, including its pending question.
- Destination: existing /workbench.html#chat in D:/code-agent-rag-workflow.
- Site key: app-roboflow-com-f07e3b30; page key: agent-confirmation-dock-19099711 (state /agent#confirmation-dock-20261015).
- Scope: move pending interactive confirmations out of the message scroller into a composer-adjacent dock; match Roboflow question-card visuals; persist dismissal of failed queue banners. Preserve execution audit/history, files, approval/version checks and submission deduplication.
- Existing vanilla JS/CSS application is explicitly the requested target. Do not replace it with a Next.js scaffold or introduce another application/route.
- Components: existing web/workbench.js and scoped web/chat-workbench.css; persistent dismissal in backend/app/conversation_control.py and backend/app/chat_sessions.py.
- New research namespace only; existing reference artifacts/routes/assets stay untouched. No new remote images/fonts or third-party assets are needed.
- Desktop only, as explicitly requested. No phone/tablet redesign or acceptance requirement.
- Baseline: node --test tests/test_chat_frontend.cjs: 33 passed.

## Observed behavior / topology

The reference conversation keeps replies in the scrollable message region, while a pending question sits immediately above the composer in a separate bottom region. The question has a compact purple heading, minus and close controls, numbered choices with descriptions, and a one-line custom-answer input with an arrow action. Minus collapses only the body and can be expanded again; it does not submit an answer. The reference question was left unanswered; no project creation or public-sharing action was approved.

Codezzn will keep pending controls only in the dock, and answered/cancelled interactions as compact timeline history. Closing a pending card explicitly rejects/cancels that interaction via the existing authenticated API, never silently approves. Polls must preserve typed answers, collapse state and submission locks. Terminal failed queue banners may be dismissed durably; neither messages nor files nor execution records are deleted.
