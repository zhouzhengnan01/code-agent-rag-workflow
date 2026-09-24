# Project-flow layout

At the observed 1295px desktop viewport, Roboflow uses a narrow dark navigation rail and a flexible white content area. The confirmation card sits inside the conversation's message column rather than over the page. The asset picker overlays the page, centers a max-width ~720px panel near the top, and scrolls its contents independently. Starting a new model changes the main area to a split layout: chat on the left, creation pane on the right, with an asset tab above the pane.

Codezzn retains its existing static FastAPI workbench. The adaptation is an inline confirmation card, a centered project picker and a project-artifact management view; existing chat, streaming and tool-approval layouts remain intact.
