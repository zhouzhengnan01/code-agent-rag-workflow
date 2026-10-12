# Verification and adaptations — 2026-10-12

The requested existing Codezzn route and real backend take precedence over a fresh Next.js scaffold. No source route, third-party account data, paid settings, logo, or avatar was recreated as Codezzn product data. The source session was only inspected, never sent a task.

## Source and target checks

Source screenshots captured at 1440 desktop, 768 tablet and 390 mobile. Desktop/tablet have a persistent 240px sidebar; mobile hides the sidebar behind an explicit button. Composer is 640px maximum, 16px radius, light border; tablet/mobile fill the available width with gutters. Exact desktop computed styles and image/SVG inventory are in LIVE_STYLES.json.

Codezzn desktop was measured at sidebar 240px, composer 640px, header 48px. Message cards use the same 640px reading column. At 768px the composer shrinks alongside the sidebar; at 390px it measures about 366px with 12px gutters. Source mobile model control truncates long names; Codezzn uses a native select with a constrained width and keyboard support.

Intentional adaptations: Chinese product copy; existing Codezzn logo and purple accent; all platform menu entries; history nested under 对话调试; an additional compact project/Skill/MCP row in the composer; native model selector populated by local configuration; no unsupported billing, reasoning, fast mode or share action. Independent message scroll and bottom composer preserve task context. File panel retains existing real project artifacts.

## Functional browser checks

Executed using the actual application handlers, API, tenant database, attachment parser, Agent input assembly and SSE state machine with deterministic model responses and stubbed tools/context in a temporary QA process. Production data and credentials were not used. This verifies integration, not third-party inference quality or sandbox connectivity.

- Upload TXT through picker; verify extracted CHAT-640-2026 reaches model input and answer.
- Explicit chat-precise selection reaches runtime; refresh retains selection and attachment.
- PNG becomes image_url input; image preview loads as an authenticated Blob.
- Attachment download produces the original test file through the authenticated handler.
- Stop a slow stream; textbox becomes available and a subsequent task can run.
- Rename and archive using sidebar menus; search and history updates work.
- Files panel opens with a meaningful empty/project selector and closes.
- Desktop/tablet/mobile screenshots inspected; mobile drawer opens/closes explicitly and hides offscreen keyboard targets.
- Final browser console: no errors/warnings.

## Automated checks

- 28 new backend attachment/model tests pass.
- 136 relevant backend tests pass in the Linux Docker image, including new tests and Agent, platform, project, workflow, knowledge and tenant regressions.
- 9 frontend tests pass (7 chat handlers, 2 existing knowledge entry points).
- `node --check web/workbench.js`, `git diff --check`, TypeScript/Vite build and Docker prebuilt build pass.
- Initial Windows regression hit a pre-existing `os.chown` assumption; the corresponding Linux suite passes without exclusions.

Screenshots: source files in the planned design-reference root; final implementation images in outputs/chat-workbench. Artifact images in the implementation screenshots are synthetic QA input.
