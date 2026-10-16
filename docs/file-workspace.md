# Files 工作区验收（2026-10-16）

## 功能与范围

按照 clone-website 技能，对已登录的 Browser Use Cloud 会话实测文件树、文件标签、分隔线和代码样式后，增量修改现有 Codezzn。没有替换聊天背景、认证、项目权限、Agent 工具或业务流程。

- 桌面端聊天与 Files 之间的分隔线可拖动；方向键每次调整 2 个百分点，Home/End 到安全边界。只在本机存储宽度偏好。
- Files 为常驻标签。文件点击后在同一右侧面板打开独立、可关闭的标签；重复点击不会重复打开。Files 标签切回文件树。
- 文件夹使用橙色 Lucide 风格图标、缩进连线、展开箭头；Python 使用参考站观察到的同一 PNG 图标，现已本地化。
- 本地 PrismJS 1.30.0（MIT）提供多语言词法高亮，区分关键字、注释、字符串、函数、数字等。代码区使用参考页实测的 13px/19.5px、12px 内边距、白底配色。它是只读预览，不是完整 VS Code 编辑器或语义分析服务。
- 文件内容通过原有带认证的项目/对话 API 获取，不使用公开静态路径，也不把鉴权信息放入 URL。切换对话立即销毁预览状态；关闭标签会取消读取并释放图片对象 URL。
- HTML/SVG 源文件作为文本显示，不执行；大于 1MiB 的文本不内联预览，超过 200KiB 的文本降级为无高亮文本。常见位图最多 20MiB；未知二进制文件仅供下载。
- 文件下载与文件夹打包沿用原有接口。项目管理页原有预览入口不在此次调整范围。

## 验收方式

浏览器强制刷新后进入已有项目对话，点击 Files：

1. 展开/折叠文件夹，检查文件名、大小、图标及下载操作。
2. 点击 Python、JavaScript、Markdown 文件，检查在右侧标签打开且不出现抽屉/新窗口。
3. 在 Files 与文件标签之间切换，关闭当前或后台标签。
4. 拖动聊天/文件分隔线，再用方向键调整，检查聊天与文件区分别滚动。
5. 打开文件后切换到空对话，确认旧文件标签不会带入新对话，且空对话不显示 Files 按钮。

## 自动化证据

- `node --check web/workbench.js`：通过。
- `node --test tests/test_file_code_viewer.cjs tests/test_chat_frontend.cjs`：53 项通过。
- `pytest tests/test_file_workspace_browser.py tests/test_user_message_actions_browser.py tests/test_interaction_dock_browser.py tests/test_runtime_defaults_browser.py tests/test_coding_panel_browser.py tests/test_projects_api.py -q`：14 项通过、1 项跳过。
- Windows 浏览器测试设置 `CODEZZN_TEST_BROWSER_CHANNEL=msedge`，使用全新隔离配置，不使用用户已登录的浏览器配置。测试项目/API 为本地合成数据，无模型调用、无用户业务写入。
- 文件工作区测试覆盖真实鼠标拖动、键盘调整、标签去重/切换/关闭、原文保真、代码配色、HTML 不执行、读取失败重试、关闭标签后的迟到响应、跨会话清理，以及无非 GET 请求。
- `npm run build --prefix frontend/workflow-editor`：TypeScript 与 Vite 构建通过。
- 截图：`.workflow-qa/file-workspace-tree.png`、`.workflow-qa/file-workspace.png`（合成验收项目）。

## 已知的非本次引入测试失败

扩展执行 `tests/test_browser_outputs.py` 时，3 项独立 `screenshot` 工具的审批/存储预期失败，另外 7 项通过。这 3 项在修改前的镜像 `codezzn-app:before-file-workspace-20261016` 中，以无网络、无生产数据挂载的临时容器执行同一测试，结果完全相同：返回 `approval_required`，而旧测试预期文件存储信息或 `project_write_declined`。

本次没有为通过这些测试而放宽审批，也没有改动相关后端权限逻辑；不能据此声称整个项目测试全部通过。

## 部署

本次镜像构建成功，更新主服务 `codezzn`；保留修改前回滚标签 `codezzn-app:before-file-workspace-20261016`。部署前只读检查 9 个业务数据库，待派发/运行中的聊天任务和运行中的任务数均为 0。沙箱 broker 与其他服务不重启。

部署后 `/healthz` 返回 `status=ok`，主容器为 `healthy`；本地高亮脚本与 Python 图标均 HTTP 200。未认证访问 `/workbench.html` 仍正常重定向登录页；已从容器文件验证加载的是新版本页面及离线高亮资源。未冒用用户会话进行线上业务写入验收。
