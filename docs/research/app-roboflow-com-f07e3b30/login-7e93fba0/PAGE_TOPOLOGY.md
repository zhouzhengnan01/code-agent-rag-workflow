# Authentication page topology

Source: `https://app.roboflow.com/login`
Destination: `/login` and the matching `/register` authentication state.

1. `.auth-split`: full-viewport two-column grid, 50/50 on desktop.
2. `.auth-pane`: white left column with vertically distributed brand, centered authentication workflow and legal/footer links.
3. `.auth-workflow`: provider chooser or staged email/password form. Interaction model is click-driven.
4. `.auth-promo`: dark right column with grayscale video, scrim, animated 3D event ticket, event copy, CTA and animation toggle. Interaction model is time-driven plus click-to-pause.
5. At `max-width: 820px`, the promo column is hidden and the authentication column fills the viewport.

The Codezzn clone preserves the existing real GitHub OAuth and local email/password API. Google and SSO are visible provider components but report that the corresponding provider is not configured instead of simulating a successful login.
