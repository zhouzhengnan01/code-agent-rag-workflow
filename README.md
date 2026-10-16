# Codezzn

Codezzn 是一个本地优先、可 Docker 部署的智能体开发平台。它参考 Codex 的 Thread/Turn/Item、`SKILL.md` 与 MCP 设计，但拥有独立实现和面向管理场景的 Web Workbench。

## 已实现

- 智能体：通用/编码/审查/研究/运维角色模板；系统提示词、技能/知识库/MCP/内置工具组合；逐工具 `allow`/`ask`/`deny` 策略
- 模型接入：OpenAI-compatible Chat Completions 与原生 Responses API；支持持久 `previous_response_id`、reasoning effort、自动/本地上下文压缩、并行与异步函数工具声明、动态路由和故障回退
- 技能：在线创建、启停、编辑、删除；安全导入单文件 `SKILL.md` 或带 `scripts/`、`assets/`、`references/`、`skill.json` 的 ZIP 包，并校验 SemVer、依赖声明和内容完整性
- MCP：stdio 与 Streamable HTTP JSON-RPC transport，支持版本/能力协商、Session ID、JSON/SSE、工具、资源/资源模板、提示词、补全、订阅、日志级别、分页，以及 stdio roots 反向请求
- RAG 知识库：可选择本地 SQLite + Milvus 混合检索，或通过独立 RAGFlow 服务使用复杂文档解析、全文/向量混合召回、重排与来源引用；旧知识库保持本地后端，不会被默认配置自动迁移
- 工作流：input、prompt、agent、knowledge、mcp、condition、parallel、output 节点；并行就绪队列、条件边、节点超时/重试、检查点恢复、后台运行和节点 trace
- Workbench：仪表盘、对话、角色/智能体团队、任务队列、长期记忆、各资源管理、React Flow 工作流画布（节点配置、JSON 导入导出、版本历史、运行调试）、设置
- 工具执行：知识检索、代码搜索、AST/符号/引用/调用图/依赖图、LSP 3.18、目录读取、原子文件读写、测试、完整 Git 远端/merge 工作流、GitHub PR/CI/Review、Playwright 浏览器/DOM/截图；写操作受沙箱、审批与工具策略共同控制
- 后台任务：SQLite 持久队列、并发 worker、失败退避重试、取消、事件历史、进程重启后恢复未完成任务；智能体和工作流均可后台执行
- 多智能体：可配置团队、协调智能体、成员白名单、并发和深度限制；主智能体通过 `delegate_task` 并行委派并用 `task_status` 汇总
- 长期记忆：用户、项目和线程三级作用域，哈希向量+词法混合检索、可信度、冲突待确认、确认/拒绝、过期淘汰和自动经验沉淀
- 任务隔离与恢复：项目写任务使用独立 Git worktree 或有界文件快照；发布回项目前校验哈希，冲突保留任务副本而不覆盖他人修改。模型轮次、Responses ID 和工具结果持久化；有有效检查点的安全对话可在重启后恢复，副作用结果不明时停止自动重放；轮次预算耗尽后显示继续/停止问题卡
- 编码工程闭环：计划与版本化审批、显式测试/lint/类型检查质量门、修改前基线对照、双视角模型审查与证据验证、PreToolUse/PostToolUse/Stop Hooks、文件快照/Diff/哈希保护回退；网页“工程”面板、CLI `/plan /diff /context /review /rewind` 和可选 VS Code 客户端桥
- 按需上下文与开发环境：MCP 工具动态发现、Skill 指令渐进加载与只读依赖预检、结构化/语义上下文压缩、增量代码索引、隔离 LSP 与跨轮后台命令日志；后台命令不是交互式 PTY，语言服务器和 Node 环境需管理员按文档构建
- Execution safety: container-backed `read-only` / `workspace-write` Shell and read-only Git; `danger-full-access` Shell is rejected. Thread locks, approval records, atomic file writes, and backups remain unchanged.
- Windows CLI：Node.js 20+ 的 `codezzn` 客户端，支持浏览器账号授权、交互/单次对话、流式文本/JSON/JSONL、智能体与模型选择、项目选择、审批/追问、会话续接、断线恢复、附件上传和取消；复用服务器项目与 Docker 沙箱，不执行 Windows 主机命令
- 原有 Python CLI：`python -m backend.app.cli exec` 支持非交互执行、stdin 和 JSONL 事件输出，与新增 Windows 客户端并存
- 持久化：SQLite WAL 保存业务数据，Milvus 保存知识向量，记录线程消息、知识来源、工具事件、token usage 与工作流运行记录
- 认证与部署：本地账号、邮箱验证码（需 SMTP）、GitHub/Google OAuth、HttpOnly 浏览器会话、可撤销的 CLI 凭证、按账号隔离的业务库与工作区；Dockerfile、Compose healthcheck、持久化数据卷和可选 API 管理密钥

## 启动

默认使用方式已改为“直接对话”，无需先创建智能体或勾选 Skill/权限。Web 点击“新对话”或运行 Windows `codezzn`，即使用内置 Codezzn 运行配置；仍需账号具有可用的模型提供方/API 凭据。旧会话与自定义智能体保持原配置，不会自动放宽权限。

- 基础读取、搜索与编码工具默认提供；写文件和运行命令时才弹出审批。项目选择仍是文件归属确认，不等于批准工具执行。
- Skill 自动发现当前账号已启用、且属于用户或当前项目的技能，只先加载描述；模型按需读取 `SKILL.md`。也可输入 `/技能名 任务` 或 `/skill 技能名 任务` 手动调用，`/skills` 查看列表。
- 配置优先级为内置默认 → 用户默认 → 项目默认 → 当前会话覆盖。Web 输入框旁的权限下拉和“默认配置”入口可调整；CLI 使用 `/permissions default|acceptEdits|plan|inherit`。
- `default` 对写入/命令逐次审批；`acceptEdits` 仅自动接受工作区文件编辑，Shell、脚本和外部写操作仍按原策略审批；`plan` 禁止文件写入和命令。拒绝规则、只读沙箱、禁用 Shell/浏览器和账号隔离不能被 Skill 提升。

完整配置、兼容边界和网页验收步骤见 [直接对话与按需 Skill](docs/direct-chat-runtime.md)。

本次编码能力对齐的配置、网页对话测试、CLI/VS Code 入口、部署与明确边界见 [编码能力验收指南](docs/coding-parity.md)。实现参考本机 Claude Code 2.1.140 的可观测接口，不包含其私有模型、私有 Prompt 或专有云服务，不声明编码效果完全等价。

工作流画布的重新部署、入门 / 条件分支 / 知识库问答测试步骤见 [工作流画布使用说明](docs/workflow-canvas.md)。Docker 默认同时构建前端与后端；不能拉取 Node 镜像时可先用本机 Node 编译并选择 `CODEZZN_BUILD_TARGET=prebuilt`。

智能体问答、模型检索决策、两条分支的真实 Agent 调用，以及旧演示流程升级步骤见 [智能体工作流说明](docs/workflow-agent-routing.md)。

本地知识库批量上传、后台文档处理、失败重试与片段预览见 [知识库文档处理说明](docs/knowledge-documents.md)。

会话队列、按需检索、追问恢复、执行中追加/中断与默认项目保存见 [会话交互闭环说明](docs/conversation-interactions.md)。

```powershell
cd D:\code-agent-rag-workflow
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
```

打开 <http://127.0.0.1:8080/>。Docker Compose 默认启用登录保护，首次使用请注册本地账号，或按下文配置 GitHub OAuth。首次启动会生成一个默认 OpenAI-compatible 提供方和默认智能体；登录后请先在“模型接入”中填入有效 API Key，或将 Base URL 改为你的 Ollama、vLLM、LM Studio、OneAPI 等兼容端点。

Windows Docker Desktop 使用 bind mount 时，宿主机文件权限可能与容器内非 root UID 不一致。Compose 默认使用 `CODEZZN_UID=0`、`CODEZZN_GID=0` 保证本地启动可写；Linux 主机可在 `.env` 中改为 `./data` 和 `./workspace` 所属用户的 UID/GID。

## Windows 命令行客户端（CLI）

Windows Terminal、PowerShell 或 CMD 中可以使用 `codezzn` 对话，无需打开 Workbench。它是现有 Codezzn 服务的客户端：模型调用、项目文件和工具执行仍在服务器完成，Shell/Git 继续使用服务器配置的 Docker 沙箱。

命令接口参考实际观察到的 Claude Code CLI 交互方式，代码为独立实现；不包含 Claude 私有提示词、模型服务或全部专有功能。完整说明见 [Windows CLI 使用指南](docs/windows-cli.md)。

### 1. 安装或更新 CLI

前置条件：Windows 已安装 **Node.js 20 或更高版本**（含 npm），且 Codezzn 服务正在运行并包含 CLI 授权接口。客户端不需要 Python 或本机 Docker；Docker 在执行工具的服务器上运行。

```powershell
cd D:\code-agent-rag-workflow
node --version
powershell.exe -NoProfile -File .\scripts\install-windows-cli.ps1
codezzn --version
codezzn --help
```

安装器只安装仓库中的 `@codezzn/cli`，不下载外部依赖、不执行 npm 安装脚本、不修改机器 PATH；已有 `codezzn` 命令时会询问是否更新。更新源码后重新运行同一个安装器。只检查、不安装可加 `-CheckOnly`。若 npm 全局目录不在 PATH，或暂不安装，直接使用：

```powershell
node .\cli\bin\codezzn.js --help
```

### 2. 使用现有账号登录

`--server` 必须与服务端 `.env` 的 `CODEZZN_PUBLIC_URL` 一致，包括协议、主机和端口。以下是局域网 HTTP 示例，**请替换成自己配置的公开地址**：

```powershell
$CodezznServer = "http://192.168.35.69:8080"
codezzn auth login --server $CodezznServer --allow-insecure-http
codezzn auth status --allow-insecure-http
```

CLI 打开浏览器授权页；通过 Codezzn 已配置的登录方式登录，核对页面与终端的授权码，再允许当前客户端访问。不要把 GitHub/Google 密码、管理密钥或 OAuth Secret 填到终端。无法自动打开浏览器时，加 `--no-browser` 手动打开显示的授权地址。

登录成功后客户端记住该服务器地址。局域网 HTTP 不加密，**每次调用都必须显式加 `--allow-insecure-http`**；生产环境建议使用 HTTPS，HTTPS 不需要该参数。未指定 `--server` 且尚未记住服务器地址时，客户端默认访问 `http://localhost:8080`；若服务器已配置其他公开地址，须显式指定正确的 `--server`，否则会返回 `server_url_mismatch`，而不是自动切换并传递凭据。

### 3. 对话、项目与工具审批

```powershell
codezzn --allow-insecure-http
```

默认无需 `--agent`。如需使用已有高级配置，`--agent` 可使用服务器智能体 ID 或唯一名称；实际名称以 Workbench 配置为准。进入交互终端后：

```text
/agent
/project
/project 0929-dev
帮我写一份冒泡排序的 Python 文件，保存到当前项目，并读取验证内容。
```

`/project` 列出服务器项目，`/project 名称或ID` 切换当前会话项目；项目必须属于当前登录账号。创建项目、保存产物和受保护工具是否需要确认，遵循服务器返回的交互请求及智能体策略。工具审批展示名称与参数，需要明确输入 `y` 或 `yes` 才允许，空输入默认拒绝。

**Windows 当前目录不是服务器工作区**，不会自动同步或上传本地仓库。生成的项目文件仍可在 Workbench 的 Files 面板查看和下载；`/files` 用于查看待发送附件，`/files "D:\work\example.py"` 显式上传本地文件作为下一条消息的上下文。

### 4. 常用命令

以下延续上述局域网 HTTP 登录；HTTPS 使用时可省略 `--allow-insecure-http`：

```powershell
# 单次对话，完成后退出
codezzn --allow-insecure-http --agent "coding agent" -p "列出我有哪些项目"

# 继续相同服务器、账号、当前目录下最近的会话
codezzn --allow-insecure-http -c

# 恢复指定会话；不提供 ID 时交互选择本地记录
codezzn --allow-insecure-http -r SESSION_ID

# 命名会话；模型必须已在服务器配置
codezzn --allow-insecure-http --name "代码验收" --agent "coding agent" --model PROVIDER_ID/MODEL

# 输出完整 JSON 结果或逐事件 JSONL
codezzn --allow-insecure-http -p --output-format json "介绍当前项目"
codezzn --allow-insecure-http -p --output-format stream-json "介绍当前项目"

# 显式上传附件，不自动读取其他本地文件
codezzn --allow-insecure-http --attach "D:\work\example.py" "审查这个文件"

# 清除本机该服务器的 CLI 凭据并请求服务端撤销，不退出浏览器账号
codezzn auth logout --allow-insecure-http
```

| 交互命令 | 用途 |
| --- | --- |
| `/help`、`/status` | 查看帮助、当前会话状态 |
| `/new`、`/resume [ID]` | 新建或恢复会话 |
| `/agent [名称或ID]`、`/model [模型]` | 列出或切换服务器智能体/模型；`/model default` 恢复智能体默认模型 |
| `/project [名称或ID]` | 列出或切换服务器项目 |
| `/files [本地路径]` | 查看待发送附件，或明确上传文件 |
| `/skills`、`/技能名 任务`、`/skill 名称 任务` | 查看当前范围技能；按需调用，不改变执行权限 |
| `/permissions default\|acceptEdits\|plan\|inherit` | 查看/切换当前会话权限，继承用户及项目配置 |
| `/mcp` | 查看已配置服务，不自动启动 Windows 本地 MCP |
| `/stop`、`/exit` | 请求取消当前任务，或退出客户端 |

Ctrl+C 请求取消当前服务器任务，再按一次立即退出。附件限制为每文件最多 10 MiB、每回合最多 8 个且合计不超过 20 MiB。

`-p` 是非交互模式，**不会自动允许工具或回答确认问题**。遇到待确认任务，返回 `requires_action` 和会话 ID，使用交互模式 `-r SESSION_ID` 继续处理。退出码：成功 `0`、失败 `1`、待确认 `2`、取消 `130`。机器格式的结果写 stdout，诊断写 stderr。

### 5. 凭据、恢复与部署边界

- Windows 凭据存于 `%USERPROFILE%\.codezzn`，使用 DPAPI CurrentUser 加密；DPAPI 不可用时失败，不降级为明文。服务端保存令牌哈希，CLI 令牌有效期 30 天，可撤销。
- 本地会话记录按服务器、用户和当前目录区分，包含未完成提示词及交互答案，属于私密数据。可用客户端环境变量 `CODEZZN_CONFIG_DIR` 更换保存目录，不要将它提交到 Git。
- 提交前保存请求 ID 和原始载荷，断线后查询原请求；恢复时复用原提交/答案身份，避免因丢失响应而重复派发。此机制不代表服务器异常退出后的任何任务都能自动继续，也不是分布式 exactly-once 保证。
- 未新增 Windows 主机执行、权限绕过、本地 stdio MCP、IDE 集成或 Claude 专有服务。现有服务器工具策略、租户隔离和沙箱限制照常生效。
- 安装客户端不等于更新服务器。旧服务器没有 `/api/auth/cli/*` 时需要部署新后端；已启用沙箱的部署应保留两份 Compose 文件及现有 `.env`，按下方沙箱部署说明重建，不能只启动主 Compose 而丢掉 broker 配置。

客户端源码在 `cli/`，安装脚本在 `scripts/install-windows-cli.ps1`，服务端授权接口在 `backend/app/cli_auth.py`，浏览器确认页在 `web/cli-authorize.html` 和 `web/cli-authorize.js`。

### 6. CLI 验收

```powershell
node --test tests/test_windows_cli.cjs
.\.workflow-venv\Scripts\python.exe -m pytest tests/test_cli_auth.py tests/test_cli_e2e.py tests/test_auth.py tests/test_user_isolation.py tests/test_conversation_sessions.py -q
```

Python 命令使用已安装项目测试依赖的虚拟环境。端到端测试在临时数据库和实际 HTTP 服务中验证浏览器授权、Windows DPAPI、流式事件、续接和退出；模型使用受控模拟，不调用真实 OAuth 或付费模型。参考接口与验收记录见 [CLI 实测说明](docs/research/claude-code-cli-20261013/README.md) 和 [CLI 验收记录](docs/research/claude-code-cli-20261013/QA.md)。

## 注册、登录与 GitHub / Google OAuth

本地注册使用 scrypt 密码哈希；浏览器只保存 `HttpOnly`、`SameSite=Lax` 会话 Cookie。生产环境放在 HTTPS 反向代理后时，将 `CODEZZN_PUBLIC_URL` 改为外部 HTTPS 地址，并设置 `CODEZZN_COOKIE_SECURE=true`。

要启用“使用 GitHub 继续”，在 GitHub 创建 OAuth App，Homepage URL 填 Codezzn 的公开地址，Authorization callback URL 填：

```text
http://127.0.0.1:8080/api/auth/github/callback
```

然后写入现有 `.env`（不要提交真实 Secret）：

```env
CODEZZN_AUTH_REQUIRED=true
CODEZZN_PUBLIC_URL=http://127.0.0.1:8080
CODEZZN_GITHUB_CLIENT_ID=your-client-id
CODEZZN_GITHUB_CLIENT_SECRET=your-client-secret
CODEZZN_SESSION_DAYS=14
CODEZZN_COOKIE_SECURE=false
```

修改后运行 `docker compose up -d --build`。未配置 GitHub OAuth 时，本地邮箱注册/登录仍可正常使用，GitHub 按钮会返回明确的配置提示。

退出 Codezzn 会撤销当前应用会话并清除 Cookie；再次通过 GitHub 登录会要求显示账号选择器，OAuth `state` 也绑定到发起登录的浏览器。**这不会退出 github.com，也不能保证 GitHub 每次要求输入密码或二次验证**——认证挑战由 GitHub 控制。共用设备应同时退出 GitHub；若业务合规要求每次都进行密码/MFA 挑战，需要另行接入能实施该策略的身份提供方或添加应用级二次验证。生产环境请使用 HTTPS 并设置 `CODEZZN_COOKIE_SECURE=true`。

如果宿主机访问 GitHub 必须走代理，而容器直连 GitHub 超时，可设置 `CODEZZN_GITHUB_PROXY_URL` 为**容器实际可访问**的 HTTP 代理地址（例如 `http://host.docker.internal:7897`，但需先从容器验证连通）。该代理只用于 GitHub OAuth，不影响内网 RAGFlow 请求。代理不可达时，登录页会显示连接失败/超时，而不会暴露授权码或返回空白 500 页面。

要启用“Continue with Google”，在 Google Cloud Console 的 Google Auth Platform 配置应用品牌与受众，创建 **Web application** 类型 OAuth Client，并在该 Client 的 Authorized redirect URIs 中填入与 Codezzn 完全一致的回调地址。本机测试可填 `http://127.0.0.1:8080/api/auth/google/callback`；从其他电脑访问时必须先使用带 HTTPS 的正式域名（Google 不允许 `192.168.x.x` 这样的私有 IP 作为 Web OAuth 回调）。仅请求 `openid email profile` 时，Google 的基础资料权限例外规则允许未列入 Testing 测试名单的用户授权；如日后增加其他权限，需按 Audience/Testing 的要求管理测试用户。面向正式公开使用时应将应用发布为 In production，并按 Google 要求完成可能需要的验证。

在 `.env` 中填写（不要把 Secret 提交到仓库）：

```env
CODEZZN_PUBLIC_URL=https://your-codezzn.example.com
CODEZZN_COOKIE_SECURE=true
CODEZZN_GOOGLE_CLIENT_ID=your-google-web-client-id
CODEZZN_GOOGLE_CLIENT_SECRET=your-google-web-client-secret
# 可选：默认使用 CODEZZN_PUBLIC_URL/api/auth/google/callback
CODEZZN_GOOGLE_REDIRECT_URI=
```

然后运行 `docker compose up -d --build codezzn`，打开登录页点击 Continue with Google。Google 授权只请求 `openid email profile`，Codezzn 校验 `state`、PKCE、ID token、`nonce` 与已验证邮箱，并以 Google 的 `sub` 识别用户。已有本地或 GitHub 账号即使邮箱相同也**不会自动合并**，以免跨身份接管原有工作区；请先用原方式登录。退出 Codezzn 只撤销本应用会话，不会退出 Google；重新登录会显示 Google 账号选择器，但密码/MFA 提示由 Google 决定。若容器访问 Google 需要代理，可设置 `CODEZZN_GOOGLE_PROXY_URL` 为容器可达的代理地址。

### Continue with Email 邮箱验证码登录

Codezzn 不限定收件邮箱域名：QQ、163、126、139、189、阿里邮箱、企业邮箱以及国际化域名均走同一发送与验证流程；实际投递能否成功取决于发件 SMTP 服务、收件方策略，以及必要时的 SPF/DKIM/DMARC 配置。需要一只可通过 SMTP 发信的邮箱或邮件服务，通常要使用其**SMTP 授权码/应用密码**，不要在仓库保存凭据。在 `.env` 中配置：

```env
CODEZZN_SMTP_HOST=你的SMTP服务器地址
CODEZZN_SMTP_PORT=465
CODEZZN_SMTP_SECURITY=ssl
CODEZZN_SMTP_USER=你的发件账号
CODEZZN_SMTP_PASSWORD=你的SMTP授权码
CODEZZN_SMTP_FROM=你的发件邮箱地址
```

若服务商要求 STARTTLS，则改为 `CODEZZN_SMTP_PORT=587`、`CODEZZN_SMTP_SECURITY=starttls`。容器需能连接 SMTP 服务器的对应端口。保存后执行 `docker compose up -d --force-recreate --no-deps codezzn`，在 `/api/auth/me` 确认 `email_code_configured=true`，再从登录页选择 Continue with Email 测试。验证码有效期 10 分钟、最多尝试 5 次、60 秒内不可重复发送，并限制每地址及全站发送频率。启用 SMTP 后，新邮箱注册必须验证邮件；已有本地账号可使用验证码或密码登录。若邮箱只绑定 GitHub/Google 身份且没有本地登录凭据，验证码不会自动合并身份或接管该账号。未配置 SMTP 时沿用原密码登录/注册；但若已有仅通过验证码登录、没有密码的账号，不要在未提供替代登录方式前关闭 SMTP。

## 可选 RAGFlow 检索后端

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
- Only Shell/Git execution is container-sandboxed. MCP/LSP servers, Playwright, and native Python file tools execute in the main application's trust boundary. Playwright navigation rejects private/link-local destinations by default and can use an admin domain allowlist, but it is not a network sandbox; deploy with outbound egress controls and enable browser access only for trusted agents.
- When `/workspace` is a Git work tree, each persistent task or conversation receives an independent branch and `git worktree` below `.codezzn-worktrees/`. A non-Git workspace cannot provide branch isolation and falls back to the base workspace.
- A repository created with `git init` but no first commit also has no usable `HEAD`: chats fall back to that account's own workspace instead of failing at startup. This mode has no per-task file isolation. For concurrent coding tasks, make a deliberate first commit containing only files you intend to track; Codezzn does not create a commit on your behalf.

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

安全限制：登录账号的业务数据库与工作区已按用户分开，Shell/Git 沙箱只挂载该用户工作区；但还没有磁盘容量/文件数量配额，也不是完整的恶意租户安全边界。CPU/内存限制不等于磁盘配额，workspace-write 仍能修改该用户工作区。登录用户的本地 stdio MCP 和本地 LSP 暂时禁用，HTTP MCP 可用；不要将本方案称为完整 Codex 沙箱等价实现。

现有共享数据迁移：升级前，在 `.env` 设置 `CODEZZN_LEGACY_OWNER_GITHUB_ID` 为历史数据归属账号的**数字 GitHub ID**。该账号必须已登录过一次。首次启动会通过 SQLite 在线备份将旧业务库复制到 `./data/users/<user-id>/codezzn.db`，清除副本中的账号与会话记录，并将旧 `./workspace` 内容复制到 `./workspace/.codezzn-users/<user-id>/`；原库及原文件保留，不会删除。其他账号首次使用时创建独立空业务库和工作区。迁移后不要继续通过管理员密钥修改旧共享业务库，否则后续改动不会自动同步。升级期间应停止旧版本服务的写入。

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CODEZZN_PORT` | `8080` | 宿主机端口 |
| `CODEZZN_DATA_DIR` | `/app/data` | SQLite 数据目录 |
| `CODEZZN_WORKSPACE` | `/workspace` | 智能体文件工具的安全根目录 |
| `CODEZZN_MILVUS_URI` | `/app/data/milvus.db` | Milvus Lite 数据文件；可替换为独立 Milvus 地址 |
| `MILVUS_COLLECTION_PREFIX` | `codezzn_kb_` | 知识库 Collection 前缀 |
| `CODEZZN_ADMIN_KEY` | 空 | 可选的 `X-Codezzn-Key` 管理认证；普通用户可使用账号会话或 CLI Bearer 凭证 |
| `CODEZZN_AUTH_REQUIRED` | Compose 中为 `true` | 要求工作台使用有效账号会话、CLI 凭证或管理密钥认证 |
| `CODEZZN_PUBLIC_URL` | `http://127.0.0.1:8080` | 外部公开地址，用于 OAuth 回调和 CLI 浏览器授权；CLI `--server` 应与实际配置一致 |
| `CODEZZN_GITHUB_CLIENT_ID` | 空 | GitHub OAuth App Client ID |
| `CODEZZN_GITHUB_CLIENT_SECRET` | 空 | GitHub OAuth App Client Secret |
| `CODEZZN_GITHUB_PROXY_URL` | 空 | 仅 GitHub OAuth 使用的容器可达 HTTP 代理 |
| `CODEZZN_GOOGLE_CLIENT_ID` | 空 | Google Web application OAuth Client ID |
| `CODEZZN_GOOGLE_CLIENT_SECRET` | 空 | Google OAuth Client Secret |
| `CODEZZN_GOOGLE_REDIRECT_URI` | 自动生成 | 可选的精确 Google 回调地址，须与控制台完全一致 |
| `CODEZZN_GOOGLE_PROXY_URL` | 空 | 仅 Google OAuth 使用的容器可达 HTTP 代理 |
| `CODEZZN_SMTP_HOST` | 空 | 邮箱验证码的 SMTP 服务器 |
| `CODEZZN_SMTP_PORT` | `465` | SMTP 端口；STARTTLS 通常使用 `587` |
| `CODEZZN_SMTP_SECURITY` | `ssl` | `ssl` 或 `starttls`；不允许明文 SMTP |
| `CODEZZN_SMTP_USER` | 空 | SMTP 发件账号 |
| `CODEZZN_SMTP_PASSWORD` | 空 | SMTP 授权码/应用密码 |
| `CODEZZN_SMTP_FROM` | 空 | 发件邮箱地址 |
| `CODEZZN_BROWSER_ALLOWED_DOMAINS` | 空 | 浏览器目标域名白名单；逗号分隔，空表示不额外限制公网域名 |
| `CODEZZN_BROWSER_ALLOW_PRIVATE_NETWORK` | `false` | 允许访问白名单中的内网目标；仅在确有需要时开启 |
| `CODEZZN_BROWSER_MAX_SESSIONS` | `64` | 本地 Playwright 同时保留的会话上限 |
| `CODEZZN_BROWSER_MAX_TABS` | `12` | 单会话标签上限 |
| `CODEZZN_BROWSER_SESSION_IDLE_SECONDS` | `3600` | 空闲会话回收时间 |
| `CODEZZN_BROWSER_MAX_FILE_BYTES` | `52428800` | 上传/下载文件大小上限（50 MiB） |
| `CODEZZN_SESSION_DAYS` | `14` | 登录会话有效天数 |
| `CODEZZN_COOKIE_SECURE` | `false` | HTTPS 生产环境应设为 `true` |
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

上传文档后，Codezzn 会生成向量并写入独立 Collection。智能体绑定知识库后，默认 `retrieval_mode=auto`，由模型在需要相关知识时调用 `knowledge_search`，不会对问候或普通编程任务强行检索。`always` 模式在每轮前自动检索，`off` 禁用知识检索；工具策略仍可禁止该工具。本地检索结合 Milvus 向量召回与 SQLite 词法召回，并按配置重排证据，回答展示实际使用的文档与片段来源。未绑定知识库时不会跨库搜索。

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
- Browser/Computer Use：给智能体启用浏览器能力。Codezzn 使用本地 Playwright（不会调用 Browser Use Cloud），兼容公开 Browser Use MCP 核心工具名：navigate/click/type/get-state/extract/scroll/back/list-tabs/switch/close；同时支持 hover、双击、右键、拖拽、等待、元素详情、下载、截图和 PDF。必要时可调用 `browser_get_state` 并设置 `include_screenshot=true`，将受大小限制的当前视口截图作为图片发给配置的模型；仅适用于支持图片输入的模型，数据发往你已配置的模型服务，且可能包含在可恢复任务状态中。会话按租户+对话隔离，空闲超时清理；文件上传、下载和页面变更仍经过 Codezzn 审批与项目文件规则。浏览器为无头、内存会话，容器重启后不保留登录态。

  默认阻止回环、私网、链路本地和云元数据目标，并拦截重定向/子资源请求。若确需访问内网，请由管理员在 `.env` 同时配置 `CODEZZN_BROWSER_ALLOWED_DOMAINS=192.168.1.10,app.internal.example` 与 `CODEZZN_BROWSER_ALLOW_PRIVATE_NETWORK=true`，然后重启服务；不要将宽泛通配符作为白名单。建议额外设置 Docker/主机出口防火墙，避免仅依赖应用层 DNS 检查。
- Worktree：当 `/workspace` 本身是 Git 仓库时自动生效；可用 `GET /api/worktrees` 查看，用 `DELETE /api/worktrees/{id}` 清理。清理前确认分支内容已经提交或推送。

## API 概览

新版对话工作台的附件上传、会话模型切换、历史子菜单及部署/验收方法见 [对话工作台说明](docs/chat-workbench.md)。

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
- `POST/GET /api/threads/{id}/queue`、`GET/DELETE /api/threads/{id}/queue/{message_id}`：持久提交、状态查询和取消；网页与 Windows CLI 共用
- `GET /api/threads/{id}/interactions`、`POST /api/threads/{id}/interactions/{interaction_id}/answer`：项目确认、工具审批和追问回答
- `POST /api/auth/cli/device`、`GET /api/auth/cli/device-info`、`POST /api/auth/cli/approve`、`POST /api/auth/cli/token`：CLI 一次性浏览器授权；确认页面 `/cli/authorize`
- `GET /api/auth/cli/status`、`POST /api/auth/cli/logout`：CLI 凭据状态与撤销；凭据不替代审批页面的浏览器会话
- `codezzn`、`codezzn -p "任务"`、`codezzn -c`、`codezzn -r SESSION_ID`：Windows HTTP 客户端，首次使用前按上文登录
- `python -m backend.app.cli exec "任务"`、`python -m backend.app.cli exec --json -`
- FastAPI 文档：`/docs`

## 当前边界

This is a runnable single-node platform, not a protocol-equivalent replica of OpenAI Codex Desktop or Claude Code. The optional container sandbox covers Shell/Git only and is intended for a trusted single-machine deployment, not hostile multitenancy. Account-scoped business databases and workspaces are implemented, but advanced RBAC and disk quotas are not. AST support is exact for Python and heuristic for other languages unless an external LSP server is configured. Skill dependencies are declared and exposed but deliberately not installed at runtime; bake trusted dependencies into images. GitHub integration currently targets GitHub REST and needs `CODEZZN_GITHUB_TOKEN`. Windows CLI credentials use DPAPI, but server-side model secrets do not have Vault/KMS-backed encrypted storage. MCP sampling/elicitation and OAuth discovery, remote/distributed workers, realtime audio/video, and a signed plugin marketplace remain outside this release. Recovery behavior depends on the execution path; interrupted running chat tasks require a new continuation task. The tool ledger prevents automatic replay of ambiguous side effects but is not a distributed exactly-once transaction system. The Windows CLI operates server projects and does not execute local Windows tools.

## 许可证说明

Codezzn 为独立实现。参考仓库 `F:\codex\codex` 使用 Apache-2.0；若后续直接复制其中代码或资源，应保留对应 LICENSE、NOTICE 与版权声明。
