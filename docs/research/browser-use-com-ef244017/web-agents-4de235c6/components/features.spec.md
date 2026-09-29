# Feature Rows Specification

## Overview
- **Target file:** `web/sites/browser-use-com-ef244017/web-agents-4de235c6/features.css`
- **Interaction model:** scroll-triggered one-time figure reveal; text is static

## DOM and exact content
Four 50/50 rows, title/description on the left and visual on the right:
1. `Thousands of agents in parallel` / Every run gets its own isolated session: a stealth browser, a proxy exit and a model context. Fan out a queue of work and collect the results. Figure: 24-column cell grid; caption `One cell = one concurrent run · each with its own browser, proxy and model context`.
2. `Runs on our own stealth browsers` / The agent drives the same infrastructure behind stealth browsers, so it reaches sites that block a stock headless browser on the first request. Figure: Browser Use 81% / Stock headless Chrome 2%; caption `Protected sites reached on our stealth benchmark`.
3. `Real-time web monitoring` / Describe what to watch in a sentence and get told when it changes. No scrapers to maintain, no selectors to repair, no diffing logic to write. Figure: 40-ish bars with tall orange ticks; caption `One tick = one check · the tall ones are the runs that came back different`.
4. `Structured outputs` / Results come back as JSON you can hand straight to the next step, with webhook callbacks when a run finishes. Figure JSON `{title:"Aeron Chair",price:1395.00,currency:"USD",in_stock:true}`; caption `You define the shape · the agent fills it in`.

## Computed styles and responsive behavior
- Parent max width 1200px; border top `#3d3d3d`; each row 1px bottom border, 32px compact / 40px desktop vertical padding.
- Row layout `minmax(0,1fr) minmax(0,1fr)`, gap 48px desktop; stacked compact. Title Geist 28px/35px, weight 450, tracking -.84px. Supporting text 13px/28px, max-width 448px.
- Visual width max 330px except the concurrency matrix (576px). JSON and small chart text use Geist Mono 11px; orange `#fe750e` against black; neutral bars `#222222`.

## Motion
- Progress bars animate from 0 to 81% and 2% when visible. Matrix and tall monitoring bars reveal in a short stagger. Use IntersectionObserver with `prefers-reduced-motion` handling.
