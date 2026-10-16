# Files panel incremental reconstruction

- Source: https://cloud.browser-use.com/v4/session/77194822-a143-4d3e-9b9a-3db4ea3e56d2
- Destination: existing `/workbench.html#chat`, repository D:/code-agent-rag-workflow.
- Explicitly requested update to the existing Files panel, not a new route or app.
- Preserve native JS/FastAPI app and all authentication, project ownership, download endpoints, chat background and prior changes. No Next.js scaffold replacement.
- Source origin and pathname namespaces already exist; add only Files-specific specs/QA without replacing earlier research.
- Main: web/workbench.js + scoped web/chat-workbench.css integration; tree/tabs/splitter/lifetime handling.
- Isolated builder: new web/file-code-viewer.js + local vendored Prism runtime/language grammars/license + tests/test_file_code_viewer.cjs. No workbench modifications by builder.
- Asset: local Python language icon from the actual observed Browser Use public image URL; no user files downloaded from the cloud reference.
- Verify: JS checks, node tests, real isolated desktop browser behavior and screenshots, existing workflow TypeScript/Vite build, server regression. Desktop only per user's established scope; no global layout redesign.

## Live evidence

Native AX wrapper was unreliable/slow; direct documented browser.tabs.get + Playwright interface works. Successfully opened quicksort.py, switched back to Files, inspected computed styles. Separator ArrowRight changed 42 to 44 (% chat). Existing screenshot supplied by user is supplementary, not the only evidence.
