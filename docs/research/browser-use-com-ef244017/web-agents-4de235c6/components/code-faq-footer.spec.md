# Code, CTA, FAQ, and Footer Specification

## Overview
- **Target files:** `web/sites/browser-use-com-ef244017/web-agents-4de235c6/code-footer.css` and the scoped page JS
- **Interaction model:** click/keyboard tabs, copy, CTA, FAQ disclosures, footer accordions

## Code example section
Title `One sentence in, structured data out.`; paragraph explains there is no flow/selectors to build and the agent handles clicking, scrolling, logins, retries; `Read the quickstart`; tab group CURL/PYTHON/NODE; copy button and code panel. Desktop two-column grid 0.85fr/1.15fr, 48px gap; H2 52px/55.12px; code is Geist Mono 13px/18.85px and horizontal overflow safe.

Tabs switch the visible snippet and selected state; CURL is default. Copy copies only the active snippet and sets an accessible “Copied” status. Use static snippets with environment-variable placeholders; never ship a real key.

## Closing CTA
Text `Give your product an agent.`; primary `Run your first agent` orange pill (44px high, 24px horizontal padding). Section 1200px max-width, desktop title 52px; CTA goes to Codezzn login.

## FAQ
Six questions: What is a web agent?; Which model does it use?; How accurate is it?; Do agents get blocked?; What does a run cost?; How do I get the results? First opens initially. Max-width 768px; question text 15px/24px (18px lead at wider widths), 20px vertical padding; chevron 16px. Click/keyboard toggles answer and `aria-expanded`; chevron rotates 180° over 300ms.

## Footer and consent
Footer has Product, Resources, Solutions, Showcase, Company, Connect groups. Desktop is a grid; mobile is six expandable disclosure rows. Keep the `View as Markdown` and status/product-map footer treatment, but route non-GitHub links through Codezzn login. GitHub points to the Codezzn repository.

Cookie banner appears on first visit, fixed at the lower edge; Reject/Accept persist choice locally and dismiss. No external analytics or third-party consent manager.
