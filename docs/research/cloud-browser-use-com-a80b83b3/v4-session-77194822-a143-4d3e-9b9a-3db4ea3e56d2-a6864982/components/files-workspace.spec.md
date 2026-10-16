# Files workspace: tree, tabs, splitter

Interaction: click Files -> folder/file tree; click a file -> same panel, new sibling tab; repeated click reuses it; switch/close tabs without losing Files tree expansion or scroll. Closing active file chooses adjacent tab, then Files. Switching threads clears private previews and aborts pending requests. Switching projects must not reuse another project's file content. Refresh retains selected tab when same file/version; actual changed file invalidates preview. Download never opens a new window.

Live computed styles:
- Tree font system ui-sans-serif, 13px / 19.5px; rows 34px high, padding 4px 8px, gap 4px, corner 4px. Container padding 8px; nested groups indentation and pale #e7e5e4 border.
- Text #0c0a09, muted #78716c; folder #f97316, same icons as preview spec.
- Tab header padding 4px; tabs gap 4px, selected background #f5f5f4, corner 8px, 13px text, file name max 200px/truncate. Button padding 4px 4px 4px 10px, icon/name gap 6px, tab height about 28px.
- Files (N) first permanent tab; Download all lives in tree-only toolbar. Right-side file content replaces tree, not overlay.
- Separator role separator, aria-orientation vertical, aria-label Resize chat and panel, aria-valuenow chat percentage, aria min 28 max 96. 12px pointer hit area, transparent line -> blue on hover/focus, 150ms color transition. ArrowRight increments chat width 2 percentage points; ArrowLeft decreases. Implement pointer drag with capture, robust pointercancel, cleanup on view replacement, and minimum usable panel widths. Persist layout only (no file content) in localStorage. Chat and Files are sibling columns.

In scope real auth-backed project files and existing conversation outputs. Source code preview inert, SVG/HTML never injected as DOM. Support code/text/images and safe fallback for binary/large files; errors remain in panel with retry and download. Preserve existing download/ownership checks, avoid leaks or wrong-tab updates from slow requests.

Desktop target preserved; no mobile/tablet redesign requested. All unrelated routes/backgrounds unchanged. Screenshots and browser tests must cover expanded folders, two open file tabs, active source preview, resize/keyboard, error/retry, malicious text, stale cross-thread fetch.
