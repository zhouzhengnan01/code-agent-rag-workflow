# Codezzn 工作流画布

## 进入和使用

登录工作台，进入「工作流」，点击「新建工作流」或已有工作流的「编辑」。项目中的工作流链接也进入画布。Agent 生成的工作流草稿可以点击「在画布中编辑」，配置后保存为正式工作流。

编辑器使用 React + TypeScript + React Flow，样式与 Codezzn 工作台的浅色主题一致：白色面板、浅灰画布、紫色主操作与选中状态。参考了 [Dify 的工作流编辑器](https://github.com/langgenius/dify/blob/main/web/app/components/workflow/index.tsx) 的节点配置和画布持久化交互，以及 [Langflow 的可视化编辑器](https://docs.langflow.org/concepts-overview) 的节点库、画布导航、测试和导入导出方式。画布交互使用 [React Flow 官方接口](https://reactflow.dev/learn)。

已支持：

- 点击或拖动添加节点，拖动端口连线，节点拖动、多选和删除；创建连线时拒绝环、重复连接和错误端口。
- 自动布局、缩放、适应画布、可导航的小地图、撤销 / 重做、复制节点。
- 节点配置面板：智能体选择、知识库多选、模板和上游变量选择器、条件判断、MCP 工具参数和工具列表加载、节点超时和重试。
- JSON 编辑、导入和导出；旧工作流没有坐标时自动布局，保留未知节点配置字段。
- 工作流名称、描述、最大并发数、关联项目、启停设置。
- 结构校验；运行前检查变量、必填配置、资源存在性及启用状态。未配置完资源的流程可先保存，补齐后再运行。
- 保存生成版本，版本历史载入，乐观锁防止旧页面覆盖别人保存的内容。
- 文本 / JSON 测试输入，异步运行、停止运行、最终输出、每节点状态 / 输出 / 错误 / 耗时 / 尝试次数、运行历史。
- 当前标签页的未保存内容恢复提示，离开未保存页面的浏览器提示。恢复缓存按登录账号隔离，保存在 sessionStorage 中。

默认新建流程为「输入 → 智能体 → 输出」。智能体问答与智能分支检索、Agent 工具 / 检索策略，以及旧分支模板升级步骤见 [智能体工作流说明](workflow-agent-routing.md)。

## 重新部署

### 通常的 Docker 部署

在项目根目录运行：

```powershell
cd D:\code-agent-rag-workflow
docker compose up -d --build codezzn
docker compose ps codezzn
docker compose logs --tail 80 codezzn
```

Dockerfile 会在 Node 构建阶段运行 `npm ci` 和 `npm run build`，把构建结果复制到 Python 服务中。浏览器加载的 React 和 React Flow 资源随服务本地提供，无需访问 CDN。构建需要拉取 Node 22 镜像并访问 npm registry。

保留现有 `.env`、`data` 和 `workspace`。不需要重建数据库；画布坐标存入现有资源 JSON，历史版本使用已有的 workflow_versions 表。

### Docker Hub 访问受限时：先在本机编译画布

本次开发环境拉取 Node 镜像时遇到了 Docker Hub 连接超时，可以使用已验证的预构建方式。需要本机 Node.js **22.12+ 或 24+**：

```powershell
cd D:\code-agent-rag-workflow\frontend\workflow-editor
npm.cmd ci
npm.cmd run build
cd D:\code-agent-rag-workflow
$env:CODEZZN_BUILD_TARGET = 'prebuilt'
docker compose up -d --build codezzn
docker compose ps codezzn
```

`prebuilt` 跳过 Docker 内的 Node 阶段，使用本机生成的 `web/workflow-editor/`。以后修改前端，需要重新执行 npm 构建。Python 基础镜像和后端依赖仍需已有缓存或可访问的下载源。

也可以在 `.env` 设置 `CODEZZN_NODE_IMAGE` 指向可以访问的 Node 22+ 镜像，并保持 `CODEZZN_BUILD_TARGET=runtime`，继续由 Docker 编译前端。若长期使用预构建方式，可将 `.env` 中的 `CODEZZN_BUILD_TARGET` 改为 `prebuilt`；只设置 PowerShell 环境变量时，它仅在当前终端会话中有效。

部署后打开工作台 `/workbench.html#workflows`，按 Ctrl+F5 刷新旧页面。

### 不使用 Docker

先执行上述 `npm ci` / `npm run build`，再按原来启动方式启动后端：

```powershell
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8080
```

前端开发源码在 `frontend/workflow-editor/src`。`npm run dev` 的 API 代理默认指向本机 8080 后端；生产环境始终使用 Python 服务提供的 `/workflow.html`。生成目录不提交到 Git。

## 第一个测试：不用模型或知识库

1. 进入「工作流」→「新建工作流」，点击「从模板开始」→「入门 · 文本处理」，显示「输入 → 欢迎文本 → 输出」。
2. 输入工作流名称，如「我的画布测试」。
3. 点击中间的「欢迎文本」，右侧应显示文本模板：`你好，{{input}}！工作流已成功运行。`。
4. 点击输出节点，其模板为 `{{prompt_1}}`，引用上游欢迎文本。
5. 点击「校验」，应提示校验通过。
6. 点击「测试运行」，在输入栏填写 `小明`，点击「保存并运行」。
7. 任务完成后，最终输出应为 `你好，小明！工作流已成功运行。`，三个节点日志应为「已完成」。
8. 拖动一个节点后保存，返回工作台再编辑，节点位置应保持；「版本历史」应显示新版本。

也可以导入项目内的 `samples/workflows/canvas-hello.json`。

## 第二个测试：条件分支

1. 新建工作流，点击「从模板开始」→「规则分支 · 路由演示」。
2. 条件节点默认比较 `{{input}}` 是否等于 `查知识库`。
3. 输入 `查知识库` 运行，输出「进入检索分支」，「直接回答」节点应标记「已跳过」。
4. 改为输入 `你好` 再运行，输出「进入直接回答分支」，「需要检索」节点应标记「已跳过」。

这个模板只验证条件路由，不会调用知识库。要实际检索，可把「是」分支连接到知识检索节点，再连接智能体和输出节点。

## 第三个测试：真实知识库问答

1. 在工作台配置可以正常调用的模型提供方和智能体。
2. 创建知识库，上传一份已知内容的文档并确认索引 / 文档解析完成。可以选择「本地 Milvus」，不需要 RAGFlow；本地配置、样本文档与停止运行测试见 [智能体工作流说明](workflow-agent-routing.md#使用本地知识库测试)。
3. 新建工作流，选择「知识库问答」模板。
4. 点击「知识检索」，勾选已有知识库；默认检索问题为 `{{input}}`。
5. 点击「智能体」，选择已有智能体。提示词中已经包含原问题与 `{{knowledge_1}}` 检索结果。
6. 点击「输出」，确认模板为 `{{agent_1}}`。
7. 校验、保存，输入一个可由文档回答的问题运行。
8. 在「节点日志」展开知识检索节点，检查召回片段；展开智能体节点检查回答，然后查看最终输出。

新的知识库问答模板默认将智能体设为「由工作流控制检索」，避免重复检索；工具模式默认「仅生成回答」。旧节点未设置这两个字段时仍继承原智能体配置。需要 Agent 执行工具时可在节点中改成「继承智能体工具与权限」。

## 数据格式与执行语义

工作流仍使用原生 `nodes` / `edges` 格式，新增独立的 `canvas` 元数据：

```json
{
  "name": "我的工作流",
  "enabled": true,
  "max_parallel": 4,
  "nodes": [
    { "id": "input_1", "type": "input" },
    { "id": "output_1", "type": "output", "template": "{{input}}" }
  ],
  "edges": [{ "source": "input_1", "target": "output_1" }],
  "canvas": {
    "version": 1,
    "positions": { "input_1": { "x": 50, "y": 100 }, "output_1": { "x": 360, "y": 100 } },
    "viewport": { "x": 0, "y": 0, "zoom": 1 }
  }
}
```

节点类型：

| 类型 | 配置与职责 |
| --- | --- |
| input | 返回本次运行的原始输入 |
| prompt | 渲染 `template` 文本 |
| agent | 通过 `agent_id` 调用智能体，渲染 `prompt` |
| knowledge | 检索 `knowledge_ids` 指定的知识库；`query` 和 `limit` 控制搜索 |
| mcp | 调用 `server_id` 服务的 `tool`，参数为 `arguments` JSON 对象 |
| condition | 比较 `value` 与 `equals`，支持 equals / not_equals / contains / not_contains / is_empty / not_empty |
| parallel | 等待所有上游结束并收集已经执行的上游结果数组 |
| output | 渲染 `template`，作为工作流最终输出 |

- 连线是执行依赖；输入内容需要通过变量引用。没有前置连线的节点会作为根节点执行。多个就绪节点按最大并发数执行。
- 条件边 `when: true / false` 对应条件节点的「是 / 否」端口。旧格式无 `when` 的条件边从底部「总是执行」端口发出。
- 汇合节点会等待所有上游结束；只要有至少一条已执行且满足条件的前置边，就执行该节点。所有前置分支跳过时，该节点也跳过。
- `{{input}}` 为原始输入；`{{节点ID}}` 为上游输出；`{{节点ID.字段}}` 和 `{{节点ID.0.content}}` 支持对象字段及数组下标。结构化输出在文本模板中转为 JSON。
- 已跳过分支没有变量结果。跨条件分支组合结果时，先使用并行汇合节点，再引用汇合结果。未产生结果的变量会明确报错。
- 并行流程优先引用具体节点 ID，避免 `{{last}}` 的批次顺序依赖。
- 一个输出节点执行时直接返回其结果；多个输出节点执行时返回以节点 ID 为键的结果对象；旧流程没有 output 节点时返回最后完成的结果。
- 入队时保存工作流定义快照，运行中编辑正式工作流不会改变已入队的任务；重试和检查点恢复也使用该快照。
- 运行中暂时锁定流程编辑；可停止后台运行。停止不能撤销工具已经完成的操作。
- 最多 100 个节点、300 条连线；循环、任意代码执行节点、实时多人协作和 Jev 模型决策节点不在本次实现范围内。

## API 与验证

- 原有资源 API 创建 / 更新 workflows 会验证结构并生成版本；画布更新发送 `expected_version`，版本冲突返回 409。
- `POST /api/workflow-validation`：检查结构、配置、变量和资源；返回校验结果与警告。
- `PUT /api/workflow-drafts/{id}`：在画布编辑 Agent 草稿；已有 save API 发布。
- `POST /api/workflows/{id}/enqueue`：保存定义快照并入队。
- `GET /api/workflow-runs/{id}`：节点运行状态、结果及版本。
- `POST /api/workflow-runs/{id}/cancel`：停止后台运行。
- `GET /api/workflow-runs?workflow_id=...`：按工作流过滤运行历史。
- 继续沿用已有租户认证与隔离，画布、资源、版本、草稿、运行记录均按账号访问。

开发检查：

```powershell
cd frontend\workflow-editor
npm.cmd ci
npm.cmd test
npm.cmd run build
cd ..\..
python -m pytest tests/test_workflow_canvas.py tests/test_agent_domain_loop.py tests/test_platform_capabilities.py -q
```

既有部分测试使用 Linux 的 `os.chown`，在 Windows 上请放进 Linux 容器执行相关回归。工作流画布新增测试可以直接在 Windows 执行。
