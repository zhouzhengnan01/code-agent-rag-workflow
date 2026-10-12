# Adapted conversation topology
Source: Browser Use session route listed in OUTPUT_PLAN.json; desktop measured at 1440x960.
1. Permanent left sidebar, measured ~240px, white, menu groups and history; replace Codezzn hover expansion. History is a child of 对话调试 per explicit user request.
2. Slim header: source 40.8px / 6px 16px padding; adapt existing workbench command bar to 48px, current thread name, files toggle and Agent selector.
3. Scrollable conversation column: centered, max-width 640px, white, user messages on right, assistant text and collapsed work trace on left.
4. Docked composer: exact source width640px, height121.6px empty, radius16px, border rgb(231,229,228), input15px/24.375px, input padding10px 8px. Footer attachment32px, model control36px/13px.
5. Optional file panel: user-controlled, starts closed, consumes width only when open; no second conversation history pane.
6. Keep project confirmation/approval/tool execution/knowledge sources and saved assets functional. Project and capabilities become composer context controls.
Interactions: click for submenu/model/files; native scroll for messages; streaming updates/stop for turns; no hover-driven navigation.
