# Particle orb verification — 2026-09-30

- Inspected the live PolyAI login page and preserved its delivered orb source in `source/orb.original.js`.
- Rendering shaders, initial particle seeds, simulation `step()` and rendering `draw()` match the captured source. Shader block SHA-256: `a9b284b97e6fc342fc086f686607a45285011cfafecb7effb8a05c708b8f46a3`.
- Geometry is intentionally adapted to the Codezzn left pane: centered behind the existing login controls, retaining the user-approved 1.5× size. The right promo and authentication flow are unchanged.
- Original grain texture, ambient glow, vignette and feathered backdrop softening are included.
- Real Chromium/WebGL2 test at 1280×720: radius 330 CSS pixels, 32,761 particles, no GL errors, no horizontal or vertical overflow.
- Passed: active animation, shared pause/resume, pointer interaction, context loss/restoration without losing email input, reduced-motion freezing, desktop/mobile resize and no page errors.
- `tests/test_public_landing.py`: 2 passed. JavaScript syntax and `git diff --check`: passed.
- Final in-app browser preview visually checked after separating the clipped backdrop-filter frame from the atmosphere layer.

The same engine does not imply identical pixels in screenshots taken at different times, viewport sizes, animation phases or adaptive GPU quality levels.
