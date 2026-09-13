# 扩展约定

- `readers.py` 提供坐标、单元格和合并区域；`parsing.parse_sheets` 是表格与 OCR 共用入口。未来 PDF 可在还原版面后接入，不在 UI 添加空入口。
- `rules.py` 管理班次、课程和模板。复杂布局扩展不能绕过姓名精确匹配、字段证据、待确认和预览。
- `calendar.py` 管理稳定身份、来源贡献、规则、变更、修正和撤销。网页版不提供云同步，不能以内容哈希替代稳定身份。
- `ocr.py` 负责预处理与证据；`browser_ocr.py` 调用 Worker 内的单线程 ONNX Runtime Web。模型升级需更新固定版本及校验值，重新运行真实浏览器与固定模型验收。
- `calendar.export_ics` 只生成静态快照，不开发订阅消息、后台提醒或系统服务。
- `web/src/database.ts` 在 IndexedDB 事务内核对版本并提交完整快照；数据失败不回报保存成功。工作区、草稿、证据、偏好和备份兼容性必须一起验证。

验收范围和实测情况见[网页版验证记录](verification-web.md)。历史版本验证文档不代表当前网页状态。
