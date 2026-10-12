# Chat workbench implementation contract

The conversation submission contract was extended on 2026-10-12 to use durable session queues and interactions. See [conversation interactions](conversation-interactions.md) for the current ordinary-chat entry points; the existing synchronous/SSE turn APIs remain compatibility endpoints.

User request (2026-10-12): adapt Browser Use Cloud conversation layout to Codezzn's existing `/workbench.html#chat`, with an always-expanded desktop sidebar, chat history as a submenu of 对话调试, centered narrow conversation/composer, working attachments and model selection. Existing repository technology and functional backend take precedence over the clone skill's fresh Next.js template defaults.

Backend/frontend contract:

- `GET /api/chat/models` → `{data: [{provider_id, provider_name, model, label}]}` with enabled configured providers/models only; no credentials.
- `POST /api/chat/attachments` multipart `file` → public metadata `{id, name, size, mime_type, kind, download_url}`; tenant scoped. Support bounded text/code documents, PDF/DOCX and images if model adapters can consume them correctly. Reject unsupported/binary/oversized input explicitly.
- `GET /api/chat/attachments/{id}/download` → authenticated tenant-scoped file.
- `PATCH /api/threads/{id}` accepts `model_override: {provider_id, model}` or `{}` to inherit Agent settings. Returned thread exposes `model_override` and persists it independently of the Agent resource. Explicit selection must override automatic routing/fallback for this thread.
- Turn bodies (sync and SSE) accept `attachment_ids: [id]`; attachment metadata persists in user-message `meta.attachments` and is supplied to the actual model. Text attachment contents and images must remain available during later turns and approval resume. Validate tenant, limits and IDs before adding messages or launching a turn.
- Preserve existing Agent skills/MCP capability policies, project confirmation, streaming, stop, fork, archive and files panel. Do not introduce fake cost or unsupported control options.
- Tests must cover configured model validation, override precedence without changing Agent resources, attachment upload/download, actual prompt/model adapter inputs, persistence, limits and tenant isolation.

Ownership: backend specialist edits backend/app and new backend tests; primary agent owns web/workbench.js and workbench markup/integration; styling specialist owns new chat-workbench.css and its research/spec updates. Shared files must be coordinated.
