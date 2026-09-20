# Landing-page behavior audit

- Sidebar: icon-only by default at desktop, expandable by click to reveal names. No scroll-driven transition observed.
- Composer: text entry area; bottom-left add/agent controls, bottom-right history/send controls. Empty message keeps send unavailable.
- Suggestion pills: click actions.
- Lower dashboard: desktop shows Examples and Recent simultaneously; at 390px it shows Conversations and Examples as tabs.
- Scrolling: the main page scrolls naturally; the sidebar remains fixed to viewport height. No section snap or sticky-state transition observed.
- Hover: source controls use subtle neutral background/border transitions. Codezzn follows the same pattern, adapted to its own actions.
- Roboflow's animated placeholder text is intentionally not copied; it would interfere with the Codezzn user's own draft input.
