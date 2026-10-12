# Codezzn 会话交互闭环

更新日期：2026-10-12。此实现将 Browser Use Cloud 已观察到的会话队列、交互卡片和用户反馈行为适配到 Codezzn。依据公开前端证据与官方开源实现，没有取得云端私有后端或系统提示词，不能声称内部算法完全相同。

## 实际行为

任务提交后先保存到服务端会话队列，再由后台执行。普通对话不再先调用额外的意图分类模型：主 Agent 结合历史、附件、当前项目、知识库范围及工具结果理解任务并决定下一步。明确的项目切换和文件去向规则仅负责确定保存位置；语义不明确时交给主 Agent，必要时调用 `ask_user`。

| 操作 | 行为 |
|---|---|
| 普通发送 / Enter | 空闲时执行；运行时排队，在上一轮结束后读取最新历史再执行 |
| 立即调整 | 等当前执行停止，再优先执行新指令；原有排队消息保留，可逐项取消 |
| 停止 | 取消当前执行或等待中的任务，关闭旧问题和检查点；已经完成的操作和文件保留 |
| 必须先回答的问题 | `ask_user` 暂停原轮，选项或自由文本以对应 `tool_call_id` 的结果恢复原轮 |
| 建议、方案、风险卡片 | `present_cards` 展示不阻塞的卡片；选择携带交互、卡片、动作标识作为后续消息排队 |
| 工具审批 | 单独明确允许或拒绝；普通聊天文本、建议卡片选择不构成工具授权 |
| 已选择项目 | 生成的产物默认保存到该项目，不再每轮询问；实际执行仍遵守工具和沙箱策略 |
| 未选择项目 | 明确产物任务先保存原请求，再展示项目去向问题；选择已有项目或新建后继续原请求 |
| 页面刷新 | 从服务端恢复消息、等待问题、卡片与队列；保留已接收的回答状态 |

界面保持 Codezzn 的浅色主题、常驻侧栏、侧栏对话历史和居中窄输入框。执行时仍可输入及上传附件；运行配置在有任务排队或等待回答时锁定，避免修改正在执行的上下文。模型选择只影响当前会话。

## 按需检索

现有 Agent 未设置 `retrieval_mode` 时和新建 Agent 均默认 `auto`。在智能体配置中可选择：

- `auto`：主模型看到已绑定知识库的名称、描述与 `knowledge_search` 工具，自行判断是否缺少相关私有或业务资料，再检索并使用来源。问候、身份和附件已经提供答案的问题通常跳过检索。
- `always`：每轮先检索已绑定知识库，再运行 Agent。
- `off`：隐藏并拒绝知识检索工具。

`auto` 的语义选择由当前模型完成，效果受模型工具调用能力、知识库描述和文档覆盖范围影响。需要确定每轮检索的业务 Agent 可显式选择 `always`。未绑定知识库不会自动搜索所有知识库；本地知识库与 RAGFlow 都通过已有检索服务接入。工作流的显式知识节点和禁用工具配置仍有效。

## 持久化与重试

新增 `chat_queue_messages` 和 `chat_interactions` 表，保留既有消息、工具审批和检查点。队列投递状态与执行结果分别记录，回答先落库后恢复执行。

消息和回答使用稳定的 `submission_id`。同一标识、同一内容只接收一次；同一标识对应不同内容返回 409。网络返回丢失时，前端先查询已接收状态；结果仍不明确时只允许显式重试原提交，不生成新的执行标识。已消费的回答即使后续模型调用失败也不会重新启用旧选项。

服务重启后，未执行的排队消息与未回答的等待状态可以继续。正在执行的轮次若中断则明确标记失败或取消，不盲目重放可能已完成的工具操作；回答续跑也同步更新队列执行状态，避免重启后会话一直显示运行中。此实现不承诺浏览器进程、远端工具或进行中的副作用跨重启精确续接。

后台运行需要正常 FastAPI lifespan。默认 Compose 使用单个应用进程；没有加入多进程分布式线程锁。

## 接口

所有接口沿用现有认证与租户隔离。

| 接口 | 用途 |
|---|---|
| `POST /api/threads/{id}/queue` | `content`、`attachment_ids`、`submission_id`；`interrupt:true` 表示立即调整 |
| `GET /api/threads/{id}/queue?submission_id=...` | 查询消息投递结果和去重状态 |
| `GET /api/threads/{id}/queue/{message_id}` | 查询单条任务的执行状态 |
| `DELETE /api/threads/{id}/queue/{message_id}` | 取消排队消息或对应活动任务 |
| `GET /api/threads/{id}/interactions` | 恢复持久化问题、审批、项目去向和卡片 |
| `POST /api/threads/{id}/interactions/{interaction_id}/answer` | 稳定提交标识及回答、选项、项目或卡片动作 |
| `GET /api/threads/{id}/events?turn_id=...&since=...` | 从持久序号增量恢复执行过程 |

旧 turn 和 approval 接口保留兼容性；新版对话页面使用上述队列与交互接口。

## 重新部署

当前环境已包含构建好的工作流前端。仅更新主应用，继续使用已有沙箱 overlay 和数据卷：

```powershell
cd D:\code-agent-rag-workflow
docker build --target prebuilt -t codezzn-app:local -t code-agent-rag-workflow-codezzn:latest .
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml up -d --no-build --no-deps codezzn
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml ps
```

工作流前端源码有变更时先在 `frontend/workflow-editor` 执行 `npm ci` 和 `npm run build`，再使用 `prebuilt`。首次部署也可使用 `runtime` 目标完成 Node 构建。不要只用基础 Compose 重建当前带沙箱的环境，否则会丢失 overlay 提供的 broker 配置。

部署前使用 SQLite 在线 backup 备份了 9 个数据库，位于 `data/backups/before-conversation-20261012T082057Z`；当时没有活动或等待中的会话。更新后浏览器用 `Ctrl+F5` 重新加载 `/workbench.html#chat`。

## 手动验收

使用已配置模型且有相应工具权限的 Agent，新建测试会话：

1. 绑定本地知识库、检索策略设为按需，问“你是谁？”，再问该知识库中具体制度或文档内容。查看执行过程，前者通常不检索，后者应出现知识检索和来源。
2. 发送“先问我想用快速排序还是归并排序，收到我的选择后再解释实现”。出现问题后刷新页面，选择答案，确认只继续一次且保留选择记录。
3. 运行一个需要多步执行的任务，在执行中追加“补充：最后用中文总结”，确认先排队再执行。另测“立即调整”和独立停止按钮。
4. 已选项目时发送“生成一个 Python 排序脚本并保存”，确认去向不再反复询问，工具审批仍生效，产物可在 Files/项目中下载。无项目时另测去向问题。
5. 发送“用建议卡片给我两个下一步方案，先不要执行”。分别选择卡片动作，确认选择作为后续会话消息，并且没有直接绕过工具审批。

自动验收覆盖 Chat Completions/Responses 检索策略、问题对应工具调用、续跑后的卡片保存、执行中追加、中断顺序、停止续跑、重启处理、去重、附件、项目产物和原有工作流。页面截图来自独立测试数据与模拟模型，不是对用户云端会话的抓取；本轮未用用户模型执行付费任务。

最终验证：211 项 Linux 后端测试通过，28 项前端测试通过；本次回归未运行 4 项无关帮助页或旧浏览器 UI 测试。主应用镜像 `70c37c18b8de88ceeea2fb8d2f05289e75248fd2e6564e6c2670aac426f362d9` 已部署，主应用和 broker 均健康；原有两张 GitHub 项目截图的认证下载及会话产物关联仍通过检查。

## 参考与证据

- [Browser Use Cloud Sessions](https://docs.browser-use.com/cloud/agent/sessions)：会话内队列和共享上下文契约。
- [官方 V4 OpenAPI](https://docs.browser-use.com/cloud/openapi/v4.json)：会话消息队列接口。
- [Human in the loop](https://docs.browser-use.com/cloud/agent/human-in-the-loop)：人工处理后在原会话继续的公开行为。
- [Browser Use Agent 源码](https://github.com/browser-use/browser-use/blob/5c892e013a73e6622e6f50336e1eb0aa2c4405f2/browser_use/agent/service.py)：锁定提交的工具循环、暂停和新任务处理；`add_new_task` 不直接提供可持久化的并发会话队列。
- [Agent SDK](https://github.com/browser-use/agent-sdk/tree/0cf7492fa07e2de3143ec1a81e7cef7acc6c212a)：顺序查询和会话上下文参考。
- [公开云端交互证据与分析](browser-cloud-intent-analysis.md)；[改造前差异基线](codezzn-intent-comparison.md)。
- [隔离会话问题卡片截图](../outputs/conversation-interactions/qa-question.png)：REA 被动截图证据 `ev_dfb393025c3f1bd8e8d5be6dcfb54a18cf40a07b37377823301e7b76f2dd8d42`。
