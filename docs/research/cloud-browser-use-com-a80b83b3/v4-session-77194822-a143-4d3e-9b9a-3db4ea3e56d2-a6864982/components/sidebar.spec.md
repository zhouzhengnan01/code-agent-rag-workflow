# PersistentSidebar specification
Target: web/chat-workbench.css sidebar rules; HTML/functions owned by primary in web/workbench.js.
Source measured width239.2px + border0.8px =240px; background white, border rgb(231,229,228), labels13px; groups12px/16px semibold muted rgb(120,113,108); rows32px,radius6px,8px horizontal padding.
Chosen layout: .studio-shell grid240px minmax(0,1fr), .workspace-rail white full-height flex column; .primary-nav flex1 overflow-y:auto; brand top52px; footer anchored bottom. .nav-icon16px; .nav-label alwaysvisible; .nav-short/rail-hover/.rail-expand hidden. Keep Codezzn violet logo.
History DOM: .chat-history-submenu contains .history-scope (active/archive), .session-search, .session-list, .session-item/.session-open/.session-more; max-height220px internal list scrolling; .session-name ellipsis; active tinted neutral/violet; new thread button.
Interaction: click to expand/collapse chat submenu via .nav-chat-toggle; no mouseenter widths. History uses existing select/fork/rename/archive menus. Separate .chat-history-submenu[hidden] must stay hidden.
Desktop width240 persistent. At <=700px sidebar an explicit overlay drawer via body.rail-open; mobile menu button visible and scrim; no shrinking icon rail/hover. <=1000px width220 acceptable adapted density.
Assets: existing Codezzn SVG and existing navIcons; no external avatars/logos.
Accessibility: navigation labels alwaysvisible, active aria-current, button-expanded, keyboard focus, reduced-motion rule.
