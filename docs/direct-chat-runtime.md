# 直接聊天、配置继承与按需技能

这是对 Claude Code 公开可观测交互模式的本地实现，不是复制私有 Prompt、私有代码或保证模型编码效果等价。Codezzn 的项目、沙箱、用户隔离、MCP 和审批恢复机制保留。

## 使用

1. 管理员/当前账号仍需配置可用模型和服务器 Docker 沙箱；“免组装智能体”不表示免配置 API 凭据。
2. Web 点“新对话”，默认运行配置是 Codezzn。直接问问题或提出任务，无需前往智能体管理页。Windows CLI 登录后运行 `codezzn`，不需要 `--agent`。
3. 普通读取/检索直接执行；写文件先确认项目去向，再根据具体工具请求审批。已有选定项目不会重复询问去向。未得到审批不得写入。
4. 输入 `/` 或点击输入框旁 `/` 查看当前可调用技能，选择后补充任务；`/skill`、`/skills` 也可打开列表。支持 `/技能名 参数` 与 `/skill 技能名 参数`。参数按原文传入，不作 Shell 命令拼接。
5. 输入框权限/模型下拉只覆盖本会话。齿轮“默认配置”可保存用户或当前项目的默认模型、权限和 Skill 发现方式。CLI `/permissions` 查看模式，后加 `default`、`acceptEdits`、`plan` 或 `inherit` 修改/恢复继承。

## 配置层次与兼容

内置默认 → 用户默认 → 目标项目默认 → 会话显式覆盖。会话模型选择优先于默认模型。只允许经认证配置 API 写入默认设置，不会执行项目文件中的权限指令。切换项目后重新解析目标配置和技能范围。

内置默认配置以账号独立数据库内的 `agt_codezzn_default` 记录存在，按需创建；不拷贝其他用户配置。旧会话绑定的自定义智能体不自动迁移，不因用户默认设置自动开启 Shell、放宽只读模式或扩大技能白名单。需要直接体验新流程请点“新对话”；高级自定义 Agent 仍可通过右上角选择或 CLI `--agent` 使用。

不提供 `bypassPermissions`；没有“完全不用审批”的默认模式。权限不是加载 Skill 时一次性授予。

| 模式 | 文件读/检索 | 工作区文件写入 | Shell/Skill 脚本/外部操作 |
| --- | --- | --- | --- |
| default | 按工具策略直接读 | 按工具策略审批 | 按工具策略审批 |
| acceptEdits | 同上 | 仅 `write_file/apply_patch` 和相应别名可自动接受 | 不因模式而自动批准 |
| plan | 同上 | 禁止 | 禁止执行命令及外部副作用；允许保存计划/待办及选择项目等对话控制状态 |

显式 `deny` 永远有效；显式 `ask` 必须得到此次操作的审批，不能被 `auto_approve` 或 acceptEdits 覆盖。原有沙箱、关闭的 Shell/浏览器能力和当前回合拒绝保存仍有效。运行或等待审批期间不能修改会话运行配置；更改用户默认只影响之后解析的回合，不代替待处理审批。

## Skill 包与发现

使用已有“技能”页导入 `SKILL.md` 或 ZIP 包（含 scripts/assets/references/skill.json），无需逐一绑定到默认 Agent。这里的“用户技能”指服务端当前账号安装的技能，不读取服务器 Windows 管理员目录，也不扫描其他用户的 `.claude`/`.codex` 目录。

默认自动发现启用的用户技能；资源设置 `project_id` 可限制为某个项目。自动发现关闭后仅使用显式绑定的技能。描述先进入上下文，完整指令和辅助文件通过 `skill_read_file` 读取；手动命令会直接加载指定技能的完整指令。单个指令有大小上限，依赖不会自动安装，脚本保持包完整性检查与容器执行。

支持 SKILL.md frontmatter 或资源同名字段：

```yaml
---
name: audit-code
description: 审查当前项目代码
disable-model-invocation: true
user-invocable: true
---
```

`disable-model-invocation: true` 表示仅用户主动调用，不进入自动发现的模型目录；`user-invocable: false` 表示不出现在手动命令菜单，但可由模型按需使用。命令名支持字母、数字、下划线、短横线；不符合格式的技能使用资源 ID。重名命令拒绝歧义解析，菜单自动使用唯一 ID。

手动调用在入队时解析到具体 Skill ID，保存到队列与恢复检查点；续跑重新检查启用状态、账号及项目范围，不依靠模型猜名称，不允许用 Skill 内容改变权限。

自动发现开启时，“添加”中的 Skill 是可选显式绑定；移除绑定不等于停用自动发现。要禁用某个 Skill，请在技能页停用，或通过用户配置 `disabled_skill_ids`；要仅使用勾选技能，在默认配置关闭自动发现。MCP 不会全部自动连接。

## API

- `POST /api/threads {}`：直接创建默认对话。
- `GET /api/chat/runtime?thread_id=...`：当前模式和受作用域约束的技能目录，不返回 API Key。
- `PATCH /api/chat/runtime/settings`：更新账号默认。
- `PATCH /api/projects/{project_id}/runtime-settings`：更新当前账号拥有项目的默认。
- `PATCH /api/threads/{thread_id}` 的 `capability_overrides.permission_mode/skill_discovery`：会话覆盖；与原 Skill/MCP 覆盖兼容。

默认配置允许字段：`provider_id`、`model`、`permission_mode`、`skill_discovery`、`disabled_skill_ids`。拒绝通过此接口提交 auto_approve、沙箱模式或其他绕过字段。均经过现有认证和租户数据隔离。

## 网页验收

1. 点“新对话”，不要打开智能体管理，发送“你好”。应直接回答，无 Skill/权限装配表单。
2. 发送“列出我有哪些项目”，应读取真实项目，不询问文件写入权限。
3. 导入一个带唯一描述的测试 Skill，不绑定 Agent。普通问候不能加载其完整正文；输入 `/技能名 按技能要求完成一个只读任务`，应使用完整指令。
4. 设置上述 manual-only 标记，普通对话不得自动使用；手动命令可以使用。停用后该命令应在入队前报错，不能偷偷使用旧内容。
5. `default` 模式请求创建测试 Python 文件，选择项目后必须等待写入审批；拒绝后不能出现新文件。允许后重新读取核对。
6. `acceptEdits` 模式请求新文件可不再逐个审批文件编辑；请求执行 Python/Skill 脚本仍要审批。不要用真实生产文件验证写入。
7. `plan` 模式请求写文件或执行命令必须被拒绝，读取仍可用；不能从审批接口绕过。
8. 用户设 acceptEdits，项目设 plan：选择该项目后应显示继承 plan。会话显式设 default 后显示 default。换项目检查其独立设置。
9. 两个账号各自安装技能，互相不可见；旧自定义只读 Agent 保持只读且 Shell 仍关闭。
10. Windows CLI 执行相同 `/skills`、`/技能名` 和 `/permissions`，确认实际工具仍在服务器 Docker 执行，不在本机执行。

测试使用独立临时数据库、模拟模型与浏览器页面，避免消耗真实模型额度或修改业务项目。
