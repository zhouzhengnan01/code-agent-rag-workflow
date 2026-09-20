# Dashboard specification

## Overview

- Target file: `web/workbench.js`, function `dashboard()` and small related handlers only.
- Interaction model: typed prompt / click-driven chips and cards.
- Screenshot reference: source was inspected in the authenticated Codex browser at 1440×900 and 390×844; screenshots remain in the browser observation because the browser surface does not expose a persistent screenshot file.

## DOM structure

- `.rf-dashboard`
  - `.rf-hero`
    - `h1`: "今天想构建什么？"
    - `.rf-composer` containing textarea, toolbar, agent label, history button and send button
    - `.rf-suggestions` linking to existing Codezzn sections
    - centered connection CTA
  - `.rf-home-panel`
    - `.rf-home-tabs` for mobile
    - `.rf-examples` showing Codezzn's existing setup paths as cards
    - `.rf-recent` showing existing conversation data

## Computed styles from source

- Source `h1`: Inter, sans-serif; `30px`; weight `600`; color `rgb(17,24,39)`; line box 36px.
- Source hero wrapper: flex column, centered, gap `32px`, desktop vertical padding `80px 0px`, max-width around 1280px.
- Source composer outer card: width `736px` at 1440px viewport, height `125.6px`, background `rgb(255,255,255)`, border `0.8px solid rgb(221,214,254)`, border-radius `8px`, shadow includes `rgba(0,0,0,.1) 0px 1px 3px 0px` and `0px 1px 2px -1px`.
- Source composer inner padding: `16px`, flex column, gap `12px`.
- Source suggestion buttons: height `32px`, background `rgb(255,255,255)`, border `0.8px solid rgb(229,231,235)`, border-radius `9999px`, text `12px` weight `500`, padding `0 12px`.
- Source primary send button: 32×32px, circular, `rgb(109,40,217)` background, white text.

## States and behavior

- Empty prompt: send disabled. Nonempty prompt: enabled. Pressing Enter (without Shift) sends. Shift+Enter inserts newline.
- Sending the landing-page prompt opens the existing chat page and sends the prompt via the existing `sendMessage()` path; avoid introducing a second backend call path.
- Recent conversation item opens its actual thread.
- Mobile tab choice switches between setup examples and recent conversations without destroying either dataset.
- Hover style handled in CSS; JS must preserve focus/keyboard controls.

## Per-state content

- Suggestions adapt source labels to Codezzn: 创建智能体、接入模型、编排工作流、打开知识库.
- Connection CTA: "配置编码智能体" opens the agents page.
- Examples use existing `setup` array, rather than source site examples.
- Recent conversation cards use `recent.data` already returned by `/api/threads`.

## Assets

- No remote images: Roboflow's model/vision example images are unrelated to Codezzn's coding-agent domain. Use CSS/icon treatments and existing local data.

## Responsive behavior

- 1440px: centered hero and desktop two-column lower panel.
- 768px: narrower composer and card columns.
- 390px: full-width composer, wrapped suggestions, single-column panel with tabs.
