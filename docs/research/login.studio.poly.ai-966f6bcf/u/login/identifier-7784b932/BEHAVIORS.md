# PolyAI login particle field — live observations

Observed in the Codex in-app browser on 2026-09-29. No sign-in form was submitted.

- Live sign-in route's page background computed to `rgb(2, 2, 5)` (`#020205`); primary text computed to `rgb(237, 237, 237)`. The current live page remains open and its sign-in controls are present.

- At a 1242 × 668 CSS-pixel viewport, the page renders a large, softly lit spherical particle cloud behind the left-side hero copy. The sign-in panel remains a separate right-side column.
- At 426 px wide, the orb canvas is `display: none`; the live page's inline implementation declares a 761 px minimum width before creating its WebGL context. This is a responsive performance guard, not a connection failure.
- The live implementation describes a WebGL2 particle simulation with position/velocity ping-pong textures, additive point rendering, bloom, and a composite pass.
- A pointer move over the page updates pointer position/velocity uniforms; pointer leave and window blur clear the pointer response. Touch pointers are ignored.
- Focus and form-submit events trigger an orb pulse. `prefers-reduced-motion` disables cursor response; rendering quality degrades when frames are slow.
- The orb is decorative and does not participate in the login form's layout or submit behavior.

# Codezzn adaptation constraints

- Keep the existing split-screen geometry, authentication controls, copy, and right-side promo unchanged.
- Render a decorative point-sphere only as an absolutely positioned layer inside the `.auth-pane`, centered behind the login controls and beneath the brand, form, and footer in the stacking order.
- Match the live page background with `#020205`, preserve readable auth controls, and use restrained gray particles on the dark field; do not copy PolyAI branding, copy, or assets.
- Reuse Codezzn's existing “Pause Animations” control and honor reduced motion, page visibility, and responsive sizing.
