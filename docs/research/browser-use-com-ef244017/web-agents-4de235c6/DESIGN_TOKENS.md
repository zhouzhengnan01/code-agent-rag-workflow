# Design tokens

Values were read from computed styles on the rendered source page at a 1440×900 CSS viewport.

## Color

| Token | Value | Use |
|---|---|---|
| page/surface-0 | `#000000` | Page background |
| surface-1 | `#0a0a0a` | Dark inset surfaces |
| surface-2 | `#171717` | Hover surfaces |
| surface-3 | `#222222` | Neutral chart bars |
| copy-strong | `#fafafa` | Primary copy |
| copy-body | `#e5e5e5` | Body copy |
| copy-secondary / muted | `#a1a1a1` | Secondary copy |
| line | `#3d3d3d` | Section/card dividers |
| line-strong | `#4c4c4c` | Strong outlines |
| pumpkin-500 | `#fe750e` | Primary orange |
| pumpkin-400 | `#fe8f3c` | Hover orange |

Additional orange ramp observed: 50 `#fff8f3`, 100 `#ffddc5`, 200 `#ffc397`, 300 `#ffa969`, 600 `#db6103`, 700 `#ac4e04`, 800 `#7e3b04`, 900 `#512704`, 950 `#251202`.

## Typography

- Sans: Geist variable, weights 100–900; browser computed family `Geist, "Geist Fallback"`.
- Mono: Geist Mono variable, weights 100–900; used for metadata, code, chart labels.
- Body base: 16px/24px. Lead: 18px/27px. Regular paragraph: 15px/28px. Meta: 13px; micro: 11px.
- Hero title: 68px/68px, weight 450, tracking `-4.08px` at desktop; 34px on 390px.
- Section title: 52px/55.12px, weight 450, tracking `-1.144px`.
- Feature row title: 28px/35px, weight 450, tracking `-0.84px`.

## Geometry and motion

- Main max width: 1200px; side gutters: 24px.
- Main section vertical padding: 112px desktop (`sm:py-28`); 80px compact (`py-20`). Hero has its own 104px top/72px bottom desktop and 64px/56px compact padding.
- Header: 64px fixed; controls 40px high; pill buttons radius 9999px.
- Hero art frame: 16px radius, 1px `#4c4c4c` border; source asset aspect ratio 580:326.
- Main CTA: 44px high, 24px horizontal padding, 15px/24px medium label.
- Standard UI transitions: 150ms `cubic-bezier(0.22, 1, 0.36, 1)`; image hover 1s same easing; FAQ chevron 300ms.
