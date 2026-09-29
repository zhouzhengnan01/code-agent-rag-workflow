# Clone output plan

- Source URL: `https://browser-use.com/web-agents`
- Normalized origin: `https://browser-use.com`
- Site key: `browser-use-com-ef244017` (SHA-256 origin prefix)
- Normalized path: `/web-agents`
- Page key: `web-agents-4de235c6` (SHA-256 path prefix)
- App root: repository root (`D:\code-agent-rag-workflow`)
- Destination route: `/` → `web/home.html` (public pre-login landing page)
- Existing route preservation: `/workbench.html`, `/login`, `/register` remain intact; unauthenticated `/workbench.html` still redirects to `/login`.
- Authorized route change: `/` currently aliases the protected workbench. This request explicitly makes it the public landing page; only `/` changes behavior.
- Namespaced research: `docs/research/browser-use-com-ef244017/web-agents-4de235c6/`
- Namespaced screenshots: `docs/design-references/browser-use-com-ef244017/web-agents-4de235c6/`
- Namespaced components (static-app equivalent): `web/sites/browser-use-com-ef244017/web-agents-4de235c6/`
- Namespaced assets: `public/sites/browser-use-com-ef244017/web-agents-4de235c6/`
- Route integration: keep Codezzn authentication and API behavior; mount only public static clone assets; do not add Browser Use analytics or third-party scripts.
- Navigation wiring: login/start CTAs and the remaining non-GitHub external product links route to Codezzn login (`/login?next=/workbench.html`). GitHub links route to `https://github.com/zhouzhengnan01/code-agent-rag-workflow` in a new tab. Code-example tabs, copy, FAQ, dropdown, mobile menu, and cookie controls retain their local interaction.

## Stack adaptation

This repository is a FastAPI app serving static HTML/CSS/JavaScript, not the Next.js + shadcn + Tailwind starter assumed by the skill. The page will therefore use a route-scoped static implementation under `web/`, namespaced assets under `public/sites/`, and a narrowly scoped FastAPI static mount. No new frontend framework is introduced. `npm run build`/`npx tsc` are not applicable because this repository has no `package.json` or TypeScript application.
