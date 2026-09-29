# Benchmark Specification

## Overview
- **Target file:** `web/sites/browser-use-com-ef244017/web-agents-4de235c6/benchmark.css`
- **Interaction model:** scroll-driven reveal for the SVG; benchmark links remain normal links
- **Asset:** inline SVG exported as `benchmark-chart.svg` (viewBox 0 0 1200 640)

## Content and DOM
Section title `Measured on real browser tasks.`; explanation about comparing task success/cost on the 106-task Internal Bench Hard; summary sentence `Browser Use: 82% of tasks solved at 17¢ each. That is 20 points better than Opus 5, which costs 20× more per solved task.`; chart labels Browser Use, GPT-5, Gemini 3.6 Flash, GPT-5.6, Sonnet 5, Gemini 3.1 Pro, Opus 5; metadata `Internal Bench Hard · updated 2026-08-01`; two links to agent benchmarks.

## Computed values
- Section 1200px centered; desktop vertical padding 112px, compact 80px; border bottom `#3d3d3d`.
- H2 52px/55.12px, weight 450, tracking -1.144px, white; body 15px/28px, max-width 576px, secondary gray.
- Chart rendered at 1200×640 on desktop, width 100%, native aspect ratio. It is a cost-vs-accuracy scatter plot, not a bar chart: x-axis is cost per solved task (0¢, $1, $2, $3); y-axis is strict accuracy (20–90%). Browser Use is the pumpkin-orange point; the other six models are gray. A hatched top-left zone says “cheaper and better than every model”; point labels use short leader lines.

## States
- Source chart is inline and receives no remote requests. Feature chart can fade in on first viewport intersection. All benchmarks links are routed to Codezzn login to keep this page in the local product funnel.
