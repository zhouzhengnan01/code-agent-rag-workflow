# Hero Specification

## Overview
- **Target file:** `web/sites/browser-use-com-ef244017/web-agents-4de235c6/hero.css`
- **Interaction model:** CTA click; image hover; responsive layout
- **Asset:** original `agents-hero-750.webp` / `agents-hero-640.webp`

## Content and DOM
Inside the first section: uppercase eyebrow `FULLY HOSTED WEB AGENTS`; H1 `Browser Use Agents`; lead `Describe the task in a sentence. An agent runs it in a real stealth browser and returns structured data.`; orange `Run your first agent` pill; adjacent hero image with alt `A hand holding a magnifier over a train of glass carriages, each carrying a city`.

## Computed values
- Hero section desktop height 563px after the 64px header; max-width 1200px, 24px page gutters.
- At 1440: H1 68px/68px, weight 450, tracking -4.08px; lead 18px/27px, `#a1a1a1`; button 44px high, 15px/24px medium, 24px horizontal padding.
- At 390: H1 34px; first section is stacked; art retains 16:9 ratio, full width minus 48px gutters.
- Image frame is 16px radius, 1px `#4c4c4c` border, overflow hidden; image transition 1s cubic-bezier(.22,1,.36,1), hover transform 1.035.
- Hero top/bottom padding desktop 104px/72px, compact 64px/56px.

## States
- Default: image scale 1; CTA bg `#fe750e`, black text.
- Hover: image scale 1.035; CTA bg `#fe8f3c`.
- Active CTA: scale .96 for 75ms.
- CTA destination: `/login?next=/workbench.html`.
