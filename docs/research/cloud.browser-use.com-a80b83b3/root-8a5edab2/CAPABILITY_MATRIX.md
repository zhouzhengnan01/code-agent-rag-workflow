# Public capability comparison

| Capability | Browser Use public reference | Codezzn status / intended mapping |
|---|---|---|
| Natural-language task loop | Agent repeatedly observes, acts, and verifies | Existing Codezzn agent tool loop; Browser Use-aligned behavior prompt |
| Navigation/search/back/wait | Public action set and MCP tools | Implemented with local Playwright tools and official MCP aliases |
| DOM state and indexed interaction | Page state with indexed interactive elements | Fresh snapshot-scoped indexes, accessible names/labels, values (secrets redacted), attributes, bounds, and stale-index invalidation |
| Extract/search page | Content extraction plus find/search actions | Implemented local DOM/text extraction, selector inspection, text search, and regex search |
| Multiple tabs | List, switch, close | Implemented tenant/thread-scoped tab list/open/switch/close actions with capacity limits |
| Browser vision | Public agent receives screenshot as a visual observation | Opt-in `include_screenshot` captures a bounded viewport JPEG and sends it to Codezzn's configured model as a visual observation; only use with image-capable model/provider. Screenshot bytes are excluded from durable tool-result cache, while normal task checkpoints may contain model input for resumability |
| Files | User task files and optional agent output files | Codezzn project Files/artifact tracking with bounded downloads, screenshots, and PDFs |
| Upload | File-based tasks / browser upload | Local workspace upload action gated by approval and file-size bound |
| Local browser policy | Allowed domains, sandboxing, profiles | HTTP(S) URL/redirect/subresource guard, private-network deny-by-default, optional admin domain allowlist, size/session caps; retain no-cloud design |
| Persistent profiles | Cloud profile can preserve cookies/local storage across sessions | Local thread context survives turns only while service process remains alive; persistent credentials/profile import not included |
| Run judge | Independent strict trajectory judge | Not implemented; `done` success plus explicit artifact/page verification only |
| Cost/spend control | Cloud usage limits/credits | Provider usage accounting exists; a per-run monetary cap/judge toggle is not equivalent and remains a gap |
| Hosted browser / anti-bot | Proprietary Browser Use Cloud infrastructure | Intentionally not replicated or called; local Chromium cannot guarantee anti-bot parity |
| Reusable session | Cloud session browser can run sequential tasks | Tenant/thread-scoped local context, tab/session caps, serialized operations, idle-session cleanup; profile persistence across process restarts is not included |
| Public MCP retry helper | `retry_with_browser_use_agent` starts/retries a higher-level Browser Use agent task | Codezzn's existing bounded autonomous tool loop is the high-level agent entry point; no nested Browser Use client or duplicate retry loop is introduced |
