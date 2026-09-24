# Observed design tokens

Values below are from the authenticated Agent landing page's computed styles where specified. The rest are layout observations from 1440×900 and 390×844 screenshots.

- Body font: `Inter, sans-serif`; base 16px.
- Primary heading: 30px / 36px, weight 600, `rgb(17,24,39)`.
- White card: `rgb(255,255,255)`.
- Composer border: `0.8px solid rgb(221,214,254)`; radius 8px; inner padding 16px; desktop width 736px.
- Pills: 32px high, white, `0.8px solid rgb(229,231,235)`, 9999px radius, 12px medium text.
- Send button: 32×32px, `rgb(109,40,217)`, circular.
- Sidebar: dark charcoal; collapsed ~60px, expanded ~155px.
- Mobile top bar: ~56px.
- Home backdrop: soft white/lavender radial wash.

## Project and confirmation flow (observed 2026-09-23)

- Confirmation choices appear in the chat stream, not a blocking modal. The card is white, approximately 694px wide in the observed desktop conversation, with a thin lavender border and subtle rounding.
- Each answer row is a full-width button with 8px padding and gap, a compact gray numbered icon frame, 13px medium title and 12px muted description; hovering changes the row to a very light gray.
- The optional free-text answer row uses a pencil icon, a borderless input, and a small send button.
- The existing-asset picker is a centered white modal approximately 720px wide with an 8px radius, shadow, and a 25% black backdrop. Its header uses 24px horizontal padding, a folder icon, search field and close button.
- Picker tabs use a 2px purple bottom border for the active state; asset rows pair a 48px thumbnail/icon with name and muted secondary metadata.
