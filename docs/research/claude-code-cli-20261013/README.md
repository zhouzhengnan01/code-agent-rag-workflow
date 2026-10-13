# Windows CLI reference inspection

Date: 2026-10-13. Target: user-selected installed Claude Code executable.

- REA open_binary identified x86_64 PE, SHA-256 `fcfe90297861b1bcfa581d7db645ec8a71984baed3b1c44d28032650baa2617c`.
- Normal shell runtime probes returned exit 0 for version, top-level help, auth help, agents help, MCP help and project help. Version: Claude Code 2.1.140. Complete output is retained in evidence.json.
- Observed public interface: interactive by default; -p print; text/JSON/stream-JSON outputs; continue/resume/fork; model and agent selection; auth lifecycle; named sessions; MCP and plugin management options.
- Help declarations establish the interface, not successful execution of every declared feature. No paid inference prompt, sign-in, MCP launch, permission bypass, updater or private credential inspection was performed on Claude Code.
- REA native decompilation unavailable: Ghidra is not configured. REA native Windows PTY capture is unsupported by this adapter. PE resource inventory rejected the 227 MB target against its 64 MB input limit. These are explicit coverage limits; no engines or unrelated runtime prerequisites were installed.
- Codezzn implementation is original code using existing tenant-scoped server APIs, not recovered Claude source or private prompts. Backend model quality and proprietary/cloud-only features are not claimed equivalent.
- Confirmed scope: the user selected a Windows terminal client operating existing Codezzn server projects and Docker sandbox. The working directory identifies saved sessions only; no Windows host execution authority is added.
