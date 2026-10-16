# File code preview and icons

Interaction model: click-to-open sibling tabs, not modal. Files remains a permanent first tab; opened file tabs can close independently. Preserve blank lines and raw copy text. No editing/execution of previewed source.

Live computed values from actual quicksort.py preview:
- white panel; no code container border or shadow.
- monospace: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, Courier New, monospace.
- 13px, line-height 19.5px, padding 12px, pre-wrap and break-words; code preview scrolls independently.
- Prism token classes visible: triple-quoted-string string, keyword, function, builtin, punctuation, operator, number, plain.
- plain/punctuation/operators/builtins rgb(57,58,52); keyword rgb(0,0,159); string/docstring rgb(227,17,108); function rgb(215,58,73); number rgb(54,172,170).
- Distinct comment colors required; do not treat a Python docstring as ordinary comment. Use real grammar highlighting, safely escaped unknown languages, capped file size and graceful fallback. Never execute source/HTML.
- Python language icon is actual 14x14 PNG, NOT a snake emoji. Source observed https://cloud.browser-use.com/_next/image?url=%2Ficons%2Flanguages%2Fpython.png&w=32&q=75
- Generic file Lucide 14px, color #78716c. Folder-open Lucide 16px, #f97316. Chevron-right 16px, #78716c, rotates 90deg when open. Download Lucide 14px, #78716c. Lucide source already installed (MIT).

Builder output: standalone global CodezznFileCode = {highlight(source,filename), languageFor(filename), icon(filenameOrKind)}; highlight returns escaped HTML with token classes; icon returns trusted static SVG or local img markup. No imported app state or backend calls. Add a node-testable export without requiring DOM. Vendored grammar license and fixed version must be retained. Tests: Python multiline/docstrings/comments/def/import/strings/numbers, JS, JSON, HTML/script source escaping, unknown/plaintext fallback, large-source safety, language/icon mapping. No executable code loaded from a CDN at runtime.

Main integration owns CSS, tabs and asynchronous lifecycle. Builder must not change workbench files. JS syntax + new node tests must pass. This existing vanilla JS component has no TS typechecker; unrelated workflow app retains tsc build.
