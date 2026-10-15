# Codezzn Server Bridge (Windows)

这是轻量 VS Code 桥接，不是 Claude IDE 扩展的克隆，也不是本机编码执行端。

1. 安装 Node >=20，先完成 Codezzn Windows CLI 安装和浏览器授权。
2. 用 VS Code 打开此目录，按 F5 在 Extension Development Host 加载（也可自行使用 `@vscode/vsce` 打包；仓库不自动下载打包器）。
3. 在**用户**设置填写 `codezzn.server`；局域网 HTTP 需明确设置 `codezzn.allowInsecureHttp: true`。如 Node 非标准安装，填写 `codezzn.nodeExecutable` 和 `codezzn.cliScript` 的绝对路径。
4. 命令面板运行 `Codezzn: Open Server CLI`。CLI 复用自己的 DPAPI 凭据，不把 Token 交给扩展。
5. 选中代码，运行 `Codezzn: Review Selected Code on Server`。确认目标服务及字节数后，选区作为显式附件上传，启动新服务器会话。不要选择密钥。

扩展只读取用户级设置，不读取仓库指定的命令、服务器或凭据；在可信工作区中使用绝对 Node/CLI/PowerShell 路径，参数使用 PowerShell 单引号转义，避免调用 `.cmd` 壳。

选区先存扩展的用户存储目录，扩展停止时尝试删除；异常退出可能留下 `selection-*.txt`，可手动清除。它不会自动上传整个仓库，也不会把服务器改动自动应用到本地文件。

目前不提供本机 LSP、诊断回写、内联编辑或双向仓库同步。服务器工程面板 / CLI `/diff` 用于查看服务器代码差异，不能称为编辑器本机 diff 集成。
