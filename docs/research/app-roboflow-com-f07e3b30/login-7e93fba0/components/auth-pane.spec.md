# AuthPane Specification

## Overview
- Target files: `web/login.html`, `web/register.html`, `web/auth.css`, `web/auth.js`
- Source: `https://app.roboflow.com/login`
- Screenshot: `docs/design-references/app-roboflow-com-f07e3b30/login-7e93fba0/codezzn-login-desktop.png`
- Interaction model: click-driven staged authentication

## DOM Structure
White `.auth-pane` contains brand, `.auth-workflow`, legal copy and a footer. Initial workflow contains heading and provider list. Email state replaces providers with labeled fields and Next/Cancel controls.

## Computed Styles
- Desktop split: `display:grid; grid-template-columns:1fr 1fr; height:100%`
- Pane: white, flex column, `justify-content:space-between`, padding `clamp(28px,5.5vh,48px) clamp(32px,6vw,88px)`
- Content width: `clamp(280px,32vw,400px)`
- Ink: `#121110`; accent: `#c29af6`; hover: `#f5f4f1`; field: `#faf9f7`
- Heading: `clamp(24px,1.1vw + 18.4px,30px)`, weight 600, line-height 1.2, letter spacing -0.02em
- Provider controls: full width, approximately 44px high, 8px radius, 1px `rgba(18,17,16,.18)` border, 15px/500 text
- Last-used badge: black, white 10px/500 text, pill radius, padding 2px 8px, right 12px, translated -50% vertically
- Legal text: 12px, muted ink, links underlined
- Footer: flex space-between, muted 11-12px text

## States & Behaviors
- Provider initial state: Google/GitHub/Email/SSO.
- GitHub navigates to `/api/auth/github/start?next=...`.
- Email opens the first step; Next validates email then reveals password and mode-specific fields.
- Cancel returns to the provider list.
- Login sends `/api/auth/login`; registration sends `/api/auth/register`.
- Google and SSO expose an inline unconfigured message.
- Hover provider surface: white to `#f5f4f1`, 150ms.
- Focus-visible: purple ring. Error fields use red border/ring.

## Responsive Behavior
- Desktop: left half of viewport.
- At 820px and below: single column, promo hidden, max content width 420px, horizontal padding `clamp(20px,5vw,40px)`.

## Text Content
- Heading: `Sign In or Sign Up`
- Providers: `Continue with Google`, `Continue with Github`, `Continue with Email`, `Continue with SSO`
- Legal: `By continuing, you are agreeing to our Terms of Service and Privacy Policy.`
- Footer uses Codezzn identity while retaining the source layout.
