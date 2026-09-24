# Project-flow interaction patterns

- A user asks for a model. The Agent explains a material consequence before creation, then offers explicit affirmative and negative choices plus a free-text alternative. No asset is created before consent.
- Selecting Open Asset opens a searchable, tabbed picker; closing it returns to the unchanged conversation.
- Selecting Create a Model opens a draft form alongside chat, with an inactive Create Model action until required fields are supplied.
- Codezzn translates these patterns to a two-stage inline decision: create/select/no project, then save/not save the requested deliverable. Choosing an existing project uses the centered picker. The user's decision is attached to the turn; tool-level write approval remains separate.
- An artifact keeps the project ID chosen when it was produced, even if the conversation later switches active projects.
- The live Roboflow confirmation is a compact inline card (448px max-width) with a light gray question header and selectable rows; the asset picker is a separate searchable dialog. Codezzn mirrors this distinction.
- Codezzn now shows an inline capability explanation for artifact requests when the selected agent is read-only, instead of silently answering with an unsaved code block. Saving remains unavailable until the user configures file tools and workspace-write mode; the server independently rejects an invalid save intent.
- After an approved save, the persisted conversation shows a selected-choice summary and a file card with preview/download actions. The project file remains in the tenant-local `projects/<project_id>/` directory.
- The Agent can also call the generic `ask_user` tool for a material choice: this creates a persisted, resumable checkpoint and renders the same compact option card with free-text input. Auto-approval does not answer on the user's behalf.
- Project files are shared only with the sandbox executor group, so isolated `run_shell`/`run_tests` can inspect them without using world-readable file permissions.
