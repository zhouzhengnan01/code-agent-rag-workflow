# Codezzn

Codezzn 是一个本地优先、可 Docker 部署的智能体开发平台。它参考 Codex 的 Thread/Turn/Item、`SKILL.md` 与 MCP 设计，但拥有独立实现和面向管理场景的 Web Workbench。

## 已实现

- 智能体：系统提示词、模型、温度、最大工具轮次、技能/知识库/MCP/内置工具组合
- 模型接入：任意 OpenAI-compatible `chat/completions` 服务，可配置 Base URL、API Key、模型列表和自定义 Header
- 技能：在线创建、启停、编辑、删除，以及导入 `SKILL.md`
- MCP：stdio 与 Streamable HTTP JSON-RPC transport（含初始化、Session ID、JSON/SSE 响应），服务测试、工具发现、智能体工具调用
- RAG 知识库：TXT/Markdown/JSON/CSV/PDF 上传、自动分块、百炼 Embedding、Milvus 向量检索、词法混合召回、Qwen 重排序与来源引用
- 工作流：input、prompt、agent、knowledge、mcp、output 节点，DAG 校验、运行记录与节点 trace
- Workbench：仪表盘、对话、各资源管理、工作流 JSON 设计器、设置
- 工具执行：知识检索、目录读取、文件读写、受智能体开关控制的 Shell
- 持久化：SQLite WAL 保存业务数据，Milvus 保存知识向量，记录线程消息、知识来源、工具事件、token usage 与工作流运行记录
- 部署：Dockerfile、Compose healthcheck、持久化数据卷、可选 API 管理密钥

## 启动

```powershell
cd F:\codezzn
Copy-Item .env.example .env
docker compose up -d --build
```

打开 <http://localhost:8080/workbench.html>。首次启动会生成一个默认 OpenAI-compatible 提供方和默认智能体；请先在“模型接入”中填入有效 API Key，或将 Base URL 改为你的 Ollama、vLLM、LM Studio、OneAPI 等兼容端点。

查看状态：

```powershell
docker compose ps
docker compose logs -f codezzn
Invoke-RestMethod http://localhost:8080/healthz
```

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
- `POST /api/workflows/{id}/run`、`GET /api/workflow-runs`
- `POST /api/threads`、`GET /api/threads/{id}`、`POST /api/threads/{id}/turns`
- FastAPI 文档：`/docs`

## 当前边界

这是可运行的平台 MVP，不是 OpenAI 官方 Codex Desktop 的逐像素复制。高风险的宿主机沙箱、OAuth 多租户、团队 RBAC、实时语音/视频、插件市场和分布式任务队列仍未实现。在继续生产化之前，优先建议增加身份与租户模型、密钥加密、异步文档任务队列和容器级执行沙箱。

## 许可证说明

Codezzn 为独立实现。参考仓库 `F:\codex\codex` 使用 Apache-2.0；若后续直接复制其中代码或资源，应保留对应 LICENSE、NOTICE 与版权声明。
