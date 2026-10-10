# 工作流画布验收记录

## 本地知识库与停止运行修正（2026-10-10）

- 当前账号三个知识库均为 RAGFlow 类型，模板选择现有资源因此访问远端；运行引擎本身支持本地资源，不要求 `192.168.33.17:9380`。未改写账号的资源、工作流版本或生产数据。
- 节点及统一知识库选择器增加「本地 / RAGFlow」标记和创建本地库提示。本地向量 / 重排序回退不再被当成整个检索失败，保留实际关键词召回与诊断；远端检索错误仍明确报错。
- 停止按钮放在测试面板标题右侧，增加「正在停止…」、成功 / 失败反馈、防重复提交。轮询不能把终止状态改回运行中；运行中不允许切换到其他历史详情，以免丢失当前运行的停止入口。
- 取消接口返回权威运行快照并支持重复取消；运行 / 节点 / 检查点同步标为 cancelled。执行器及任务队列禁止取消后的完成、失败或重试写入，并清理节点异步调用。
- 相关回归：63 passed / 1 deselected，排除 Windows 不支持 `os.chown` 的既有测试；前端 8 项测试及 TypeScript / Vite 生产构建通过。
- 停止测试通过实际 ASGI HTTP 接口和真实 PersistentTaskQueue，覆盖排队取消、运行中取消、重复取消、已完成任务、已有任务取消状态同步、节点取消后迟到返回 / 报错、禁止下游执行 / 任务重试、保留停止日志。
- 本地测试走真实上传解析、分块、SQLite 写入、知识服务分派、关键词检索及工作流传参；替换外部 Embedding、向量存储和回答模型以隔离测试。验证 RAGFlowClient 从未创建。本轮未以生产账号进行真实本地 Embedding / 模型端到端验收。
- 源码与生成的前端资源已更新，生产服务仍需重建后生效。浏览器工具连接此前关闭，本轮未进行新版停止按钮的交互式浏览器验收。

本地样本文档见 `samples/workflows/local-knowledge-test.txt`，具体设置、测试与停止步骤见 [智能体工作流说明](workflow-agent-routing.md#使用本地知识库测试)。

## 智能体与检索路由补全（2026-10-10）

- 确认实际账号保存的「条件分支演示」最新为 V3；输入「你是谁？」的运行记录没有任何 Agent 节点，只有固定文本输出。
- 新增检索决策 router 节点、智能体问答 / 智能分支问答模板、统一绑定 Agent 和知识库、原始演示图升级入口；Agent 节点支持由工作流控制检索与模型回答模式，原节点默认继承策略保持兼容。
- 最终相关回归 57 passed / 1 deselected（Windows 不支持 `os.chown` 的既有测试）；前端 6 项测试及 TypeScript / Vite 构建通过。覆盖模型真假路由、原 Agent 配置不变、JSON 分类输出校验、空回答与审批状态拒绝、检索错误诊断、版本保存兼容与原演示图识别。
- 真实模型调用：当前账号 Codezzn Assistant / qwen3.7-plus 判断身份问题无需检索，跳过知识节点并生成真实身份回答。记录见 `outputs/workflow-canvas/live-identity-test.json`；未创建正式工作流运行记录或覆盖用户保存的版本。
- 真正的外部 RAGFlow 分支尚未通过：容器内 `192.168.33.17:9380` 的 health / retrieval 均 ConnectError；新引擎将检索节点标记为失败并记录诊断。受控适配器验证了另一分支的检索调用、文档传入 Agent 和最终回答，不能据此声称外部服务已经连接成功。
- 浏览器验收工具仍返回 Transport closed，本轮未完成新版界面的交互式浏览器验收。

升级与测试步骤见 [智能体工作流说明](workflow-agent-routing.md)。

## 浅色主题修正（2026-10-10）

此前误以为基础 `workbench.css` 的深色配色是最终主题；实际工作台随后加载 `roboflow-theme.css`，主内容区为浅色。画布已统一为该主题的白色面板、`#f8f9fd` 背景、`#6d28d9` 主色，涵盖节点、工具栏、配置面板、测试面板、小地图、弹窗和运行状态；React Flow 和原生表单也明确使用浅色模式。

修正后 TypeScript / Vite 生产构建和 4 项前端图数据测试通过，生成资源已更新。浏览器检查工具返回 `Transport closed`，本轮未完成浅色界面的截图与交互验收；此前 `outputs/workflow-canvas/canvas-preview.jpg` 是修改前的深色预览，不代表当前主题。

## 已通过

- React + TypeScript 生产构建、4 项前端图数据测试，npm 依赖检查无已知漏洞。
- 最终本机相关回归：43 passed；排除 1 项依赖 Linux `os.chown` 的既有项目文件测试。
- 开发中 Linux 容器相关回归：60 passed，包含工作流、草稿、版本、项目 API、认证及租户隔离。
- 浏览器实际操作：从工作台新建进入画布；校验、保存 v1 并异步运行入门流程，得到「你好，Codezzn！工作流已成功运行。」；保存条件分支模板为 v2；输入「查知识库」和「你好」分别命中不同分支，另一输出节点正确跳过；查看节点日志。
- Docker `prebuilt` 目标成功构建完整镜像。默认 Node 构建目标拉取镜像时，当前机器访问 Docker Hub 的认证服务器超时，因此提供了可配置 Node 镜像与本机 npm 预构建方式。

最终新增后端测试覆盖：画布与未知配置字段保留、版本历史与冲突、Agent 草稿与画布互操作、草稿 revision 冲突、循环及无效配置拒绝、运行前资源检查、任务定义快照、真假条件分支与汇合、节点失败记录和恢复、嵌套变量与 MCP 参数、停止排队 / 运行中的任务、条件运算符、知识检索 → Agent → MCP 的受控适配器测试，以及账号隔离。

知识检索、Agent、MCP 的适配器测试使用受控替身验证调用参数与数据传递；没有使用真实模型 API 密钥或外部 MCP 服务。真实服务接入按使用说明中的知识库问答测试步骤验证。

## 尚未解决的环境 / 回归项

首次全量 Linux 回归为 144 passed / 2 failed：

1. 工作台登录跳转 URL 编码改变了既有行为，已修复，并在最终本机相关回归中通过 `test_public_landing.py`。
2. `tests/test_browser_use_integration.py::test_workbench_files_panel_tree_preview_and_download` 等待 `.chat-file-row` 可见时超时。该测试覆盖聊天文件面板；本次工作台改动集中在工作流入口和草稿画布链接。已准备修改前工作台脚本的对照测试，但后续 Docker CLI 调用不再返回，未完成基线比较，不能把这一失败直接认定为既有问题。

后续浏览器自动化连接也已关闭，因此后续修改主要通过 TypeScript 构建、图数据测试和后端 API 回归确认。运行停止、草稿 revision 和局域网 ID 兼容等收尾修改未再次进行交互式浏览器验收。

恢复 Docker 环境后，可单独复核聊天文件面板：

```powershell
docker compose exec codezzn python -m pytest tests/test_browser_use_integration.py::test_workbench_files_panel_tree_preview_and_download -q
```

本次验收使用了独立测试数据，正式 Codezzn 服务需要按 [部署与测试说明](workflow-canvas.md) 重新部署后生效。临时测试容器名称为 `codezzn-workflow-qa`，Docker 恢复后如果仍存在，可清理：

```powershell
docker rm -f codezzn-workflow-qa
```
