# 本地知识库文档上传与入库

## 本次修复

原上传入口引用了不存在的 `cache.knowledge`，点击时出现 ReferenceError，尚未打开文件窗口。改为使用工作台实际的 `state.cache.knowledge`，并将文档界面独立为 `web/knowledge-documents.js`。样式沿用浅色工作台，资源随应用提供。

文档处理参考 [Dify 1.9.1 IndexingRunner](https://github.com/langgenius/dify/blob/1.9.1/api/core/indexing_runner.py) 的提取、转换分块、索引阶段和持久化失败记录，以及 [DatasetService](https://github.com/langgenius/dify/blob/1.9.1/api/services/dataset_service.py) 的文档与任务管理方式。复用 Codezzn 的 SQLite 租户存储和 PersistentTaskQueue，没有引入 Redis / Celery 部署依赖。

## 上传步骤

1. 在「知识库」中新建或编辑，后端选择「本地 Milvus」，配置有效的 Embedding 提供方、模型和对应维度。
2. 点击「上传文档」，选择或拖入文件，支持 TXT、Markdown、PDF、DOCX、JSON、CSV。一次最多选择 20 份文件；默认每份最多 10 MB，可用 `CODEZZN_MAX_UPLOAD_BYTES` 调整服务器限制。
3. 点击「上传并入库」。文件传输进度和后台处理阶段分别展示。传输期间不允许关闭；提交后可以关闭面板，后台继续处理。
4. 后台依次显示等待处理、解析文档、清洗与分块、生成向量、写入索引。只有实际索引和 SQLite 提交成功后才显示「可检索」。
5. 打开「文档状态」查看处理记录、失败原因、文档片段数、估算 Token 数和版本。处理中自动刷新；失败时可以修正模型配置后点击「重试处理」，复用已保存的原始文件。
6. 点击「查看片段」确认实际提取内容，支持分页；再用「测试检索」输入一个文档内问题。

同名文档按原有规则作为新版本替换。新向量全部写入后才激活新片段；失败时原有可检索内容不受影响，避免出现上传了一半就覆盖旧资料的情况。并发替换会通过 revision 检查拒绝过期提交。

扫描 PDF 没有可提取文字时明确提示先做 OCR。本版本不包含 OCR 服务，也不支持老式 `.doc`、Excel 或图片直接解析。DOCX 提取段落与表格单元格中的文字，PDF 提取文字；版面结构、多栏表格及图片语义需要额外解析服务。

## 工作流测试

可上传 `samples/workflows/local-knowledge-test.txt`。预期入库为 3 个片段；在「测试检索」输入「本地工作流测试环境的部署口令是什么？」，应召回包含 `local-workflow-2026` 的内容。

在画布刷新资源，选择本地库；智能分支模板的决策范围和知识节点都应绑定该库，回答 Agent 选择「由工作流控制」检索。也可先用「知识库问答」模板直接验证检索 → Agent → 输出链路。

## 部署与数据

源码已更新；已有 Docker 服务需要重建：

```powershell
cd D:\code-agent-rag-workflow
$env:CODEZZN_BUILD_TARGET = 'prebuilt'
docker compose --progress plain up -d --build codezzn
```

画布前端本次没有新增构建步骤，已有 `web/workflow-editor/` 可复用。新的文档 JS / CSS 位于 `web/` 并随镜像复制。部署后 Ctrl+F5 刷新工作台。

任务及阶段记录保存在现有 tasks / task_events 表中，复用启动恢复机制。原始上传文件位于账号数据目录的 `knowledge_uploads/`，以随机上传 ID 命名，为失败重试保留；该目录应随 `data/` 备份，当前未增加自动过期清理策略。本次不需要新增数据库表。

API 保留原有同步上传行为；新增 UI 使用 `POST /api/knowledge/{id}/documents?background=true`，返回 HTTP 202 和 task_id。文档状态响应增加 uploads；失败重试使用 `POST /api/knowledge/{id}/uploads/{task_id}/retry`。本地片段预览使用 `GET /api/knowledge/{id}/documents/{document_id}/chunks?offset=0&limit=20`。这些接口均使用当前账号的租户数据库。

## 验收记录（2026-10-10）

- 相关后端回归 99 passed / 1 deselected；排除 Windows 不支持 `os.chown` 的既有测试。新增测试覆盖上传大小 / 格式、后台队列处理、阶段记录、Embedding 失败与重试、失败替换不破坏旧资料、片段分页、知识库与租户隔离、DOCX / 扫描 PDF 处理以及错误信息不泄漏凭据。
- 2 项 Node 前端入口回归通过，直接执行实际工作台事件函数，防止上传按钮再次因缓存变量错误无法打开。
- 浏览器实际点击验收：上传样本文档 → 等待后台处理 → 可检索 / 3 个片段 → 查看片段 → 本地 hybrid 检索。另一个库故意设错模型，确认错误可见；修改模型后通过「文档状态 → 重试处理」成功入库，刷新页面后结果仍保留。测试使用独立容器和数据，浏览器链路的模型适配器受控，索引为真实 Milvus Lite。
- 浏览器批量验收：同时选择 TXT 和 DOCX，两份均成功入库，分别为 3 个和 2 个片段；页面未记录 JavaScript 错误。同名 TXT 再次上传正常作为新版本替换。
- 真实模型与索引测试：当前提供方的 `qwen3.7-text-embedding` 返回 1024 维向量；独立数据目录中完成真实 Embedding → Milvus Lite 入库 → hybrid 检索，召回 3 个片段，诊断为 ok，并包含预期测试口令。记录见 `outputs/knowledge-documents/real-embedding-retrieval.json`。
- 知识检索 → Agent → 输出的工作流测试通过。该测试回答模型为受控 QA Answer，见 `outputs/knowledge-documents/workflow-retrieval.json`，不代表真实回答模型的端到端验收。
- Docker `prebuilt` 镜像构建成功。未重启正式 Codezzn 服务，未向正式账号知识库写入测试文档。
- 浅色界面截图：`outputs/knowledge-documents/batch-upload-success.jpg`、`local-chunks.jpg`、`upload-failure.jpg`、`upload-retry-success.jpg`。
