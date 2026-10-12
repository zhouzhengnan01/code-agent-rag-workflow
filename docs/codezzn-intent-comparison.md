# Codezzn 与 Browser Use Cloud V4 的输入决策对比

> 本文记录 2026-10-12 改造前的差异基线。新版对话已使用服务端队列与持久交互，不再以此处的前端预分类流程作为普通提交入口；当前行为见 [会话交互闭环说明](conversation-interactions.md)。

检查日期：2026-10-12。Codezzn 依据当前工作区源码；云端依据此前保存的公开前端脚本和官方 V4 契约。没有读取云端私有会话内容，不能确认其内部分类模型、提示词或检索策略。

## 当前 Codezzn 的完整链路

前端发送任务前调用 `/api/agent/intent`。该接口读取租户 Agent、线程模型覆盖、最近 6 条文本消息和真实项目列表，调用 `classify_intent`。分类先解析显式项目切换，再运行 `_obvious_intent` 规则；未命中时才调用配置中的模型，最多尝试两个候选，每条历史截取 1000 字符。

分类结果主要是 requires_project、kind、suggested_name、reason，以及项目切换/未知目标信息。前端据此显示权限、项目或保存确认；确认后提交真实 turn。工具与写入权限仍由服务端单独校验，分类不是授权。

主 Agent 结合系统提示词、历史、附件、项目与产物、技能等上下文进行工具调用循环。需要用户决定时可调用 ask_user；该动作经 approvals 表、tool_call_id 和 turn_checkpoints 暂停，用户回答以工具结果回到原轮继续。前置分类器没有替代主模型的目标理解与工具决策。

## 主要差异

| 维度 | Codezzn 当前实现 | Browser Use Cloud 已观察的实现 |
|---|---|---|
| 提交入口 | 先进行项目/产物分类，再选择确认或提交 turn | 公开前端提交 task/sessionId/model/附件，按会话状态选择 run 或 queue |
| 分类范围 | 主要判断是否产生持久文件、项目、工作流，及显式项目切换 | 未看到这条提交链路有独立 intent 标签；内部分类器未知 |
| 语义判断 | 正则规则优先；未命中再调用 LLM | 可见前端主要处理运行与交互状态；后端语义决策策略未知 |
| 用户追问 | ask_user 与工具审批复用 approvals 机制，保存 checkpoint 后恢复同 turn | Agency 卡片携带 deck/card/action 或回答上下文，通过原 session queue 送回；普通多轮可另建 run |
| 前置确认持久化 | pendingProjectTurn 是前端状态，真实 turn 尚未提交，没有对应服务端 checkpoint | Agency 卡片与反馈关联服务端事件及队列，可据已有反馈重建状态 |
| 执行中补充 | 聊天输入在运行时禁用；再次发送变成停止，服务端线程锁拒绝并发 | 官方 session queue 支持追加，及 interrupt 模式 |
| 选模型 | 会话覆盖、Agent 默认及配置的关键字/正则 model_routes 和回退 | 公开前端可提交选定 model/modelParams；内部路由未知 |
| 检索 | 普通 Agent 绑定 knowledge_ids 时新 turn 先检索；另有 knowledge_search 工具和工作流 router 节点 | 本次没有知识库策略证据 |

队列差异针对聊天会话，不代表 Codezzn 没有任何任务队列：Codezzn 已有 Agent/工作流后台任务队列与 SSE 事件队列，二者都不能直接等同于执行中的用户消息追加通道。

## 已验证的规则误判

只在本地运行 `_obvious_intent` 纯函数，没有模型调用或文件任务执行：

| 输入 | 当前规则结果 | 含义 |
|---|---|---|
| 截图是什么？ | requires_project=true，browser_artifact | 解释请求可能被提前带入产物确认 |
| 帮我看看这张截图为什么模糊 | requires_project=true，browser_artifact | 对既有图片的分析可能被当成生成截图 |
| 查看这段代码，并把分析结果保存为报告 | requires_project=false，answer | 复合任务的保存要求被规则漏掉 |

这些是前置分类错误，不代表最终主模型必然执行错误。服务端写入检查与 Agent 内部追问可能补救；代价是多余确认、阻断或分类与执行理解不一致。不能据此推定云端对同样输入一定正确。

## 检索需要单独说明

`agent.py` 的 Chat Completions 与 Responses 两种新轮分支都在 knowledge_ids 非空时先调用 search，之后才进行主模型推理。项目意图分类器不会输出 needs_knowledge，因此“无需项目”并不等于“无需检索”。

`workflows.py` 的 router 节点会清除知识库自动注入并禁用工具，让配置的普通模型根据问题、知识库名称/描述及路由提示输出 needs_knowledge、reason、query。是否真正执行检索由后续工作流连接决定。目前这不是已实现的 JEV prefill 分类；对当前 app/web 的有界搜索未发现 JEV 集成。

## 建议的优先顺序

1. 明确前置接口的范围是产物与项目检查。优化歧义/复合任务处理，确定性规则只处理高置信度情况，其余交给有充分上下文的判断；分类需要看附件相关信息。
2. 将普通检索支持配置为 always、auto、off；auto 使用独立检索判断或模型工具选择。工作流已有 router 可作为基础。
3. 为用户提问、权限审批、项目确认定义各自含义，并用统一交互记录保存 ID、turn、回答、消费与后续执行状态。保留现有权限校验和 checkpoint。
4. 为聊天会话增加消息队列、幂等键、查询状态及执行中补充/中断规则。不要直接复用后台 task enqueue 来假装完成同一会话的对话控制。
5. 决策使用已验证的项目与对话产物，继续保留当前已有截图上下文、工具结果和恢复能力。

## 源码索引

- `backend/app/intent.py:48`：规则；`:102`：完整前置分类。
- `backend/app/main.py:451`：意图接口；`:1579`：审批续跑；`:1726`：流式 turn 和线程锁。
- `backend/app/agent.py:69`：ask_user schema；`:358`：系统上下文；`:615`：用户答案；`:1232`、`:1417`：新轮自动检索；`:1538`：提问/审批保存。
- `web/workbench.js:1945`：提问卡片；`:2288`：提交链路；`:2385`：前置项目确认状态。
- `backend/app/workflows.py:178`：Agent/router 节点与检索判断。
- `backend/app/capabilities.py:87`：模型路由。

云端证据和限制见 `docs/browser-cloud-intent-analysis.md`；包括 REA Evidence ID、公开脚本 SHA256、卡片协议、消息队列及官方链接。
