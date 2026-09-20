# Navigation shell specification

## Overview

- Target files: `web/workbench.html`, `web/workbench.css`, `web/workbench.js` navigation markup.
- Interaction model: click-driven collapsed/expanded desktop rail; mobile top bar plus menu.

## DOM structure

- Dark left rail with compact workspace badge, icon-and-label nav items, health/utility footer and collapse control.
- Existing Codezzn nav destinations remain unchanged.
- Main dashboard has no separate top command bar, following the source landing page. Other Codezzn pages retain their utility actions in a light top bar.

## Computed styles from source

- Collapsed workspace button: 31.2×32px, 8px radius, translucent white 5% background.
- Navigation item icon hit areas: approximately 32×32px, 8px radius.
- Source sidebar collapsed width: ~60px; expanded screenshot width: ~155px.
- Source mobile top bar height: ~56px.
- Source body font: Inter, sans-serif, 16px base.

## States and behavior

- Active nav item outlined/tinted purple.
- Expand button toggles desktop width and label visibility.
- Mobile menu opens the existing rail as overlay and keeps route controls working.
- No backend behavior changes.

## Assets

- Use simple local glyphs/SVG icons; no Roboflow logo, account avatar, or usage data.

## Responsive behavior

- Desktop: 60px collapsed rail, optionally expanded to ~155px.
- Mobile (390px): rail hidden; 56px dark top bar with workspace mark and menu button.
