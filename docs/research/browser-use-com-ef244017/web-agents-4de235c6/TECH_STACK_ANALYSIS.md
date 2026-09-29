# Source and destination stack

- Source site: Next.js App Router, Tailwind utility classes, Geist and Geist Mono self-hosted WOFF2, inline SVG for the benchmark chart and Lucide-style icons. No video was present. Hero art is a Next image optimizer WebP derived from `agents-be1dd941.jpg`.
- Local destination: FastAPI 0.115.14 serving static HTML, CSS, and JavaScript. There is no package.json/React/Next/TypeScript app. Existing route and auth middleware are production-relevant and must be retained.
- Chosen equivalent: a `web/home.html` page, page-scoped CSS and JS in the unique `web/sites/...` namespace, binary assets in `public/sites/...`, plus a public StaticFiles mount for that namespace only. No source-site runtime JavaScript, analytics, API calls, or authentication service are copied.
- Local behavior is intentionally remapped: login/start actions go to Codezzn auth; GitHub actions go to the Codezzn repository; all tabs, disclosures, copy, menu, consent, and scroll reveals stay local.
