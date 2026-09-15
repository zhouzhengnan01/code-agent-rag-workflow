# Codezzn

Codezzn 是一个本地优先、可 Docker 部署的智能体开发平台。它参考 Codex 的 Thread/Turn/Item、`SKILL.md` 与 MCP 设计，但拥有独立实现和面向管理场景的 Web Workbench。

## 已实现

- 智能体：系统提示词、模型、温度、最大工具轮次、技能/知识库/MCP/内置工具组合
- 模型接入：任意 OpenAI-compatible `chat/completions` 服务，可配置 Base URL、API Key、模型列表和自定义 Header
- 技能：在线创建、启停、编辑、删除，以及导入 `SKILL.md`
- MCP：stdio 与 Streamable HTTP JSON-RPC transport（含初始化、Session ID、JSON/SSE 响应），服务测试、工具发现、智能体工具调用
- RAG 知识库：可选择本地 SQLite + Milvus 混合检索，或通过独立 RAGFlow 服务使用复杂文档解析、全文/向量混合召回、重排与来源引用；旧知识库保持本地后端，不会被默认配置自动迁移
- 工作流：input、prompt、agent、knowledge、mcp、output 节点，DAG 校验、运行记录与节点 trace
- Workbench：仪表盘、对话、各资源管理、工作流 JSON 设计器、设置
- 工具执行：知识检索、目录读取、文件读写、Patch、Git 状态/Diff/Log/Review、受沙箱与审批策略控制的 Shell
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

The sandbox image contains Python 3.12, Git, patch, and CA certificates, with Python standard-library tests available by default. It contains no Node.js or application/model dependencies. To include pinned pytest for user tests, build it instead with:

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
- Each Shell or Git tool invocation gets a **separate execution container**, not one container for a whole Turn. Execution runs as UID/GID `10001:10001` in `/workspace`, without network, inherited application environment secrets, or Docker socket. Defaults are 1 CPU, 512 MiB memory, 64 PIDs, and a 60-second timeout, configurable with `CODEZZN_SANDBOX_CPUS`, `CODEZZN_SANDBOX_MEMORY_MB`, `CODEZZN_SANDBOX_PIDS`, and `CODEZZN_SANDBOX_TIMEOUT`.
- Only Shell/Git execution is container-sandboxed. MCP servers (including native stdio processes) and native Python file tools are **out of scope** and still execute in the main application's trust boundary. Files containing secrets under the shared workspace remain readable to allowed tools; environment isolation does not hide workspace files.
- The workspace is shared between invocations, agents, and threads. Writes persist in `workspace-write`; this is **not branch, tenant, or per-Turn filesystem isolation**. Coordinate concurrent edits separately.

### Tool permissions and Linux bind mounts

`run_shell` requires both `allow_shell=true` and `auto_approve=true`, in either `read-only` or `workspace-write`. Read-only Shell **does not require enabling `danger-full-access`**; that mode is rejected rather than executed on the host. Git status/diff/log/review always use `read-only`, disable hooks and fsmonitor, and disable external diffs/text conversion. Review refs reject option-like or unsupported revision input. Unified-diff `apply_patch` input is rejected: use exact `old`/`new` replacements instead; their existing file-write approval rules still apply.

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

Inspect the returned task states and `cleanup_pending` flags together with broker logs. Missing image, socket access, workspace mount/permissions, or mismatched tokens must be fixed at deployment; never bypass them with host execution. The client raises `RuntimeError` for unavailable/failed/timed-out execution and cancels the remote task when its awaiting coroutine is cancelled. This integration does not change Turn lifecycle or introduce a new Turn cancellation API.

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

## 工作流节点

- `input`: 将运行输入写入上下文
- `prompt`: 模板渲染，不调用模型
- `agent`: 调用已配置智能体
- `knowledge`: 检索知识库
- `mcp`: 直接调用 MCP 工具
- `output`: 生成最终输出

模板支持 `{{input}}`、`{{last}}` 和 `{{节点ID}}`。例如：`请总结以下资料：{{search_docs}}`。

## API 概览

- `/api/resources/agents`、`/api/resources/providers`、`/api/resources/skills`、`/api/resources/mcp_servers`、`/api/resources/knowledge`、`/api/resources/workflows`：CRUD
- `POST /api/skills/import`：导入 `SKILL.md`
- `POST /api/knowledge/{id}/documents`、`POST /api/knowledge/search`
- `POST /api/mcp_servers/{id}/test`
- `GET /api/sandbox/status`: authenticated broker health and task states
- `POST /api/workflows/{id}/run`、`GET /api/workflow-runs`
- `POST /api/threads`、`GET /api/threads/{id}`、`POST /api/threads/{id}/turns`、`POST /api/threads/{id}/turns/stream`
- `POST /api/threads/{id}/fork`、`POST /api/threads/{id}/resume`
- `GET /api/threads/{id}/approvals`、`POST /api/approvals/{approval_id}`、`GET /api/threads/{id}/events`
- `python -m backend.app.cli exec "任务"`、`python -m backend.app.cli exec --json -`
- FastAPI 文档：`/docs`

## 当前边界

This is a runnable platform MVP, not a pixel-for-pixel replica of OpenAI Codex Desktop. The optional container sandbox covers Shell/Git only and is intended for a trusted single-machine deployment, not hostile multitenancy. OAuth multitenancy, team RBAC, realtime audio/video, a plugin marketplace, and distributed task queues remain unimplemented. Further production hardening should prioritize identity/tenant boundaries, encrypted secrets, asynchronous document jobs, and isolation of the remaining native/MCP tools.

## 许可证说明

Codezzn 为独立实现。参考仓库 `F:\codex\codex` 使用 Apache-2.0；若后续直接复制其中代码或资源，应保留对应 LICENSE、NOTICE 与版权声明。
