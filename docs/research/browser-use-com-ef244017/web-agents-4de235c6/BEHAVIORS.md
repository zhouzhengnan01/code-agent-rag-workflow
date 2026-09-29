# Behavior bible

Inspected in the Codex in-app browser at 1440×900, 768×900, and 390×844. The 1440 view exposed desktop navigation; 768 and 390 use the compact menu. At 390 the hero stacks, uses a 34px title, and the footer becomes disclosure rows. The actual in-app screenshot surface is narrower than its CSS viewport, so these dimensions are taken from the page's read-only viewport/DOM measurements.

## Header and navigation

- Header is fixed at `top: 0`, `height: 64px`, `z-index: 50`; background resolves to black at 85% opacity with `backdrop-blur-md`; thin bottom rule.
- Wide layout shows brand, Agents, Browsers, Showcase menu, Resources menu, Pricing, GitHub star link, Log in, and Start for free.
- At the compact breakpoint (desktop links are zero-width at 768px; hamburger visible at 390px; source uses `lg:hidden`), show the menu button. Menu opens/closes an overlaid/dropped navigation surface; close by selecting a destination or pressing its close control.
- Nav links use 150ms color/background transitions; orange focus ring. Menus expose their submenu links.
- Codezzn wiring overrides product/login destinations: login/start links open Codezzn `/login?next=/workbench.html`; GitHub opens the Codezzn repository. Internal section anchors remain scroll links.

## Hero

- Two-column desktop composition: left eyebrow/title/body/CTA; right original 580×326 hero illustration in a rounded, bordered, overflow-hidden frame. At 390px it stacks vertically and the image remains full-width with its 16:9 ratio.
- Image hover scales to `1.035` over `1s cubic-bezier(0.22, 1, 0.36, 1)`; honor reduced-motion preferences.
- CTA uses orange `#fe750e`; hover uses `#fe8f3c`; active scale `.96` over 75ms; it routes to Codezzn login.

## Content and scroll

- Page is one native vertical scroll surface with six content sections; no scroll snapping. Header stays fixed while scrolling. Sections use dark background and 1px `#3d3d3d` dividers.
- Benchmark chart is an inline SVG sourced from the rendered page. Feature rows use a 24-column concurrency matrix, an 81%/2% comparison, a monitoring bar chart, and a structured JSON panel. The progress bars animate from zero when entering the viewport; the matrix and monitoring chart have staggered orange activity. Implementation uses IntersectionObserver with once-only reveal to preserve the observed scroll-triggered behavior without shipping remote JavaScript.
- Code examples are click/keyboard-driven tabs: CURL is selected initially; Python and Node select their own snippets. Copy button copies the currently selected snippet and briefly reports “Copied”.

## FAQ and footer

- FAQ is a disclosure list; first question is open on load. Clicking another question opens its answer and rotates the chevron; transition is 300ms. Each answer is distinct.
- Desktop footer presents six navigation groups as columns. On compact screens each group collapses into an accordion row; the Product group was verified opening to Browser Use Agents and Browser Infrastructure. Links are wired to Codezzn login except the Codezzn GitHub repository.
- Initial page can show a cookie-preferences banner with Reject and Accept actions. Either action persists a non-sensitive local preference and dismisses the banner; the privacy link stays local rather than sending visitors to the source company.

## States inspected / limitations

- Captured original desktop hero and compact hero, mid-page code/CTA, and compact footer screenshots in browser observations. `pageAssets` exported the original visual assets (logo variants, hero image, fonts, icon SVGs, and benchmark chart) with no download failures.
- Hover-only styles were read from the source class/transition rules rather than simulated with a pointer. The UI automation surface has click/drag/scroll but no hover primitive.
- Click sweeps confirmed the mobile footer disclosure. Code tabs, FAQ, and desktop menu are represented in the accessibility tree and DOM as interactive controls; the source control click did not reliably change selection through the remote browser bridge, so the clone implements standard click + keyboard semantics and will be locally tested.
- Cookie choice may already be persisted in this browser profile; the first screenshot showed the banner before the accidental navigation to the privacy page. Clone includes the first-visit banner state.
