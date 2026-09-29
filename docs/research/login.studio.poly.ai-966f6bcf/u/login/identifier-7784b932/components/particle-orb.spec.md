# Component spec: login particle field

## Purpose

Add the live-observed PolyAI-style spherical particle animation behind Codezzn's login controls. The pane uses the observed PolyAI page background (`rgb(2, 2, 5)` / `#020205`); the animation must remain decorative and must not alter authentication or layout flow.

## Placement and layering

- Mount a single `aria-hidden` canvas as a direct child of the existing login `.auth-pane`.
- Center it absolutely behind the provider button group, spanning the pane width. Keep the buttons above the sphere in the stacking order, with a translucent dark surface so particles remain subtle beneath them. The canvas must have no effect on flex sizing, scroll height, or the two-column grid.
- Keep brand, workflow/form, and footer above the canvas. Keep the existing dark right promo, ticket, text, and buttons unchanged.
- Fade the canvas edges so particles recede naturally into the near-black background. Use soft neutral-gray dots, with only a sparse muted-lavender accent, for visible but restrained contrast.

## Motion and interaction

- Show a slowly rotating, breathing point-cloud sphere with a light upper tail, subtle twinkle, and a gentle halo.
- Mouse movement in the canvas region should softly displace nearby particles; pointer exit/blur should ease the interaction back to rest.
- Focusing a login control or submitting a form should produce a brief pulse, without intercepting the event.
- The existing promo “Pause Animations” control pauses this canvas too. Resume restarts animation.
- Honor `prefers-reduced-motion` by drawing a static frame with no pointer response. Stop requestAnimationFrame while the document is hidden, the canvas is offscreen, or motion is paused.

## Responsive and performance requirements

- Use the pane's measured size and `ResizeObserver`; cap device pixel ratio and point count for constrained hardware/save-data settings.
- Reduce backing resolution before reducing particle count when sustained slow frames are detected.
- The animation must remain local-only, have no network dependencies, and fail gracefully if a 2D canvas context is unavailable.
- On narrow/mobile viewports reduce the canvas height/opacity; preserve the existing auth layout and hide policy for the separate right promo.

## Acceptance

1. The existing login layout and auth controls remain in the same positions and work as before.
2. The left pane uses `#020205`; the login controls remain legible and keep their existing geometry. The point sphere is centered behind the controls, without blocking pointer/keyboard interaction.
3. Pointer, focus pulse, shared pause, visibility, resize, and reduced-motion behavior work as specified.
