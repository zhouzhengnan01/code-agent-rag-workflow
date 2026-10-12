# Agent 对话工作台

入口保持 `/workbench.html#chat`。本次在现有 FastAPI、JavaScript 和 CSS 上实现；工作流编辑器、知识库和其他资源页继续使用原有路由。

## 界面与交互

- 浅色界面，桌面导航宽 240px，始终显示图标和名称，不随鼠标移入展开。
- 历史位于“对话调试”的子菜单，支持新建、搜索、切换、重命名、归档、恢复及原有删除确认。
- 对话正文与输入框最大宽度 640px，居中排列。用户消息靠右，Agent 回复保持阅读列，运行细节沿用可展开记录。
- 输入框提供附件、模型、发送/停止，以及当前项目和 Skill/MCP。Enter 发送，Shift+Enter 换行；支持拖入文件及粘贴图片。
- 未发送的内容和附件在当前页面内按会话保留；页面重载不恢复未发送草稿。已发送附件和会话模型存入数据库。
- Files 面板默认关闭，通过顶部按钮打开；继续展示已有项目文件树、预览和下载。
- 浏览器截图现在提供对话预览和下载，已确认项目保存的截图登记到项目；没有关联项目的文件作为对话产物显示。审批续跑错误处理与找回历史截图的记录见 [截图与续跑修复](browser-screenshot-fix.md)。
- 768px 保留桌面导航，390px 使用按钮打开导航抽屉。手机关闭抽屉后，隐藏菜单不会进入键盘焦点顺序。

## 模型选择

下拉菜单来自已启用且配置完成的“模型接入”，不展示 embedding/rerank 模型和凭据。默认选项继承智能体的模型、路由和回退策略。显式选择后，仅当前会话使用该提供方和模型，不修改智能体默认设置，也不会在失败后悄悄切换其他模型。切回“默认”可恢复继承行为。

选择保存为 `threads.model_override`，刷新和分支会话保留。生成期间或等待工具审批时不能切换模型；已禁用的选择会明确显示“暂不可用”。

## 附件处理

支持 UTF-8 文本与代码、可提取正文的 PDF、DOCX，以及 PNG/JPEG/WebP 静态图片。扫描 PDF 当前需要先 OCR；Excel、PPT、ZIP、动画图片不在此次支持范围内。

单文件最多 10 MiB，每条消息最多 8 个文件、20 MiB 总大小及 10 万字符正文。文档正文真实进入模型上下文，图片通过多模态输入发送；会话后续轮次、分支和审批恢复保持这些上下文。

图片需要实际支持视觉输入的模型。常见多模态名称自动识别；自定义模型别名可在提供方配置 API 中设置 `vision_models: ["your-vision-alias"]`。不支持图片的主模型或备用模型会在保存消息前返回明确错误，前端保留输入以便更换模型。图片历史也会影响后续模型兼容性。

附件是会话资料，不会自动加入知识库或写进项目。它们按租户保存，下载经过认证；使用管理员访问密钥时，前端通过认证请求获取 Blob，不把密钥拼到下载地址。点击移除只移除草稿引用；保留文件以供已发送历史、分支及续跑使用，目前没有未引用附件的自动清理策略。备份时应同时保留数据库和 `chat_attachments` 目录。

## 重新部署

完整 Agent 部署需要同时加载基础与沙箱 Compose 文件。当前任务启动会通过沙箱检查 Git/worktree；单独启动基础文件会缺少沙箱地址和控制网络，即使浏览器任务也可能在准备工作区时失败。在 `D:\code-agent-rag-workflow` 执行：

```powershell
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml up -d --build
```

本次已经在本机构建并验证了 `code-agent-rag-workflow-codezzn:latest`。沙箱覆盖文件使用的应用镜像名是 `codezzn-app:local`，因此先给新镜像添加该标签。若代码没有再次修改，且现有 sandbox-broker 与执行镜像正常，可快速更新主服务：

```powershell
docker tag code-agent-rag-workflow-codezzn:latest codezzn-app:local
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml up -d --no-build codezzn
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml logs --tail 60 codezzn
```

请保留现有 `.env` 中的 `CODEZZN_SANDBOX_TOKEN`，不要因为缺少 URL 而重新生成令牌；覆盖文件会注入 `http://sandbox-broker:8090` 并连接控制网络。其他 Compose 覆盖文件也应继续沿用。本次没有重启正在运行的正式服务，也没有改正式数据。新字段和表会在服务启动时自动迁移；更新后浏览器按 Ctrl+F5。

离线前端构建方式仍可使用：先在 `frontend/workflow-editor` 执行 `npm.cmd run build`，再设置 `$env:CODEZZN_BUILD_TARGET='prebuilt'` 并执行 Compose 构建。

## 快速验收

1. 确认“模型接入”已有启用的提供方、有效凭据和模型列表，且智能体绑定了可用模型。
2. 打开“对话调试 → 新对话”，在输入框下拉选择一个已配置模型。
3. 创建 UTF-8 文件 `notes.txt`，正文填写 `本次验收口令：CHAT-640-2026`，点击回形针上传。
4. 输入“请读取附件，告诉我验收口令”，发送后检查答复及附件下载。刷新确认附件和模型选择仍保留。
5. 使用真实支持视觉的模型测试图片。对较长任务点击“停止”，确认可以再次输入和发送。
6. 在历史子菜单的 `···` 中重命名、归档，再在归档页恢复。切换会话确认输入框宽度和项目/模型上下文正确。

## 实现与验证记录

核心文件：`web/workbench.js`、`web/chat-workbench.css`、`backend/app/chat_inputs.py`，以及 Agent、线程 API 和数据库的小幅集成改动。图片解析增加 Pillow 依赖。

136 项相关后端测试在 Linux 镜像中通过，覆盖附件、模型、Agent、项目、工作流、知识库和用户隔离。9 项前端处理器测试通过，工作流 TypeScript/Vite 构建通过，Docker prebuilt 镜像构建通过。

浏览器在隔离数据库和受控模型响应下验证了上传、正文/图片进入 Agent 模型输入、模型持久化、附件下载、流式停止、历史搜索/重命名/归档、Files 开关及 1440/768/390px 布局。没有调用正式模型服务；部署后仍需用你已配置的端点完成上面的实际回答验收。

参考 Browser Use Cloud 的实时 DOM、尺寸和交互，保留 Codezzn 品牌及原平台能力；另外参考 [Claude 的文件交互](https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude) 和 [Manus 的附件与任务关联](https://open.manus.im/docs/v2/task.create)，将输入资料、会话与生成文件明确关联。未复制第三方账号、头像、费用或分享控件。

研究记录位于 `docs/research/cloud-browser-use-com-a80b83b3/`，源页面截图位于 `docs/design-references/cloud-browser-use-com-a80b83b3/`。本地验收截图位于 `outputs/chat-workbench/`。
