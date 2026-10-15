# Confirmation dock specification

## Target / interaction model

- Target: web/workbench.js and web/chat-workbench.css; existing /workbench.html#chat.
- Interaction model: click-to-answer, click-to-collapse/expand, explicit reject/cancel on close. No answer is submitted during inspection or on render.
- Reference: user's live Roboflow Create Cat Detector YOLO Project conversation, inspected through the Codex browser, not inferred solely from screenshots.

## Observed DOM / computed styles

- Separate section, aria-label="Question awaiting your answer", max-height:50vh, overflow-y:auto; not inside the message scroller.
- Card: flex column, white #fff, 1 CSS px border #ddd6fe (reported 0.8 rendered px at host scaling), radius 8px, shadow 0 1px 2px rgba(0,0,0,.05), margin-block:4px, width:100%.
- Header: border-bottom #ede9fe; padding:8px 8px 8px 12px, gap:8px; gradient from purple-50 at .5 opacity to white.
- Header question: 12px, weight500, line-height20px, color #4c1d95. Question icon:20px square, radius6px, background #ede9fe, color #6d28d9, glyph10px.
- Minus/close:20px square, radius6px, no visible border/background, color #6d28d9; hover gains pale purple background.
- Body: padding4px; choice button padding8px, gap8px, radius8px, background white; hover gray-50 #f9fafb.
- Number badge:20px square, radius6px, background #f3f4f6, color #374151, font10px.
- Choice label:13px, weight500, line-height20px, #374151; description12px/16px, #6b7280, gap2px.
- Custom answer row: padding8px, gap8px; pencil badge same as number badge. Input: transparent, border0, padding0, font13px/20px weight500, placeholder12px normal #6b7280; submit arrow20px square purple #6d28d9 / white, shown when nonempty.
- Font observed: Inter/sans-serif; use the existing local application font stack without adding external font requests.

## Integration / state preservation

- Use a separate flex bottom region immediately before the existing footer prompt-dock; not position:fixed over content. Its maximum height is 50vh with internal scrolling so long questions do not hide the composer.
- Pending question/tool approval/project confirmation use this framing. Actual tool arguments remain available in a details disclosure; preserve explicit approve/deny calls and plan revisions. Nonblocking recommendation/decision cards retain their existing timeline position and per-card response semantics; they do not pause execution and do not offer unsupported global denial.
- Keep pending DOM nodes stable across polls. New pending cards are docked; finished cards move to history; no duplicate IDs or stale active controls in history.
- Keep collapse state local per interaction, never interpret collapse as cancel. Close uses the existing denial API and is disabled during pending/unknown submission.
- Failure deletion is a separate persistent presentation action, not destructive data removal or cancellation of an unrelated running task. Display both retry and delete, lock both during request, recover after errors, preserve tenant/thread scoping and unknown-submit protections.

## Desktop acceptance

At desktop width verify card directly above composer, reply scroll independence, expand/collapse, numbered choices, custom-answer submit/Enter and refusal, unknown submission recovery, persisted deletion after refresh, and no duplicate POSTs. No phone/tablet work requested.
