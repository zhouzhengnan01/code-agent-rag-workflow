# NavigationRail specification

## Overview

- **Target files:** `web/workbench.html`, `web/roboflow-theme.css`, `web/workbench.js`
- **Interaction model:** hover/focus expansion on desktop; click-driven drawer on mobile; optional pin button

## DOM structure

`studio-shell > aside.workspace-rail` contains brand, generated primary navigation, a pin/expand control, service state, user/session action and logout action.

## Computed styles

### Rail

- Collapsed width: `60px`
- Expanded width: `155px`
- Height: `100vh`
- Display: `flex`, column
- Background: `#0c0f1a`
- Padding: `12px 20px 12px 8px`
- Gap: `8px`
- Right border: `1px solid rgba(255,255,255,.08)`
- Width transition: `200ms cubic-bezier(0,0,0.2,1)`

### Navigation item

- Height: `34px`
- Border radius: `8px`
- Collapsed: centered icon and visually hidden label
- Expanded: left-aligned icon plus single-line label
- Hover background: `rgba(255,255,255,.08)`
- Active background: muted purple with a violet border
- Color transition: `150ms ease-out`

## States and behaviors

- `:hover`/`:focus-within`: width `60px -> 155px`; labels fade/translate into view.
- Pinned: `body.rail-expanded` holds the 155px state.
- Mobile: width `245px`; translated off-canvas until the menu button opens it.
- `prefers-reduced-motion`: transitions are disabled.

## Responsive behavior

- Desktop/tablet above 700px: compact rail with hover expansion.
- Mobile at or below 700px: off-canvas full-label drawer; no hover dependency.

