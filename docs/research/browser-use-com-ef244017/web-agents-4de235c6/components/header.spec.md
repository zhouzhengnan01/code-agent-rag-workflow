# Header Specification

## Overview
- **Target file:** `web/sites/browser-use-com-ef244017/web-agents-4de235c6/header.css`
- **Interaction model:** click/keyboard-driven menu; fixed while page scrolls
- **Reference screenshot:** browser observation at 1440×900; compact view at 390×844

## DOM and content
Fixed 64px header with a centered max-width 1200px row. Brand asset left; Agents, Browsers, Showcase, Resources, Pricing; GitHub metric, Log in, Start for free. At compact widths, hide desktop links and show hamburger that opens the same destinations in a panel.

## Computed values
- Header position `fixed; inset-inline:0; top:0; z-index:50; height:64px`.
- Background `color(srgb 0 0 0 / 0.85)`, `backdrop-blur-md`, 1px `#3d3d3d` bottom rule.
- Inner max width 1200px; header logo box 119×40 at viewport x=136 on the desktop reference; nav buttons 40px high, 12px horizontal padding, 15px font.
- Login: 40px high, 16px horizontal padding, 13px Geist medium, 9999px radius, transparent with 1px `#4c4c4c` border.
- Start: 40px high, 16px horizontal padding, 13px Geist medium, black text on `#fe750e`, pill radius.
- Nav hover transitions 150ms `cubic-bezier(0.22,1,0.36,1)`; hover background `#171717`; focus 2px pumpkin ring.

## Behaviors
- Sticky header remains at the viewport top while main content scrolls.
- At desktop (1440px) show full nav; at tablet/mobile (768/390) hide it and expose hamburger.
- Showcase/Resources buttons expand their dropdown; mobile menu exposes nav entries. Escape closes menu; selecting a link closes it.
- Log in and Start for free both resolve to `/login?next=/workbench.html`. GitHub metric resolves to the Codezzn repository in a new tab.
