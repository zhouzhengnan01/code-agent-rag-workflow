# Component inventory

| Component | Structure / states | Responsive behavior |
|---|---|---|
| PrimaryHeader | Sticky logo, link groups, Showcase/Resources popovers, GitHub metric, login/start actions; hover/focus/open menu states | Desktop link row at `lg`; compact hamburger at 768/390 |
| Hero | Eyebrow, H1, lead, pill CTA; framed original art with hover scale | Desktop 2-column; compact stacked, full-width 16:9 image |
| Benchmark | H2, explanatory copy, native inline SVG chart, source/date and benchmark links | Chart retains 1200:640 aspect inside horizontally safe container |
| ParallelRunsRow | H2/description + 24-column concurrent-run grid | Two columns at `sm`, stacked below 640-ish |
| BrowserReachRow | H2/description + 81%/2% progress bars | Two columns/stacked |
| MonitoringRow | H2/description + 40-ish event bars and caption | Two columns/stacked |
| StructuredOutputRow | H2/description + JSON card/caption | Two columns/stacked |
| CodeExamples | explanatory copy, quickstart, CURL/PYTHON/NODE tabs, copy icon, syntax-colored snippet | Two columns at desktop; stacked with horizontal code overflow on narrow screens |
| ClosingCTA | Large heading and orange pill CTA | 52px desktop title scales down at mobile |
| FAQ | Six keyboard-operable disclosure buttons with answers and chevrons | Max width 768px; full width with 24px gutters |
| Footer | Six product/navigation groups, legal/info row, status, product map | Multi-column desktop grid; disclosure rows on compact screens |
| CookieNotice | Fixed bottom privacy note, policy link, Reject/Accept | Compact bottom card; locally persisted choice |
