# Roboflow Agent-inspired workbench output plan

- Source: `https://app.roboflow.com/zhouzhengnans-workspace/agent`
- Destination: existing Codezzn route `/workbench.html` (the user explicitly requested redesign of this existing frontend).
- App root: repository root; the project is FastAPI + static HTML/CSS/JS, not the Next.js template assumed by the cloning skill. Preserve this architecture and all backend APIs.
- Source namespace: `app-roboflow-com-f07e3b30/zhouzhengnans-workspace-agent-af2d120e`.
- Implementation files: `web/workbench.html`, `web/workbench.css`, `web/workbench.js`.
- Design goal: emulate navigation, hero composer, suggestion chips, card organization and responsive behavior while retaining Codezzn's own Chinese labels, data, actions and existing routes.
- No Roboflow account data, example images or branding will be copied into the local application.
- Existing routes: all API routes and `/workbench.html` remain in place; no route is removed.

## Observed topology

1. Desktop left rail: 60px collapsed, dark `#11131b`-like surface; workspace badge, stacked icon navigation, bottom controls. Expanded width approximately 155px; navigation labels appear.
2. Main hero: pale white/lavender gradient, centered `30px` semibold Inter heading. At 1440px, hero is roughly 540px tall including vertical padding.
3. Composer: white rounded card, 736px wide at 1440px, 125.6px tall, 0.8px `rgb(221,214,254)` border, 8px radius, internal padding 16px, bottom toolbar.
4. Suggestion chips: four 32px-high white pill buttons with `rgb(229,231,235)` borders; fifth centered connection CTA.
5. Lower panel: white rounded workspace card. Desktop has examples on the left and recent conversations on the right. Narrow screens replace the split with Conversations/Examples tabs.
6. At 390px, navigation becomes a 56px dark top bar and content stacks with 24px horizontal padding.

## Interaction model

- Sidebar: click-driven collapse/expand; mobile menu overlay.
- Composer: typing + send; local adaptation routes the prompt into Codezzn's existing chat workflow.
- Suggestions: click-driven navigation into the relevant Codezzn sections.
- Lower panel: desktop split; mobile tabs click-switch content.
- Hover: subtle gray/purple background transitions on nav items, pill buttons, and cards.
- No scroll-driven state changes were observed on the Agent landing page.
