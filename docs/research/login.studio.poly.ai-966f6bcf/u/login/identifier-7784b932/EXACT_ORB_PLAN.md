# PolyAI particle orb — exact engine adaptation

## Output plan
- Source: https://login.studio.poly.ai/u/login/identifier (temporary OAuth state omitted).
- Existing destination: /login in Codezzn; only the left decorative animation is updated.
- Implementation: web/auth-particle.js, web/auth-particle.css, web/auth-particle-grain.css.
- Original public animation excerpt: docs/research/login.studio.poly.ai-966f6bcf/u/login/identifier-7784b932/source/orb.original.js.
- Preserve login controls, authentication handlers and right-hand promo.
- Preserve the accepted center and the user's latest 1.5× original Codezzn diameter.

## Verified live implementation
- WebGL2, EXT_color_buffer_float, 181×181 = 32,761 particles.
- RGBA32F ping-pong position and velocity simulation.
- Six shader programs: velocity, position, particle, light pools, blur, composite.
- Keep ALL shader strings and initial seeds byte-identical to the extracted source.
- Point size 2.55; exposure 0.74 for desktop; bloom 0.66 plus submit pulse×0.5.
- Particle color ramp: (0.12,0.24,0.42) to (0.86,0.95,1.0).
- Ten broad light pools, additive HDR particle/light scene, half-size two-pass blur.
- Real flowing curl-noise forces, damping, cohesion, stray/rogue motion and pointer inertia.
- Orbit 0.055 rad/s; bob sin(time×0.21)×0.09; breathe sin(time×0.31)×0.012.
- Pointer radius 1.55; smooth 13/s; strength easing 5/s; velocity easing 9/s, cap6.
- Focus raises tighten at 3.2/s; keystrokes add voice0.16 capped0.5; decay2.4/s.
- Submit displacement wave: speed7.4; pulse decay1.9/s, expires1.9s.

## Compositing layers, extracted CSS
- Pane background rgb(2,2,5).
- Full viewport-sized atmosphere clipped by the existing left pane.
- mark-glow: radial ellipse34%46% at26%58%, rgba(237,237,237,.045)/.01452%/transparent76%.
- Glow breathes80s ease-in-out alternating, opacity.8→1, translateY0→-1.5vh.
- Original 256×256 PNG grain tile at128×128 CSS pixels.
- Lit grain opacity.42, screen blend; ellipse54%74% at26%58% mask .9/.5 at42%/.16 at70%/transparent94%.
- Base grain opacity.09.
- Vignette ellipse130%100% at50%42%, transparent62% to black.42 at100%.
- Hero scrim: blur13px brightness.62 saturate.85, background rgba(2,2,5,.1), source radial feather mask.
- These ambient layers are part of the original perceived orb color/density; do not omit them.

## Adaptation boundaries
- Change only host/form selectors, pane-relative center, diameter and pointer coordinates.
- Compute scale from model radius3.36, camera12.2 and focal1/tan(.3665) to retain the accepted pixel diameter.
- Use full-viewport canvas width to preserve original vignette/compositing proportions.
- Match source quality fallback: lower DPR before particle count; no orb on phones below761px.
- Keep original GPU context restoration without reloading authentication.
- Add existing Codezzn shared pause, dynamic reduced-motion and offscreen/hidden stopping.
- Decorative layers never intercept mouse/keyboard or change flow layout.

## Acceptance
- Source shader strings and seeds match the original; no approximate substitute.
- Live browser shows the source's flowing particles, soft rim, cool-white ramp and grain.
- Verify pointer/focus/typing/submit, shared pause, resize, reduced motion, context loss/restoration.
- Verify the diameter equals the prior accepted1.5× sizing and center is unchanged.
- Node syntax and real browser rendering must pass.
