# Browser Use Cloud V4 用户输入与交互分析

分析日期：2026-10-12。目标：https://cloud.browser-use.com/v4/session/77194822-a143-4d3e-9b9a-3db4ea3e56d2

## 结论及证据边界

可证实的公开链路是：用户任务文本 → 会话内 run 或消息队列 → 执行事件 → 对话/工具过程/文件/决策卡片 → 用户反馈回到原会话。

前端提交原始任务和上下文引用，不在这条可见提交路径上先产生独立的 intent 标签。对任务语义、工具选择和是否追问的解释，合理指向服务端模型与 Agent 执行循环；云端是否另有私有路由模型、分类器、系统提示词和澄清阈值，无法从前端证实。开源 Python Agent 只能提供可核对的实现参考。

本次没有读取指定会话的私有消息和实时请求。页面控制工具先发生超时，随后运行资源路径缺失；发现的浏览器进程未提供 remote-debugging 端口，因此未获得 REA 被动 CDP 采集条件。使用匿名 HTTP 获取该 URL 的公开应用壳及同源 JavaScript，得到 61 个脚本，另有 1 个脚本获取失败。未提交新的云端任务，没有抓取 Cookie、Token 或原会话网络正文。

从公开脚本选择三个与提交、事件和交互卡片直接相关的完整 chunk，使用 REA 进行静态分析：353,795 字节、3 个文件均解析成功。函数关系图受到资源预算限制而为 partial；不能把未匹配的图节点当成“没有该功能”。后续同时核对实际源码字节与官方接口说明。

## 1. 普通输入如何进入 Agent

提交处理器先检查文本非空、是否正在提交、附件状态与当前会话。普通空闲会话走 `POST /api/v4/runs`，请求体构造包含 `task`、`model`、`sessionId`，按需加入 `modelParams`、`attachedFileIds`。这里的 task 是原始用户文本。

前端把当前运行/交接状态与 Agency 卡片上下文用于选择提交通道；这属于执行状态分流，不能当成已证实的语义意图分类器。

官方说明同一个 session 可包含多轮 run，并保留对话与 workspace，仍可用时复用浏览器。新 run 的 task 因而能指向前一轮的页面、文件或动作。workspace 只保留文件，不能替代会话历史。

证据：`1513` chunk 的 composer 状态、`tf` 提交处理器及 `td` 队列处理器；[Create Run](https://docs.browser-use.com/cloud/api-v4/runs/create-run)、[Sessions](https://docs.browser-use.com/cloud/agent/sessions)。

## 2. 决策卡片如何与用户交互

找到明确的 Agency 卡片通道，不能据此声称所有云端追问都使用同一种机制。

1. 事件解析器接收 `agency.cards`，将其转换为用于展示的卡片条目。
2. 组件用 schema 校验 payload：version、cards、卡片 ID、标题、来源、actions 等；检查卡片 ID 和动作 ID 的唯一性。主版本每张卡片支持 1–4 个动作，并有跳过入口。卡片类型包括 idea、opportunity、risk、ready；这些是卡片展示分类，不等于用户意图标签。
3. 点击动作或填写文字后，前端生成带上下文的文本：包含 deck ID、card ID、动作 ID/可见标签或用户回答。文字回答包含 submission ID。
4. 标题与来源标签单独标记为不可信展示上下文，避免把卡片来源文字直接当作用户指令。
5. 通过 `POST /api/v4/sessions/{sessionId}/queue` 发送该文本，使用 `X-V4-Queue-Deduplicate: exact-text-v1`。请求体仍是 text，并非一个独立的强类型 answer API。
6. 查询队列和原会话反馈重建卡片状态；来源 run、后续 run 与消息状态用于区分仍在等待和已经完成。

这条链路解释了“用户选择为何能指向正确的卡片”：反馈不只有“继续”两个字，而是带有卡片归属与具体动作的用户消息。服务端如何将消息交付给正在运行的 Agent，公开实现细节仍未知；代码同时处理 deliveredInline 和后续 run 两种结果。

证据：`2986` chunk 中 webpack 模块 17338 的 schema、`W/B/q/H/J` 函数与卡片组件；`1513` chunk 的 `nz` 回调；`9399` chunk 的事件转换器。函数名为当前构建压缩名，不是稳定的官方 API。

## 3. 为什么不会靠反复点击恢复任务

可见代码区分 sending、accepted、uncertain、failed 等交互提交状态。卡片回调遇到网络异常或响应解析失败，会先 GET 当前会话队列，匹配文本及附件，判断此前提交是否已经接收；查不到时返回 uncertain，不能简单认定发送失败。卡片使用动作/回答键、submission ID、反馈记录防止重复操作。

官方队列契约也要求保留消息 ID、查询已有消息，而不是再次 POST 来轮询。忙时排队，空闲时派发；interrupt 可尽力取消当前 run，让新指令接续。公开 run 状态 queued/dispatching/running/completed/failed/cancelled 与前端卡片状态不同，不能混成一个“审批状态”。

证据：`1513` chunk 的 `nz/td`；`2986` chunk 的交互状态；[Queue Session Message](https://docs.browser-use.com/cloud/api-v4/sessions/queue-session-message)、[Sessions](https://docs.browser-use.com/cloud/agent/sessions)。

## 4. 模型如何判断回答、工具和追问

云端的具体系统提示词、工具清单和决策策略不可见。可以证实模型选项与任务一起发送，且前端消费 llm.request/llm.response、core.event、工具调用/结果、文本、执行状态和文件事件。由模型结合会话状态作下一步决策，是与这条链路吻合的推断；不能据此排除私有分类或路由步骤。

开源 Python Agent 的可核对参考链路是：任务、历史、浏览器状态、文件与截图构成上下文 → 提供可用工具 schema → 模型返回结构化下一步目标与 action → 参数校验和工具执行 → 结果回到下一轮模型上下文。

官方自定义工具文档提供 ask_human 示例：模型依据工具描述决定何时调用，用户回答作为 ActionResult 回到执行循环。这个示例不等于 Cloud V4 的私有 ask_user 实现，也不是当前 Python 默认工具。

来源：[Agent 服务](https://github.com/browser-use/browser-use/blob/main/browser_use/agent/service.py)、[消息管理](https://github.com/browser-use/browser-use/blob/main/browser_use/agent/message_manager/service.py)、[结构化输出](https://github.com/browser-use/browser-use/blob/main/browser_use/agent/views.py)、[工具注册](https://github.com/browser-use/browser-use/blob/main/browser_use/tools/registry/service.py)、[Add Tools](https://docs.browser-use.com/open-source/customize/tools/add)。

## 5. 对 Codezzn 的实现建议

以下为设计建议，不是宣称恢复了云端私有后端：

- 入口路由负责选择 Agent/工作流并读取会话当前状态；主模型负责结合历史理解目标、选工具、识别缺少的信息。
- 交互事件有明确的 question/card ID、turn ID、可见选项、用户输入和状态；普通聊天、任务排队和权限审批分别保留其真实含义。
- 用户选择回到原会话或 checkpoint，并携带当前问题的上下文；接收成功和后续执行成功分别记录。
- 提交使用幂等键。网络不确定时查询状态；任务失败可发起新的执行，已经消费的旧答案不重新提交。
- 文件、截图等真实产物和工具结果进入后续模型上下文，使“展示刚才的截图”能解析到既有文件。
- 如引入 JEV，可让其在有固定候选项的步骤判断检索、工具或工作流分支；自然语言澄清与最终回答仍交给有完整上下文的主模型。不能从本次证据推定 Browser Use Cloud 使用 JEV。

## 问题覆盖与证据索引

| 问题 | 状态 | 依据或缺口 |
|---|---|---|
| 用户任务如何提交 | 已回答 | 前端提交处理器＋官方 run schema |
| 卡片点击/文字反馈如何送回 Agent | 已回答公开前端通道 | schema、带归属文本、队列与状态处理 |
| 正在执行时追加指令如何处理 | 已回答公开契约 | queue、interrupt、消息 ID |
| 主模型怎样结合上下文选择动作 | 部分回答 | 云端契约与开源参考；私有策略不可见 |
| 指定会话某一轮为何追问 | 未解决 | 未读取私有消息与运行事件 |
| 是否有独立意图模型、其提示词和阈值 | 未解决 | 无服务端实现证据 |

本地采集和可复核源码在 `outputs/browser-intent-analysis-20261012/`：capture-manifest.json 保存 URL 与 SHA256，source-excerpts.json 保存相关区域，selected-source 保存三个完整 chunk，rea-summary.json 保存分析摘要及限制。

REA 父 Evidence：`ev_a9369bbda105896e3e49655a7b635c168eeb821481b747aa0f20adc347a05d88`；摘要 Evidence：`ev_42d3cab7f36a412aad4021a90603ce6a770331c2da40f2dc94a4096f1ffde59c`。

模块分页 Evidence：`ev_3a0cad6bc243e81c4d894978456717dfe09d95a34a5e64b0cc1a97a4061d413e`、`ev_8f2478f116abb7c2e7f5eed355ba00dc14a2c1614aea077ff75311b5ba705cc8`。对 /api/v4/runs 的图关系字符串追踪未匹配：`ev_90cc2efd8eb697a40b48f3a030e827907df04e42752d91d3aa0a42fa2e6bf2df`；源码中的该字面量与调用已人工核对，不把 partial 图的未匹配当成不存在。

公开脚本地址（当前构建可能随后更换）：

- https://cloud.browser-use.com/_next/static/chunks/1513-7210f0138a1a3d49.js
- https://cloud.browser-use.com/_next/static/chunks/2986-d13cd6f28b2c2f07.js
- https://cloud.browser-use.com/_next/static/chunks/9399-d2173213cb23a326.js
