# Codezzn

Codezzn 是一个本地优先、可 Docker 部署的智能体开发平台。它参考 Codex 的 Thread/Turn/Item、`SKILL.md` 与 MCP 设计，但拥有独立实现和面向管理场景的 Web Workbench。

## 已实现

- 智能体：通用/编码/审查/研究/运维角色模板；系统提示词、技能/知识库/MCP/内置工具组合；逐工具 `allow`/`ask`/`deny` 策略
- 模型接入：OpenAI-compatible Chat Completions 与原生 Responses API；支持持久 `previous_response_id`、reasoning effort、自动/本地上下文压缩、并行与异步函数工具声明、动态路由和故障回退
- 技能：在线创建、启停、编辑、删除；安全导入单文件 `SKILL.md` 或带 `scripts/`、`assets/`、`references/`、`skill.json` 的 ZIP 包，并校验 SemVer、依赖声明和内容完整性
- MCP：stdio 与 Streamable HTTP JSON-RPC transport，支持版本/能力协商、Session ID、JSON/SSE、工具、资源/资源模板、提示词、补全、订阅、日志级别、分页，以及 stdio roots 反向请求
- RAG 知识库：可选择本地 SQLite + Milvus 混合检索，或通过独立 RAGFlow 服务使用复杂文档解析、全文/向量混合召回、重排与来源引用；旧知识库保持本地后端，不会被默认配置自动迁移
- 工作流：input、prompt、agent、knowledge、mcp、condition、parallel、output 节点；并行就绪队列、条件边、节点超时/重试、检查点恢复、后台运行和节点 trace
- Workbench：仪表盘、对话、角色/智能体团队、任务队列、长期记忆、各资源管理、工作流 JSON 设计器、设置
- 工具执行：知识检索、代码搜索、AST/符号/引用/调用图/依赖图、LSP 3.18、目录读取、原子文件读写、测试、完整 Git 远端/merge 工作流、GitHub PR/CI/Review、Playwright 浏览器/DOM/截图；写操作受沙箱、审批与工具策略共同控制
- 后台任务：SQLite 持久队列、并发 worker、失败退避重试、取消、事件历史、进程重启后恢复未完成任务；智能体和工作流均可后台执行
- 多智能体：可配置团队、协调智能体、成员白名单、并发和深度限制；主智能体通过 `delegate_task` 并行委派并用 `task_status` 汇总
- 长期记忆：用户、项目和线程三级作用域，哈希向量+词法混合检索、可信度、冲突待确认、确认/拒绝、过期淘汰和自动经验沉淀
- 任务隔离与恢复：Git 工作区为每个任务/会话创建独立 worktree；模型轮次、Responses ID 和工具结果持续检查点化，进程重启自动续跑，副作用工具不会在状态不明时自动重放
- Execution safety: container-backed `read-only` / `workspace-write` Shell and read-only Git; `danger-full-access` Shell is rejected. Thread locks, approval records, atomic file writes, and backups remain unchanged.
- CLI：`python -m backend.app.cli exec` 支持非交互执行、stdin 和 JSONL 事件输出
- 持久化：SQLite WAL 保存业务数据，Milvus 保存知识向量，记录线程消息、知识来源、工具事件、token usage 与工作流运行记录
- 部署：Dockerfile、Compose healthcheck、持久化数据卷、可选 API 管理密钥

## 启动

```powershell
cd D:\code-agent-rag-workflow
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
```

打开 <http://127.0.0.1:8080/workbench.html>。首次启动会生成一个默认 OpenAI-compatible 提供方和默认智能体；请先在“模型接入”中填入有效 API Key，或将 Base URL 改为你的 Ollama、vLLM、LM Studio、OneAPI 等兼容端点。

Windows Docker Desktop 使用 bind mount 时，宿主机文件权限可能与容器内非 root UID 不一致。Compose 默认使用 `CODEZZN_UID=0`、`CODEZZN_GID=0` 保证本地启动可写；Linux 主机可在 `.env` 中改为 `./data` 和 `./workspace` 所属用户的 UID/GID。

### 可选 RAGFlow 检索后端

RAGFlow 必须作为独立服务部署，不要把其源码或 Compose 服务直接合并到 Codezzn 主容器。Codezzn 通过 RAGFlow `/api/v1` REST API 接入。将以下设置添加到现有 `.env`；`CODEZZN_RAGFLOW_URL` 可以是服务根地址或已经带 `/api/v1` 的地址：

```env
CODEZZN_KNOWLEDGE_BACKEND=local
CODEZZN_RAGFLOW_URL=http://host.docker.internal:9380
CODEZZN_RAGFLOW_API_KEY=replace-with-ragflow-api-key
CODEZZN_RAGFLOW_TIMEOUT=120
```

`CODEZZN_KNOWLEDGE_BACKEND` 只决定新建知识库的默认值。已有且未保存 `backend` 字段的知识库始终按 `local` 处理，避免环境变量导致静默迁移。Workbench 新建 RAGFlow 知识库后，可以填写现有数据集 ID，也可以先保存，再点击“创建数据集”。上传到 RAGFlow 后返回 `processing`；在“文档状态”中等待 `DONE` 再测试检索。

对照评测端点：

```http
POST /api/knowledge/evaluate
```

请求中提供 `local_knowledge_ids`、`ragflow_knowledge_ids`、`top_k` 和带 `query`/`expected_sources` 的 `cases`。结果包含 Hit@K、MRR、来源 Recall@K 与平均延迟。它是迁移验收指标，不等同于生成回答的 Faithfulness 或 Chunk 级完整评测。

查看状态：

```powershell
docker compose ps
docker compose logs -f codezzn
Invoke-RestMethod http://localhost:8080/healthz
```

## Container sandbox deployment

Shell and Git tools require the broker overlay below. Starting only `docker-compose.yml` still runs the application, but unavailable sandbox commands fail closed: there is no host shell, Git, or patch subprocess fallback.

### Build and start

Use Docker Engine with Linux containers (or Docker Desktop in Linux-container mode). Keep an existing `.env`; **do not overwrite it** with `.env.example`. For a fresh checkout, use the guarded copy above. Edit the existing file to set a strong, random `CODEZZN_SANDBOX_TOKEN` and a separate nonempty `CODEZZN_ADMIN_KEY`. Generate each secret locally with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. The overlay refuses to start with a missing/empty broker token. Do not store secrets under `workspace/`.

```sh
docker build -f Dockerfile.sandbox -t codezzn-sandbox:local .
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml up -d --build
```

The sandbox image contains Python 3.12, Git, patch, ripgrep, and CA certificates, with Python standard-library tests available by default. It contains no Node.js or application/model dependencies. To include pinned pytest for user tests, build it instead with:

```sh
docker build -f Dockerfile.sandbox --build-arg INSTALL_PYTEST=true -t codezzn-sandbox:local .
```

Install any other trusted dependencies into a custom image at build time and set `CODEZZN_SANDBOX_IMAGE` before restarting the overlay. Runtime network access is fixed off, so runtime package installation is not supported.

### Trust and isolation boundaries

- The broker runs as **root (`0:0`) with the Docker Unix socket: this is host-admin-equivalent access**. It is a trusted control plane, not a multitenant security boundary. Use a dedicated trusted machine/VM; do not expose the broker or its token to untrusted users. Read-only root filesystems and dropped capabilities do not remove the socket's host-admin authority.
- `sandbox-broker` reuses the main application image built by `Dockerfile`, running `python -m backend.app.sandbox_broker`. It has a read-only root filesystem, temporary `/tmp`, and persistent named `sandbox-state` volume mounted at `/state` for `/state/tasks.db`.
- Only the broker mounts `/var/run/docker.sock`. **Never mount the socket in the main service or execution containers**, and do not configure a remote Docker TCP endpoint. The broker receives only explicitly listed control settings, not the application's `.env` or provider keys.
- The broker connects only to the isolated, internal `sandbox-control` network and has no published port. The main service joins both `default` and `sandbox-control`. `/health` and `/tasks` on broker port 8090 require `Authorization: Bearer <CODEZZN_SANDBOX_TOKEN>`.
- The broker resolves the `codezzn` container's `/workspace` mount using Docker inspect; it does not guess a host workspace path. Keep `CODEZZN_SANDBOX_WORKSPACE_CONTAINER` aligned with the main container name when customizing deployment. Do not mount the workspace into the broker itself.
- Each Shell or Git tool invocation gets a **separate execution container**, not one container for a whole Turn. Execution runs as UID/GID `10001:10001` in the task worktree, without inherited application secrets or Docker socket. Network is off except explicitly approved Git remote calls when `CODEZZN_SANDBOX_GIT_NETWORK=true`. Defaults are 1 CPU, 512 MiB memory, 64 PIDs, and a 60-second timeout.
- Only Shell/Git execution is container-sandboxed. MCP/LSP servers, Playwright, and native Python file tools are **out of scope** and execute in the main application's trust boundary. Browser sessions can reach networks available to the main container; enable them only for trusted agents.
- When `/workspace` is a Git work tree, each persistent task or conversation receives an independent branch and `git worktree` below `.codezzn-worktrees/`. A non-Git workspace cannot provide branch isolation and falls back to the base workspace.

### Tool permissions and Linux bind mounts

`run_shell` requires both `allow_shell=true` and approval/tool-policy permission, in either `read-only` or `workspace-write`. Read-only Shell **does not require enabling `danger-full-access`**; that mode is rejected rather than executed on the host. Git status/diff/log/review always use `read-only`, disable hooks and fsmonitor, and disable external diffs/text conversion. Clone/fetch/push additionally require `CODEZZN_SANDBOX_GIT_NETWORK=true` and approval. Review refs reject option-like or unsupported revision input. `apply_patch` supports exact `old`/`new` replacement and unified diff; both create recoverable backups and remain subject to write approval.

On Linux, the execution UID/GID is always `10001:10001`, independent of `CODEZZN_UID`/`CODEZZN_GID` for the main service. Provision `./workspace` ownership, shared group permissions, or ACLs so that both identities can traverse/read it, and can write when workspace-write is intended. An empty root-owned bind directory may otherwise produce `Permission denied`. Aligning the main user and workspace owner to UID/GID 10001 is one option; keep `./data` writable by the main user as well. Do not solve this by enabling full-access mode, making the workspace world-writable, or running execution containers as root. Read-only mode still needs filesystem read/traverse permissions and rejects workspace writes; tests that emit caches must use `/tmp` or workspace-write.

### Health and troubleshooting

Application liveness alone does not prove the sandbox is healthy. In a shell with `CODEZZN_ADMIN_KEY` set to the same value as `.env`, check both:

```sh
curl --fail http://127.0.0.1:8080/healthz
curl --fail -H "X-Codezzn-Key: ${CODEZZN_ADMIN_KEY}" http://127.0.0.1:8080/api/sandbox/status
# With an admin key configured, the following must return HTTP 401:
curl -i http://127.0.0.1:8080/api/sandbox/status
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml ps
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml logs --tail=100 sandbox-broker
```

On PowerShell use `curl.exe` and `$env:CODEZZN_ADMIN_KEY` in the header instead. Compose reads `.env`, but does not export its values to your shell. Adjust the host port if `CODEZZN_PORT` differs from 8080.

`GET /api/sandbox/status` uses the application's admin authentication and delegates broker health/task states to the sandbox client; without a configured admin key it returns 503 instead of exposing task state anonymously. Broker unavailability returns 503. For a direct internal broker check without publishing its port, run:

```sh
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml exec -T sandbox-broker python -c "import os, urllib.request; h={'Authorization': 'Bearer '+os.environ['CODEZZN_SANDBOX_TOKEN']}; print(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8090/health', headers=h)).read().decode()); print(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8090/tasks', headers=h)).read().decode())"
```

Inspect the returned task states and `cleanup_pending` flags together with broker logs. Missing image, socket access, workspace mount/permissions, or mismatched tokens must be fixed at deployment; never bypass them with host execution. The client raises `RuntimeError` for unavailable/failed/timed-out execution and cancels the remote task when its awaiting coroutine is cancelled. A running streamed Turn can be cancelled from the conversation stop button; a persistent background task can be cancelled from “后台任务”.

## 容器沙箱验收（2026-09-14）

本次采用“每次 Shell/Git 工具调用一个容器”，不是整个对话共用容器。网络固定关闭、UID/GID 固定为 10001:10001；只挂载工作区，根文件系统只读，临时目录 64 MiB，默认 1 CPU / 512 MiB / 64 PID / 60 秒。执行容器不挂 Docker socket、应用数据库，不传模型密钥。每次结束强制删除容器；失败保留 cleanup_pending 并阻止新任务，后台每 2 秒重试。服务重启把遗留 active 任务标记 interrupted 并回收，仅处理本实例标签，不进行全局 prune。

容器 PID 1 另有独立超时看门狗：即使 broker 停止，命令仍会在截止时间退出；Docker 不可用时不能承诺立即删除，恢复服务后重试回收。超时退出码 124 为保留值。

已在本机 Docker Desktop Linux 引擎验证：非 root、只读写入拒绝、网络拒绝、无 socket/业务数据/密钥、工作区写入、CPU/内存/PID 配置、实际 OOM 和 PID 限制、取消、超时杀子进程、独立看门狗、遗留容器恢复。没有替换现有业务容器，也没有使用业务 data/workspace 测试。

离线单元测试（仅 Python 标准库）：

```powershell
python -m unittest discover -s tests -p test_sandbox.py -v
```

应用镜像内完整回归（需要已构建镜像）：

```powershell
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml run --rm --no-deps codezzn python -m pytest -q -p no:cacheprovider tests/test_core.py tests/test_sandbox.py tests/test_sandbox_client.py
```

真实隔离验收使用专用临时控制容器、只读源码和匿名工作卷；这个验收控制容器拥有 Docker socket（管理权限），任务容器不拥有。不要替换为生产工作区：

```powershell
docker run --rm --name codezzn-sandbox-verification --user 0:0 --network none --mount "type=bind,source=D:/code-agent-rag-workflow,target=/src,readonly" --mount type=volume,target=/workspace --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock --workdir /src --env PYTHONPATH=/src codezzn-sandbox:local python tests/sandbox_live.py
```

预期输出 count=8。任务完成后可查看 `docker ps -a --filter label=io.codezzn.sandbox.instance=codezzn-local`；没有活动任务时不应残留本实例执行容器。

安全限制：共享工作区没有磁盘容量/文件数量配额，也没有多租户隔离。CPU/内存限制不等于磁盘配额，workspace-write 仍能修改或删除工作区内容。主服务的原生文件工具与 MCP 不在本次容器隔离边界内，仍存在并发文件路径竞态；只在可信单机环境启用，关闭不需要的 MCP/原生写文件工具，工作区不要保存密钥。不要将本方案称为完整 Codex 沙箱等价实现。

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CODEZZN_PORT` | `8080` | 宿主机端口 |
| `CODEZZN_DATA_DIR` | `/app/data` | SQLite 数据目录 |
| `CODEZZN_WORKSPACE` | `/workspace` | 智能体文件工具的安全根目录 |
| `CODEZZN_MILVUS_URI` | `/app/data/milvus.db` | Milvus Lite 数据文件；可替换为独立 Milvus 地址 |
| `MILVUS_COLLECTION_PREFIX` | `codezzn_kb_` | 知识库 Collection 前缀 |
| `CODEZZN_ADMIN_KEY` | 空 | 非空时，API 要求 `X-Codezzn-Key` |
| `CODEZZN_BASE_IMAGE` | `python:3.12-slim` | Docker Hub 不可用时可换成内部 Python 3.12 基础镜像 |

Workbench 会将管理密钥保存在浏览器 `localStorage` 中。生产环境应放在 HTTPS 反向代理后，并配置认证、网络隔离和备份。模型密钥当前由本机 SQLite 保存，适合私有单机部署；团队/生产部署应接入 Vault/KMS。

## 接入阿里云百炼 Qwen

在“模型接入”中点击“新建”，从快速预设选择“阿里云百炼”，填写与地域、计费方案匹配的 API Key 后保存，再点击“测试连接”。Codezzn 使用百炼的 OpenAI 兼容 Chat API。

- 北京共享域名：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- 北京业务空间专属域名：`https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`
- 模型示例：`qwen3.7-plus`、`qwen3.7-max`、`qwen3.7-flash`、`qwen-plus`

不要把 DashScope 原生路径 `/api/v1` 填给 Codezzn，也不要把 `qwen3.7-plus` 写成 `qwen-3.7plus`。旧配置会在服务启动时自动纠正。随后进入“智能体”，选择该提供方与模型。

## RAG 知识库

在“知识库”中新建知识库，选择已配置密钥的百炼提供方。默认配置为：

- Embedding：`qwen3.7-text-embedding`
- 向量维度：1024
- 重排序：`qwen3-rerank`
- 向量后端：Milvus Lite，持久化文件为 `data/milvus.db`

上传文档后，Codezzn 会生成向量并写入独立 Collection。智能体绑定知识库后，每一轮对话都会先执行 Milvus 向量召回与 SQLite 词法召回，再用重排序模型筛选证据，回答中显示文档与片段来源。未绑定知识库时不会跨库搜索。

默认使用 Milvus Lite 以简化本地 Docker 部署。生产环境可以将 `CODEZZN_MILVUS_URI` 改为独立 Milvus 的 HTTP 地址，业务代码和已有 API 无需改变。测试资料位于 `samples/bear-knowledge.md`。

## MCP 配置示例

stdio（命令运行在 Codezzn 容器内，因此相关程序也必须安装在镜像中）：

```json
{
  "name": "filesystem",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
  "env": {}
}
```

HTTP：

```json
{
  "name": "remote-mcp",
  "transport": "http",
  "url": "http://host.docker.internal:3000/mcp",
  "headers": {}
}
```

服务测试会显示协商后的 `protocolVersion`、`serverInfo` 和 capabilities。Codezzn 只声明已实现的客户端能力；当前不声明 MCP sampling/elicitation。HTTP OAuth discovery、浏览器授权回调，以及 2026 Tasks/Apps 扩展仍需要后续实现。

## 工作流节点

- `input`: 将运行输入写入上下文
- `prompt`: 模板渲染，不调用模型
- `agent`: 调用已配置智能体
- `knowledge`: 检索知识库
- `mcp`: 直接调用 MCP 工具
- `output`: 生成最终输出

模板支持 `{{input}}`、`{{last}}` 和 `{{节点ID}}`。例如：`请总结以下资料：{{search_docs}}`。节点可设置 `retries` 和 `timeout`，工作流可设置 `max_parallel`；边可设置 `when: true/false` 连接 condition 节点。前台运行立即返回，后台运行进入持久任务队列并在节点完成后保存检查点。

## Codex 风格智能体配置

在“智能体”中新建或编辑配置：选择角色模板，绑定主模型；在动态模型路由 JSON 中按 `pattern`/`keywords`、`priority` 指定 provider/model，在回退模型中排列故障切换顺序。工具策略默认建议对读取工具设 `allow`，对 Patch、Shell、Git 写操作和 MCP 副作用工具设 `ask`。

需要委派时先创建“智能体团队”，选择协调者和成员，再把团队绑定到主智能体；也可直接设置允许的子智能体。启用长期记忆后填写稳定的用户 ID 和项目 ID，只有打开“自动沉淀”才会自动把任务结果写入项目经验。

持久任务为本机 SQLite 的 at-least-once 执行语义。进程异常退出时，运行中任务在下次启动重新排队；带外部副作用的自定义工具必须自行保证幂等。

### 新增编码执行能力

- Responses API：在“模型接入”把 API 模式设为 `Responses API`，再设置默认 reasoning effort、压缩阈值和异步工具声明。系统保存 `response_id` 并用 `previous_response_id` 延续推理；Chat Completions 提供方仍使用本地有界压缩。
- 代码智能：给智能体启用 `code_index`、`code_symbols`、`find_references`、`call_graph`、`dependency_graph`。Python 使用 AST；其他语言建议在“LSP 服务”添加已安装的 language server，并启用 `lsp_request`。
- GitHub：在 `.env` 配置 `CODEZZN_GITHUB_TOKEN`；给智能体启用 Git 远端和 GitHub 工具。所有写操作默认审批，clone/fetch/push 还要求 sandbox overlay 与 `CODEZZN_SANDBOX_GIT_NETWORK=true`。
- Skill 包：上传 ZIP 时包内必须只有一个 `SKILL.md`；可带 `skill.json`，其中 `version` 使用 SemVer，`dependencies` 为字符串/对象数组。脚本只能位于 `scripts/` 且目前仅执行 `.py`/`.sh`；依赖不会在运行期自动安装。
- Browser/Computer Use：给智能体启用 `browser` 工具和“允许浏览器操作”。支持 DOM inspect、selector/坐标点击、鼠标移动、滚动、输入、键盘、截图和受审批的页面脚本；截图写入任务工作区并可通过 `/api/artifacts?path=...` 读取。
- Worktree：当 `/workspace` 本身是 Git 仓库时自动生效；可用 `GET /api/worktrees` 查看，用 `DELETE /api/worktrees/{id}` 清理。清理前确认分支内容已经提交或推送。

## API 概览

- `/api/resources/agents`、`/api/resources/agent_teams`、`/api/resources/providers`、`/api/resources/skills`、`/api/resources/mcp_servers`、`/api/resources/knowledge`、`/api/resources/workflows`：CRUD
- `GET /api/agent-templates`：角色模板
- `POST /api/skills/import`：导入 `SKILL.md` 或完整 ZIP Skill 包
- `POST /api/knowledge/{id}/documents`、`POST /api/knowledge/search`
- `POST /api/mcp_servers/{id}/test`、resources/prompts 相关 MCP API
- `GET /api/sandbox/status`: authenticated broker health and task states
- `POST /api/workflows/{id}/run`、`POST /api/workflows/{id}/enqueue`、`GET /api/workflow-runs`
- `POST /api/agent-tasks`、`GET/DELETE /api/tasks/{id}`、`GET /api/subagents`
- `GET/POST/DELETE /api/memories`、`POST /api/memories/search`
- `POST /api/memories/{id}/confirm`、`GET/DELETE /api/worktrees/{id}`、`POST /api/code-index/rebuild`、`GET /api/code-index/symbols|references|graph`、`GET /api/artifacts`
- `POST /api/threads`、`GET /api/threads/{id}`、`POST /api/threads/{id}/turns`、`POST /api/threads/{id}/turns/stream`
- `POST /api/threads/{id}/fork`、`POST /api/threads/{id}/resume`
- `GET /api/threads/{id}/approvals`、`POST /api/approvals/{approval_id}`、`GET /api/threads/{id}/events`
- `python -m backend.app.cli exec "任务"`、`python -m backend.app.cli exec --json -`
- FastAPI 文档：`/docs`

## 当前边界

This is a runnable single-node platform, not a protocol-equivalent replica of OpenAI Codex Desktop. The optional container sandbox covers Shell/Git only and is intended for a trusted single-machine deployment, not hostile multitenancy. AST support is exact for Python and heuristic for other languages unless an external LSP server is configured. Skill dependencies are declared and exposed but deliberately not installed at runtime; bake trusted dependencies into images. GitHub integration currently targets GitHub REST and needs `CODEZZN_GITHUB_TOKEN`. MCP sampling/elicitation and OAuth discovery, tenant identity/RBAC, encrypted secret storage, remote/distributed workers, realtime audio/video, and a signed plugin marketplace remain outside this release. SQLite recovery is local at-least-once execution; the tool ledger prevents automatic replay of ambiguous side effects but is not a distributed exactly-once transaction system.

## 许可证说明

Codezzn 为独立实现。参考仓库 `F:\codex\codex` 使用 Apache-2.0；若后续直接复制其中代码或资源，应保留对应 LICENSE、NOTICE 与版权声明。
