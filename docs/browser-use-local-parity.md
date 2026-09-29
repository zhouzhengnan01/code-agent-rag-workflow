# Browser Use 开源版与 Codezzn 本地能力对照

对照基准：[Browser Use 官方默认工具清单](https://docs.browser-use.com/open-source/customize/tools/available)和[开源 Agent 系统提示词](https://github.com/browser-use/browser-use/blob/main/browser_use/agent/system_prompts/system_prompt.md)。此文只描述开源版默认动作，不将 Browser Use Cloud 私有能力算作已实现。

| 开源版默认动作 | Codezzn 工具 | 本地行为 |
| --- | --- | --- |
| `search`, `navigate`, `go_back`, `wait` | 同名 | 租户/对话隔离的本地 Chromium |
| `click`, `input`, `upload_file`, `scroll`, `find_text`, `send_keys` | 同名 | 页面状态索引或定位器；上传须单独审批 |
| `evaluate` | 同名 | 在当前页面运行 JavaScript，受浏览器工具策略约束 |
| `switch`, `close` | 同名 | 管理当前本地浏览器会话的标签页 |
| `extract` | 同名 | 读取页面证据，再由当前配置的模型按查询提取；模型失败时返回原文与错误提示 |
| `screenshot` | 同名 | 截图存入本地工作区或经确认的项目 |
| `dropdown_options`, `select_dropdown` | 同名 | 读取与选择下拉选项 |
| `read_file`, `write_file`, `replace_file` | 同名，另有 `read`/`write`/`edit` 别名 | 复用 Codezzn 项目边界、审批和文件版本记录 |
| `done` | 同名 | 明确结束任务；要求真实文件的任务不能仅靠回答宣称已保存 |

编码智能体的运行时系统提示词参考开源版的完整目标、逐步评价、短期记忆、下一目标、行动、结果验证和失败后改换策略等规则，同时保留 Codezzn 的项目确认、审批、隔离工作区和不可信网页内容边界。它是对公开规则的本地适配，不是 Browser Use Cloud 的私有原版提示词。

本地 Chromium 不提供 Browser Use Cloud 的托管浏览器、代理、隐身基础设施、自动 CAPTCHA、云录屏或云端工作区。可用模型、工具策略、最大轮次和浏览器开关仍以当前 Codezzn 智能体配置为准；工具注册不等于跳过审批。
