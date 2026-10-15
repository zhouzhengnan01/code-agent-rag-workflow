# Codezzn Windows CLI

这是当前 Codezzn 服务的命令行客户端：账号、智能体、项目、工具审批和 Docker 沙箱继续由服务器管理。Windows 当前目录只用于区分会话，不会自动上传目录，也不授予主机执行权限。

参考已安装 Claude Code 2.1.140 的实际帮助接口，实现交互对话、单次输出、流式输出、模型选择、会话续接及取消。不是 Claude 的私有提示词、云服务或全部功能的复制品。

## 安装

需要 Node.js 20 或更高版本；不需要安装 Python。

```powershell
cd D:\code-agent-rag-workflow
powershell.exe -NoProfile -File .\scripts\install-windows-cli.ps1
codezzn --help
```

安装器只安装本项目的 npm 命令，不下载依赖、不改机器 PATH。已有同名命令时会先询问。若命令不在 PATH，可直接运行 `node .\cli\bin\codezzn.js`，参数相同。

## 登录和第一次对话

当前服务器的公开地址配置为 `http://192.168.35.69:8080`。地址变化时应先同步服务器的 `CODEZZN_PUBLIC_URL` 和 OAuth 回调配置，再使用新地址登录。

```powershell
codezzn auth login --server http://192.168.35.69:8080 --allow-insecure-http
codezzn auth status --allow-insecure-http
codezzn --allow-insecure-http --agent "coding agent"
```

第一条命令会打开浏览器。通过现有 GitHub、Google 或邮箱方式登录 Codezzn，核对终端与页面的授权码，再允许当前 CLI 访问。CLI 不接收你的 GitHub 密码。不方便自动打开时加 `--no-browser`，手动打开终端显示的地址。

登录成功会记住服务器地址。局域网 HTTP 不是加密连接，必须每次显式加 `--allow-insecure-http`；生产环境建议 HTTPS。服务器公开地址与访问地址不一致会拒绝授权，不能用 localhost 绕过公开地址的回调规则。

进入终端后输入 `/agent` 查看可用智能体，输入 `/project` 列出已有服务器项目，再用 `/project 项目名称或ID` 选择项目，然后描述任务，例如：

```text
帮我写一份冒泡排序的 Python 文件，并读取验证内容。
```

需要创建项目、保存产物或执行受保护工具时，终端展示服务器的确认请求。工具审批会显示名称和参数，只有明确输入 `y` 或 `yes` 才允许。空输入默认拒绝。实际可执行能力和模型质量仍取决于服务器智能体配置。

## 常用操作

```powershell
# 单次对话；需要审批时不会自动允许
codezzn --allow-insecure-http -p "列出我有哪些项目"

# 继续当前目录最近的会话
codezzn --allow-insecure-http -c

# 指定会话 ID；无 ID 时从本地记录选择
codezzn --allow-insecure-http -r SESSION_ID

# 命名会话、选择服务器配置的模型
codezzn --allow-insecure-http --name "代码验收" --agent "coding agent" --model PROVIDER_ID/MODEL

# 机器可读的完整结果、逐事件 JSONL 输出
codezzn --allow-insecure-http -p --output-format json "介绍当前项目"
codezzn --allow-insecure-http -p --output-format stream-json "介绍当前项目"

# 只有明确指定的本地文件才会上传为上下文
codezzn --allow-insecure-http --attach "D:\work\example.py" "审查这个文件"

# 撤销本机 CLI 登录，不影响浏览器登录
codezzn auth logout --allow-insecure-http
```

交互命令包括 `/help`、`/new`、`/resume`、`/model`、`/agent`、`/project`、`/status`、`/stop`、`/files`、`/skills`、`/mcp`、`/exit`。`/skills` 和 `/mcp` 查看服务器资源，不启动 Windows 本地 MCP 进程。`/files` 查看待发送附件；带本地路径时显式上传附件。服务器项目产物继续在网页的 Files 面板查看和下载。每文件最多 10 MB，每回合最多 8 个、合计 20 MB。

Ctrl+C 请求取消服务器当前任务，再按一次立即退出。任务与交互答案在发出前保存请求 ID，断线后查询并复用同一请求，不创建第二次执行。`-p` 不会回答确认请求；返回 `requires_action` 后，使用 `-r SESSION_ID` 进入交互模式处理。

退出码：成功 `0`，失败 `1`，待确认 `2`，取消 `130`。JSON 格式的诊断不污染结果 stdout；日志写 stderr。输出只展示公开事件和回答，不展示隐藏推理。

## 安全与边界

Windows 登录凭证保存在 `%USERPROFILE%\.codezzn`，使用当前 Windows 用户的 DPAPI 加密；不支持明文降级。服务端只保存令牌哈希，令牌 30 天到期，退出可撤销。会话元数据按服务器、用户和当前目录分隔；本地会话记录含未完成提示词和审批答案，应视为私密数据。

本地文件路径不等于服务器项目路径。不要认为当前目录自动成为服务器工作区。没有新增 Windows shell 执行、权限绕过或 Claude 专有服务；可选 VS Code 轻量客户端桥见 [编码能力指南](coding-parity.md)，不提供本机自动改写或完整原生 IDE 集成。现有网页能力和旧 Python CLI 保留。

工程交互命令：`/plan` 查看计划，`/plan 目标` 请求制定计划，`/diff` 列出快照，`/diff chk_…` 读取 Diff，`/context` 查看预算与状态，`/review` 发起真实审查，`/rewind chk_…` 请求预览后审批回退。只读命令不调用模型；写入、命令与回退仍由原对话审批，`-p` 不自动确认。

出现 `server_url_mismatch` 时使用错误提示里的公开服务器地址；连接超时时检查服务器、网络和端口；模型认证或限流错误应在 Codezzn 网页的模型配置排查，不是 CLI 登录令牌的问题。

## 开发验收

```powershell
node --test tests/test_windows_cli.cjs
.\.workflow-venv\Scripts\python.exe -m pytest tests/test_cli_auth.py tests/test_cli_e2e.py tests/test_auth.py tests/test_user_isolation.py tests/test_conversation_sessions.py -q
```

端到端测试使用临时数据库、实际 HTTP 服务和 Windows DPAPI，通过受控模拟智能体检验登录、流式输出、续接和退出，不调用付费模型或真实 OAuth 提供商。
