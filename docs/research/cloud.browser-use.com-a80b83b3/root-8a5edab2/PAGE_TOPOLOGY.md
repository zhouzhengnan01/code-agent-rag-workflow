# Page / agent topology

This is a capability-flow topology inferred from public docs and user-provided screenshots, not a live page DOM inspection.

1. **Agent task composer** — user describes a task and may add files; chooses model/reasoning and optional run settings.
2. **Run/session settings** — public Cloud guidance describes one browser per session, one active agent per session, and reusable session context within the session lifetime.
3. **Agent loop** — each step observes page state (DOM and screenshot in public agent behavior), selects tools, executes, checks results, and eventually returns success or failure.
4. **Session browser** — browser navigation and tab state are shared across sequential tasks in one session; cloud browser profiles are an explicit persistence feature.
5. **Run result** — final text plus optional generated/downloaded files; Cloud's documented flow can use a separate judge on the trajectory.
6. **Files/recording panel** — user's screenshots show task messages and a right-side file list; Codezzn already has a project Files pane and browser-produced file artifacts.

## Codezzn mapping

- Existing conversation turn + configured agent → task composer/run loop.
- Existing thread-scoped local Playwright context → local browser session; context is process-memory-only today, unlike Cloud profiles.
- `tool_started` / `tool_completed` events → action timeline.
- Project artifact table + Files pane → downloadable project files.
- `done` tool + artifact verification → completion declaration; it is not Browser Use Cloud's independent judge.

