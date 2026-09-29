# Layout architecture

- Fixed full-width header at `z-index:50`; page body is black and scrolls natively.
- Header inner container and all main content share a centered 1200px max width. At viewport 1440, usable document width measured 1425px after scrollbar and content starts x=112px.
- Hero occupies a 1200px grid with approximately 0.85fr text / 1.15fr image columns and 32–48px gap. At widths below the large (`lg`, approximately 1024px) breakpoint, order becomes text then image.
- Benchmark section has 112px vertical padding on desktop / 80px at compact widths. Its SVG chart is full-width with fixed viewBox ratio 1200:640.
- Four middle rows use 2 equal columns from `sm` upward, 48px column gap, 32–40px row padding, and bottom rules; compact layout stacks figure beneath text.
- Code section uses a 0.85fr/1.15fr grid, 48px gap, and vertically centers content. Code panel has an overflow-x scroll region.
- Closing CTA is a 1200px text container. FAQ is centered, max-width 768px. Footer has six columns, switching to accordions below the desktop breakpoint.
- Site-specific CSS is scoped to `.bw-site` to avoid changing authenticated workbench, login, or registration styles.
