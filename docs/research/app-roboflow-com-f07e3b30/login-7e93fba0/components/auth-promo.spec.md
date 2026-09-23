# AuthPromo Specification

## Overview
- Target files: `web/auth-promo.css`, `web/auth-promo.js`
- Host: `<aside id="authPromo" class="auth-promo-mount">`
- Screenshot: `docs/design-references/app-roboflow-com-f07e3b30/login-7e93fba0/codezzn-login-desktop.png`
- Interaction model: time-driven video/ticket plus click-driven pause toggle

## DOM Structure
Absolute `.auth-promo` contains looping video, two-layer scrim, ticket scene, event copy and motion toggle. Ticket uses front/back faces and compact decorative typography.

## Computed Styles
- Mount/background: `#121110`, relative, overflow hidden, full height.
- Promo: absolute inset 0, flex column, centered, gap `clamp(28px,5vh,64px)`, padding `clamp(24px,4vh,64px) clamp(32px,5vw,72px)`.
- Video: absolute inset 0, object-fit cover, `grayscale(1) contrast(1.12) brightness(.82)`.
- Scrim: radial dark vignette plus vertical dark gradient.
- Ticket: cream/lavender, clipped 14px corners, 3D perspective; rotates in 14s and floats in 6s.
- Copy title: cream, 28-40px responsive, weight 600, line-height 1, letter spacing -0.03em.
- CTA: lavender `#c29af6`, black text, square corners, 13px 32px padding; hover rises 2px with lavender shadow.
- Motion toggle: bottom-right pill, translucent black background, muted cream text, 10px.

## States & Behaviors
- Ticket `vis-spin` rotates Y 0→180→360 with slight X tilt.
- Ticket `vis-float` moves 0→-9px→0.
- Hover/focus pauses ticket animations.
- Motion toggle pauses/plays video and CSS animations and updates `aria-pressed` and visible label.
- `prefers-reduced-motion` starts paused and removes animation.

## Assets
- `/assets/sites/app-roboflow-com-f07e3b30/login-7e93fba0/cv-reel-poster.jpg`
- `/assets/sites/app-roboflow-com-f07e3b30/login-7e93fba0/cv-reel.mp4`

## Text Content
- Eyebrow: `CODEZZN PRESENTS`
- Title: `Build agents that work.`
- Meta: `Models, tools, knowledge and workflows — one local workspace.`
- CTA: `Open Workbench →`

## Responsive Behavior
- Desktop: right half of viewport.
- Below 820px: hidden.
- Ticket scale decreases at viewport heights 900/800/720/640.
