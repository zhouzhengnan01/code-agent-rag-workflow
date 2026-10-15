# Codezzn 编码能力对齐与验收

本次根据用户指定的 Claude Code Windows 可执行文件的可观测接口，以及 Codezzn 源码差距实施本地能力对齐。不包含恢复 Claude 私有提示词、私有模型、云端审查服务或宣称两者编码质量等价。

## 工程入口

- 网页：打开 `/workbench.html#chat`，选择已有对话后，顶部点击 **工程**。计划、质量门、快照 / Diff、上下文都读取当前租户、当前任务的服务端状态。
- 工程面板的写操作只填入可见对话草稿。你仍须点击发送，并在原工具审批卡中批准；按钮本身不会自动同意 Shell、文件写入、Hook 或回退。
- CLI：`/plan`、`/context` 读取状态；`/diff` 列出快照；`/diff chk_…` 查看真实差异；`/review` 请求独立审查；`/rewind chk_…` 先预览，再在原对话流程请求审批。`/plan 你的目标` 请求制定计划。
- 工程工具：`engineering_review`、`quality_discover`、`quality_run`、`plan_manage`、`hook_manage`、`task_checkpoint`、`task_diff`、`task_rewind`。

## 1. 从网页对话验收真实文件与测试

使用一个专用测试项目，不要在业务项目上尝试删除或回退。选择已配置模型、允许工作区写入和 Shell 的编码智能体，关闭“自动批准”，保留写入/Shell 的 ask 策略；模型供应商及 Docker 沙箱需可用。允许 Shell 不等于自动同意每次命令。

第一条消息：

```text
请创建一个独立测试项目 coding-acceptance，为冒泡排序编写 sort.py 和 tests/test_sort.py。
测试必须包含空列表、单元素、重复元素、负数与已排序输入，使用 Python 标准库 unittest，禁止额外安装第三方库。
先使用 plan_manage 制定计划，把 test 设为必要质量门，等待我审批计划。
写文件前使用 task_checkpoint 显式保存将修改的路径；每次实际写入和 Shell 执行仍等待我的审批。
最后通过 quality_run 运行 python -m unittest discover -s tests -v，展示真实退出码和测试输出。
未执行、失败或未覆盖的检查不能声称通过。
```

验收点：

1. 先出现计划及审批，不应把“制定计划”视为已经允许写文件。
   `plan_manage approve` 必须携带 `get` 返回的 `expected_revision`；等待审批期间计划变化，应拒绝批准旧版本而不是批错新计划。
2. 确认项目保存，文件必须出现在该用户、该项目的 Files 中。
3. 工程 → 计划显示步骤及必要检查；工程 → 质量门显示真实命令、stdout/stderr 和 exit_code。
4. 测试失败时不应声称完成；测试成功后修改源文件，旧结果不能继续满足同一任务的完成门禁。
5. 另一账号不得读取此对话状态、快照或文件。

## 2. 基线与新增回归

```text
修改代码前，使用 quality_run，baseline=true，执行名为 test 的检查：
python -m unittest discover -s tests -v。
然后改善排序实现，保持行为不变。修改后使用同名、同命令的 quality_run 再次验证，
分别报告新增失败、原有失败和不可比较项。不要把基线检查当作修改后的验收。
```

`baseline_comparison` 只有同名、同命令的结果可比较。已有失败不自动获准忽略；必要检查仍需要成功。

## 3. 独立代码审查

在测试项目中保留实际 Git 变更后发送：

```text
请使用 engineering_review 对当前项目的真实未提交变更进行独立审查。
执行正确性和安全/测试两个视角，再独立验证候选问题。
每个问题必须有真实相对路径、1-based 行号、严重程度和代码证据。
合并重复问题，过滤不存在的路径/行号/无证据指控，不修改代码。
没有模型、Git 不可用或覆盖不完整必须明确 partial/failed，不能把空 findings 当成已经全面通过。
```

审查会进行 Python AST 语法、冲突标记与常见密钥模式检查，再调用当前选定模型审查及验证。未执行程序，不能把审查当作测试或安全认证。模型调用会按供应商计费；单元测试使用假模型，不消耗费用。staged/base/range 审查应使用对应 Git 文件快照，不能混用另一份工作树代码。

## 4. 审批后安全回退

```text
请对 sort.py 和 tests/test_sort.py 使用 task_checkpoint 建立快照。
经我批准后，在 sort.py 新增一行注释，再用 task_diff 展示差异和 expected_hashes。
暂时不要回退，等待我确认。
```

打开工程 → 快照 / Diff，选择对应快照，确认真实差异。选择“在对话中请求回退”后发送草稿，并明确审批。应还原原始字节，包括 CRLF；快照中原本不存在、随后创建的文件，回退时会删除。

并发保护测试：在预览之后、批准之前，通过另一个会话修改同一个文件，再批准旧哈希回退。应返回 `conflict`，不得强制覆盖新修改。需要重新预览并重新审批。

边界：快照最多 100 个显式文件、单文件 1 MiB、总计 8 MiB；拒绝跨目录、`.git`、符号链接及 junction。不会还原外部系统、Shell 副作用或整个对话历史。外部进程在回退瞬间竞争写入仍需操作系统/工作区写入协调，不能当作事务数据库承诺。

## 5. Hooks 与失败阻止完成

```text
请使用 hook_manage 设置 Stop Hook：python -m unittest discover -s tests -v。
先展示命令并等待我批准。只允许使用当前 Docker 沙箱，禁止读取并自动执行仓库里的 Hook 配置。
```

测试时故意让一个测试断言失败，Stop Hook 应阻止任务被宣告成功。`PreToolUse` 和 `PostToolUse` 可按工具名匹配；失败需要报告而不是静默忽略。设置/清空 Hook 需要用户审批，只有此前批准的命令才可进入现有沙箱 runner。请勿把不可信命令配置为全自动 Hook。

移除测试 Hook：

```text
请列出当前 hook_manage 配置，并经我审批清空这些测试 Hook。
```

## 6. VS Code 轻量桥

参见 [桥接说明](../integrations/vscode/README.md)。它能打开服务器 CLI，以及经明确确认把当前选区作为附件发送给服务器审查。它不执行本机代码、不修改本机仓库、不扫描或上传整个工作区、不读取 CLI Token。

这不是本机 LSP、编辑器诊断回写、内联编辑或双向代码同步的替代品。服务器生成的变更仍需在服务器工程面板 / CLI 查看，不能称为完整 IDE 等价。

## 7. 轮次预算与重启恢复

对话达到当前智能体的工具轮次预算时，不应直接丢出“达到最大工具调用轮次”并遗失任务；应显示“继续执行 / 停止任务”的问题卡。选择继续会复用相同的 turn、工具结果、上下文与已有文件，增加一段执行预算，所有原工具审批仍生效。选择停止会保留已有产物，不继续调用模型。

可将测试智能体的工具轮次暂时调小，发送需要多个工具的任务来触发；验收后恢复原配置。连续点击或网络重传同一回答不能执行两次；CLI 非交互 `-p` 应输出 `requires_action` 而不是自动继续。

服务关闭并非用户取消。服务重启时，有有效运行检查点且没有结果不确定副作用的对话，会以原队列 ID / turn 自动恢复，不重复插入原用户消息。已经等待审批或预算回答的任务继续等待。没有有效状态时仍明确失败；若进程在 Git push、外部写入等副作用开始后中断，无法确认结果，则标记需人工检查，绝不自动重放。

自动化恢复用临时测试实例验证；不要通过强行停止生产实例来做验收。维护者可运行 `tests/test_coding_runtime.py`。

没有对话窗口的独立后台任务耗尽预算时保留在 `waiting`，任务页可点击“继续执行”对同一个 task_id 增加一段预算，不能被当作已完成。后台文件任务可在创建任务时选择产物项目；它没有即时会话审批通道，需提前配置最小必要工具策略。对话/子任务已在问题卡等待时，应回原对话回答，任务页不会绕过审批。

## 自动回归（维护者）

在项目根目录运行，不访问业务项目，不调用付费模型：

```powershell
.workflow-venv\Scripts\python.exe -m pytest tests/test_engineering.py tests/test_coding_runtime.py -q
node --test tests/test_windows_cli.cjs tests/test_vscode_bridge.cjs tests/test_coding_panel.cjs
```

工程测试使用临时目录和隔离 SQLite；CLI 测试使用本地假 HTTP 服务。VS Code 参数安全测试会运行一条无害 PowerShell → Node 参数回显探针，不执行模型、不登录账号。

## 已知边界

- 工程能力复用本地 Codezzn 与 Docker，并不获得 Claude 的专有模型、云端多智能体服务或质量保证。
- 多语言语义质量取决于实际安装、隔离运行的语言服务器和选定模型；确定性 AST 检查不是所有语言的编译器。
- 相同工具和提示词不能保证相同结果。应使用相同仓库、任务与测试对照验收，不能声称达到未测的百分比。
- 页面入口、CLI 和 VS Code 扩展不授予额外权限；原项目隔离、工具策略、审批及取消机制必须继续生效。

## 8. 本次覆盖清单和证据边界

参考对象是本机 Claude Code **2.1.140**，PE SHA-256 `fcfe90297861b1bcfa581d7db645ec8a71984baed3b1c44d28032650baa2617c`。REA 核实文件身份；实机 `--version` / `--help` 输出保留在 [参考证据](research/claude-code-cli-20261013/evidence.json)。帮助声明不等于已实际运行其每项功能。没有解密、恢复或使用 Claude 私有 Prompt，没有调用 Claude 的收费推理或云端审查。

| 对齐方向 | Codezzn 本次实现 | 不能冒称的范围 |
| --- | --- | --- |
| 计划与验收 | `plan_manage`、版本审批、必要质量门、基线对比、Stop Gate | 模型可能未遵守指令，需实测；未设置必要检查不等于已经全面测试 |
| 代码审查 | 真实 Diff、确定性检查、双视角模型审查、独立证据验证 | 不是 Claude 云端 ultrareview，不保证发现所有问题 |
| 编辑与回退 | 原子写入、可选 `expected_hash`、快照、Diff、CAS 回退 | 不回滚外部系统、Shell 副作用或整个对话历史 |
| 任务工作区 | Git worktree / 非 Git 有界快照、冲突校验发布、独立子任务 Turn | Git 提交留在任务分支，不自动合并；不是 OS 级跨项目 Shell 沙箱 |
| 上下文和工具发现 | 结构化摘要、可选语义摘要、MCP schema 按需发现、Skill 渐进读取 | 估算不是精确 tokenizer；不能恢复模型私有思维链 |
| 多语言与开发环境 | 增量索引、Python AST、沙箱 JSON-RPC LSP、可选 Node/Python 镜像 | 非 Python 回退索引明确 heuristic；LSP 依赖真实语言服务安装 |
| 后台命令 | `terminal_start/status/logs/cancel`、持久身份和增量日志、跨轮查询 | 非交互 PTY；Broker 重启会中断其容器任务，不自动续跑任意命令 |
| 多智能体 | 原有持久委派、独立任务副本/运行记录、`team_send/receive` 持久邮箱 | 邮箱不自动唤醒空闲成员；并行审批仍需用户处理 |
| GitHub 工程协作 | PR 读取/创建、评论、CI 状态/日志/重跑、按租户凭据 | PR 文件/评论前 100 条，日志受限；OAuth 登录不自动授予仓库 Token |
| 扩展与 IDE | Skill 完整包校验/依赖预检、Hooks、Web/CLI 工程入口、VS Code 轻桥 | 不自动装不可信依赖；不是完整 Claude 插件市场/原生 IDE 同步协议 |
| 恢复 | 每轮/每工具状态保存、结果复用、预算问题卡、安全重启恢复 | 不确定副作用失败需人工检查，不承诺 exactly-once 外部执行 |

## 9. 工作区、后台命令和团队的网页验收

在专用测试项目中发送：

```text
请读取当前项目已有文件，使用 read_file 返回哈希。对 sort.py 使用 task_checkpoint。
给文件增加一条注释，调用 write_file 或 apply_patch 时携带 expected_hash，然后重新读取验证。
分别使用 search_code 和 git_status 检查，确认文件工具、搜索、测试和 Git 都在同一执行工作区。
展示实际任务工作区和 canonical 项目位置，不把它们当作同一个目录。
```

已有有效 HEAD 的项目应显示 `git-worktree`；普通新项目显示 `snapshot`，不是虚构的 Git 仓库。项目目录位于当前租户 `projects/<project_id>/`，任务副本在 `.codezzn-execution/`，不可写的发布元数据在 `.codezzn-coding/`。不要手动删除这些目录来“修复”冲突。快照预算 20,000 文件 / 256 MiB，不复制 `.git`、依赖、缓存目录。源码中依赖目录被排除不代表依赖已安装。

并发测试：两个独立会话读取同一项目的同一文件后分别修改。第一个发布成功，第二个必须报告 `CodingWorkspaceConflict`，保留副本，不能静默覆盖。需要人工/Agent 重新读取当前文件并解决冲突，不自动选择胜者。

后台命令测试：

```text
经我批准，用 terminal_start 启动 Python 标准库命令，每秒打印一次进度，运行 10 秒。
不要用 run_shell 阻塞等待。拿到 task_id 后使用 terminal_logs 增量读取，再使用 terminal_status 确认退出码。
```

继续发送“查询刚才 task_id 的日志”，同用户、同项目的新轮次应仍可读取。启动另一条 30 秒命令，再经批准 `terminal_cancel`，确认真实取消；不是只改变页面状态。后台写出的文件在完成状态查询时做冲突检查后登记到 Files。日志和命令有边界，不会返回环境变量或开启 Windows 本机执行。

团队需先在智能体配置中授权成员。再发送：

```text
请把只读代码审查委派给已授权的审查成员，把测试建议委派给另一个成员。
使用独立 task_id / turn_id；通过 team_send 发送任务背景，成员使用 team_receive 读取。
通过 task_status 汇总证据。不要让多个成员直接覆盖共享文件；修改发生发布冲突时停止并报告。
```

## 10. LSP 和 Skill 环境验收

准备好下面的 Node/LSP 镜像后，在左侧 **LSP 服务** 新建资源，传输方式选 **Docker 沙箱**，语言服务别名填 `python` 或 `typescript`，然后在编码智能体中勾选该服务。管理员映射决定运行哪个程序，用户表单不能自行指定 executable。

```text
请在当前项目创建一个小 Python 模块，使用 code_index / code_symbols / find_references / call_graph 分析。
修改一个函数后再次查询，确认索引自动更新。
使用已授权 LSP 的 textDocument/didOpen 和 textDocument/definition 查询真实定义，报告原始 URI/位置与覆盖限制。
诊断未完成必须说明 incomplete，不要用符号字符串搜索冒充编译器诊断。
```

LSP 单请求 25 秒；didOpen / 全量 didChange 文档缓存最多 32 个、每文档 12 KB。重命名返回经过路径校验的 WorkspaceEdit 建议，**不会自动应用**，实际改写仍走审批。多租户禁止在主应用容器启动任意 stdio 子进程；HTTP 代理也要管理员 allowlist 和 Token。

给 Agent 授权一个完整 Skill 包后发送：

```text
请先用 skill_read_file 读取这个 Skill 的 SKILL.md，再用 skill_check_environment 检查 manifest 声明的依赖。
缺少依赖、版本范围无法判断或 Node 未安装都明确报告，禁止自动联网安装。
只有我批准后才能 skill_run_script 运行已校验包 scripts/ 下的 Python、Shell 或 JavaScript 脚本。
```

## 11. 上下文、GitHub 和部署

智能体编辑表单提供上下文估算预算、语义压缩、MCP 按需加载和内置工具按需加载。编码角色默认对 MCP 延迟加载；Agent 用 `tool_search` 搜到的 schema 会进入后续模型请求。Skill 默认先加载名称/描述，再按需读取正文。语义压缩调用当前模型，可能计费，20 秒超时或模型失败时保留结构化摘要。主消息中的网页、代码和摘要都不能升级为系统指令。

GitHub 登录只做身份认证。PR/CI 需要管理员单独在 `.env` 配置 **内部用户 ID → 最小权限仓库 PAT**：

```dotenv
CODEZZN_GITHUB_USER_TOKENS={"usr_your_internal_id":"github_pat_replace_me"}
CODEZZN_GITHUB_ALLOW_SHARED_TOKEN=false
```

不要把 Token 发送给 Agent 或提交到 Git。只读 PR/CI 测试不需要授予写仓库权限；创建 PR、评论和重跑 CI 仍要批准。测试仓库先设置实际 GitHub origin，再让 Agent 调用 `github_read_pr`、`github_ci_status`、`github_ci_logs`。重跑工作流、push 或发评论会产生真实外部变更，请仅使用测试仓库。

部署前先备份数据库和工作区，安排无活跃任务的维护窗口。本次同时更改主应用和 Broker，**只刷新网页或只重启主应用不够**。Docker Desktop 必须处于运行状态。

```powershell
cd D:\code-agent-rag-workflow
# 可选：需要 Node 和真实 Python/TypeScript 语言服务器时构建
docker build -f Dockerfile.sandbox.node --build-arg INSTALL_LANGUAGE_SERVERS=true -t codezzn-sandbox-node:local .
```

选择该镜像时在 `.env` 填写，原有 `CODEZZN_SANDBOX_TOKEN` 保持不变：

```dotenv
CODEZZN_SANDBOX_IMAGE=codezzn-sandbox-node:local
CODEZZN_SANDBOX_MAX_TIMEOUT=3600
CODEZZN_LSP_SERVERS_JSON={"python":["pyright-langserver","--stdio"],"typescript":["typescript-language-server","--stdio"]}
```

如果不构建新镜像，可以保留原有 Python 沙箱；Node/LSP 相关能力会报告缺少服务，不能声称已启用。

```powershell
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml build codezzn
if ($LASTEXITCODE -ne 0) { throw '构建失败，停止部署；不要继续启动旧镜像。' }
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml up -d --no-build --no-deps --force-recreate codezzn sandbox-broker
if ($LASTEXITCODE -ne 0) { throw '容器更新失败，请检查 Compose 状态和日志。' }
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml ps
```

构建需要镜像仓库和包源网络；失败时不要用 `--no-build` 冒充已经更新。容器健康后在浏览器 Ctrl+F5，进入历史对话，确认顶部出现“工程”按钮，再按第 1 节的标准库排序任务验收。安装过 CLI 的机器可重新运行 `scripts/install-windows-cli.ps1` 更新；VS Code 轻桥的安装/F5 方法见 `integrations/vscode/README.md`。

两个服务共用 `codezzn-app:local`，因此只构建 `codezzn`，成功后同时更新主应用和 Broker，避免分别构建同一标签。Broker 的构建参数与主应用保持一致，包括 Node 镜像和构建 target。

如果报错发生于 `load metadata for node:22-bookworm-slim`，且内容是访问 `auth.docker.io/token` 超时，这是镜像仓库连接问题，不是 Python/npm 代码报错。先用 `docker image ls` 查看本机已经缓存的完整标签；浮动标签与具体版本标签不通用。例如本次机器缓存了 `node:22.20.0-bookworm-slim`，在 `.env` 设置 `CODEZZN_NODE_IMAGE=node:22.20.0-bookworm-slim` 后已完成主应用构建。该版本仅为当前网络故障下的已验证构建方案，不是最新安全版本推荐；网络恢复后应更新到受维护、经过验证的 Node 镜像版本。不要加 `--pull` 或删除缓存后期待离线构建；首次依赖安装或缓存失效仍需要相应包源网络。

新增自动回归集合（不调用真实模型或 GitHub）：

```powershell
.workflow-venv\Scripts\python.exe -m pytest tests/test_coding_integration.py tests/test_coding_workspace.py tests/test_coding_runtime.py tests/test_coding_api.py tests/test_engineering.py tests/test_coding_language_terminal.py tests/test_coding_skill_runtime.py tests/test_coding_collaboration.py -q
node --test tests/test_coding_panel.cjs tests/test_lsp_frontend.cjs tests/test_windows_cli.cjs tests/test_vscode_bridge.cjs
```

Windows 维护者已有 Edge、但未安装 Playwright Chromium 时，可以显式设置 `CODEZZN_TEST_BROWSER_CHANNEL=msedge` 和 `CODEZZN_BROWSER_CHANNEL=msedge` 运行浏览器测试；创建的是干净的隔离上下文，不复用个人浏览器登录资料。默认生产容器仍使用镜像内 Chromium。

## 本轮实测记录（2026-10-15）

- 使用现有应用镜像为基础构建独立 QA 镜像，复制本轮源码，挂载临时数据目录，以 `--network none` 执行整套 Python / 浏览器回归：**382 passed，1 skipped**。跳过项为 Linux 无法运行的 Windows CLI 环境测试；Windows CLI 另行实测。
- Windows Node 回归（聊天、工程面板、LSP 配置、CLI、VS Code 参数桥）：**60 passed**。其中 DPAPI 凭据与 PowerShell 参数边界使用真实 Windows 运行时。
- 新工程面板在真实 Edge 浏览器上验证：打开、读取计划、查看 Diff、填入回退草稿；没有自动发送消息或批准写操作。
- 独立 Docker Broker + 新建临时卷的真实冒烟：执行 UID 10001、增量日志、命令取消后容器清理、只读挂载拒绝写入均通过。未访问业务数据库、未调用付费模型或 GitHub 写接口。临时容器/卷已清理。
- 可选 Node/pyright/TypeScript 镜像提供构建入口，但本轮**没有完成它的实际镜像构建和真实语言服务器安装验收**；LSP JSON-RPC 桥使用协议 fixture 验证，不能宣称你的生产环境已经装好这些语言服务。
- 未替换运行中的 Codezzn / Broker 容器，未修改现有智能体的模型、账号或授权配置。生产发布仍按上文维护窗口执行；QA 镜像带临时数据配置，**不能直接标记成生产镜像使用**。

### 开发沙箱构建修复与补验收

随后在本机复现 Debian HTTP 软件源返回 502：同一基础容器访问 `http://deb.debian.org/debian/dists/bookworm-updates/InRelease` 失败，官方 HTTPS 对应地址和安全源均返回 200。下载 InRelease 失败后的“repository is not signed”不是放弃签名校验的理由。

`Dockerfile.sandbox.node` 现已将官方源 URI 切换为 HTTPS，保留 suite、Signed-By 和系统信任链，配置下载重试和 HTTPS 超时；软件源索引失败时终止构建，不接受不完整更新。没有使用 `trusted=yes`、`--allow-unauthenticated` 或关闭 TLS 校验。

已实际执行完整构建并得到 `codezzn-sandbox-node:local`，自检版本为 Python 3.12.12、Node 22.20.0、npm 10.9.3、pyright 1.1.390、TypeScript 5.7.2、typescript-language-server 4.3.3。使用 UID/GID 10001、禁网、只读根文件系统和独立 `/tmp` 启动真实 Python / TypeScript 语言服务器，经项目 JSON-RPC 桥查询 `documentSymbol` 均返回测试函数。该补验收使用真实语言服务，替代此前“只验协议 fixture”的覆盖限制；不等于已经为生产账号绑定 LSP 配置或重启生产 Broker。
