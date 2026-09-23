# Authentication behaviors

- Initial state shows four full-width provider controls: Google, GitHub, Email and SSO.
- GitHub is the last-used provider and displays a black `Last Used` badge above its right edge.
- Email and SSO open a staged email form with floating `Email` label, purple `Next` button and white `Cancel` button.
- Codezzn continues from the staged email view into its real password login or registration form.
- Provider buttons use a 150ms background/border transition; hover changes the white surface to `#f5f4f1`.
- Form feedback is inline and announced with `aria-live=polite`; pending buttons show a spinner and are disabled.
- Promo video is grayscale/contrast filtered behind a dark radial and vertical scrim.
- Ticket rotates and floats continuously. Hover/focus pauses the ticket.
- `Pause Animations` changes to `Play Animations`, toggles `aria-pressed`, pauses the video and pauses ticket animations.
- Reduced-motion mode removes promo and ticket animation.
- Under 820px, the promo panel is hidden and the left workflow is centered.
- A successful local or GitHub login redirects to the sanitized `next` route, defaulting to `/workbench.html`.
