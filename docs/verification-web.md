# CaliSift 0.4.0-alpha.1 网页验证记录

验证日期：2026-09-13。本记录只针对浏览器版本；此前桌面 alpha 的结果保留为历史记录。

## 范围和方法

本机 Windows 11（build 26200）使用 Playwright 1.63.0 驱动真实浏览器，针对生产构建运行，不 mock Pyodide、模型推理、IndexedDB 或 Service Worker。故障场景明确注入存储/下载异常、断网和损坏缓存；图片粘贴使用真实图片字节构造浏览器剪贴板事件，Firefox 丢弃合成事件文件时补充该事件的 `clipboardData`，未操作系统剪贴板权限弹窗。

Python 领域与业务回归 **218 项通过**；Vue 和 IndexedDB 单元测试 **23 项通过**；`vue-tsc` 与 Vite 生产构建通过。浏览器使用 Pyodide 314.0.6、Pydantic 2.12.5、ONNX Runtime Web 1.23.2，固定模型的 WASM 推理真实运行。

| 电脑浏览器 | 本机版本 | 浏览器场景 |
| --- | --- | --- |
| Chrome | 152.0.7977.84 | 7 项通过；恢复流程修正后复验通过 |
| Edge | 152.0.4191.66 | 7 项覆盖通过，含网络检查修正后复验 |
| Firefox（Playwright 构建） | 155.0 | 7 项覆盖通过，含修正后定向复验 |

每个浏览器执行以下七组检查，细项包含：

1. 现有 **15 份合成 XLSX/XLS/CSV** 与独立保存的 Python 领域输出逐项比对，包括姓名匹配、跨夜、冲突、待确认和原文位置。
2. **6 个 OCR 合成变体**的真实检测、方向判断和识别，核对日期、标题、起止时间、姓名单元格和证据；人工修正保留 `original_text`。
3. 原文核对、刷新恢复、保存、清理原文件、备份和 ICS 下载。准备全部离线资源后禁用网络，重新打开页面，完成 XLS 和图片识别、核对、保存及 ICS 下载。
4. 两个标签页的陈旧预览不能重复提交；独立浏览器配置没有已有数据；同一服务器的根路径和子路径分别使用各自工作区。
5. 注入空间不足时不显示保存成功；导入未改动的旧 Windows ZIP 和 v1 JSON；下载启动失败时显示错误且不增加导出记录。v2 JSON 和 UID/SEQUENCE 兼容另有 Python 回归覆盖。
6. 取消、刷新中断和重试保留草稿；缓存模型被破坏后校验失败、联网修复恢复就绪；新 Service Worker 等待旧页关闭，更新前后已保存安排保持一致。
7. 拖入表格与粘贴图片创建本地任务，经真实识别后保存。

网络核验保留 HTTP(S) 请求 URL 和方法，要求全部为本站静态资源 GET。Edge 会额外暴露自身 `edge://downloads-hub` 等下载界面资源，这些是本地浏览器界面，不是 HTTP 请求；首次把它们当成外部网络请求的断言已修正。文件和安排没有业务上传接口，计算 Worker 也限制为本站 GET。

首次完整矩阵捕获并修复了两处界面问题：恢复备份后的异步工作区切换会覆盖快速导航；Firefox 等待自动持久存储授权时会锁住离线按钮。修正后重新构建并定向复验。测试还补充了等待恢复弹窗关闭的同步条件，避免前一次同文案提示让下一次恢复断言过早通过。云端发布门禁仍完整执行全部 21 个场景。

## 静态包和发布验证

本机静态服务器上的 `/` 与 `/CaliSift/` 均已逐文件验证 **219 项文件**的 SHA-256、浏览器必需的 MIME 类型和缺失资源 404。应用离线资源约 **76.3 MiB**；其中包含模型、字典、Python/WASM、许可证及对应源码。`sw.js` 和离线清单另计入发行文件校验。

首次云端运行发现 Windows CI 将 `.mjs` 返回为 `text/plain`，三个浏览器均拒绝加载模块，部署门禁正确阻止发布。已把静态服务器的 MIME 类型改为显式映射，并随 ZIP 提供该服务器；CI 在浏览器测试前检查全部静态文件，失败即停止。该问题与解析/OCR 输出无关，但必须修正后重新执行完整矩阵。

本机未安装 Docker。Actions 的 `container-check` 会从同次构建的完整 ZIP 启动只读 Nginx/Compose，检查根路径、子路径、文件哈希和 MIME，成功后才能部署 Pages。部署后的 `production-check` 再核对公开站点与 ZIP 的字节，并在全新 Chrome 配置中完成表格识别、离线准备、离线真实 OCR 和 ICS 下载。

每次执行的浏览器版本、结果、截图和请求记录保留在 [Web checks and Pages](https://github.com/StellarYige/CaliSift/actions/workflows/web.yml) 对应运行的 `browser-verification`、`container-verification`、`production-verification` 产物。静态 ZIP 与 ZIP SHA-256 同时作为 `calisift-static-web` 产物和站点公开下载，部署使用同次已验证的应用字节。

本机首次完整矩阵与失败追踪保留在 `artifacts/web-browser-initial.json`、`artifacts/web-browser-initial-traces/`；修正后的定向复验记录为 `artifacts/web-browser-*-recheck.json`，截图为 `artifacts/web-<浏览器>-review.png`。云端完整矩阵输出 `web-browser-results.json`。正式站点额外检查由 `scripts/smoke-web.mjs` 和 `scripts/verify-static.py` 复现，结果输出在 `artifacts/web-production*`。

## 证据的限制

- 真实脱敏表格和图片样本仍为 **0**。15 份表格和 OCR 6 个变体均为开发合成数据；OCR 变体属于同一种明细布局，不能算六种独立布局。`independent_review` 仍为 `false`，没有真实准确率结论。
- 本机矩阵为 Windows 电脑浏览器；Firefox 使用 Playwright 分发构建。macOS、Linux 交互使用、Safari、其他浏览器、手机网页和手机真机未作专项验收。CI 的 Linux 发布烟测不替代这些完整矩阵。
- 自动化断网使用浏览器上下文离线模式；未进行长时间硬件断网或低内存设备压力验收。操作系统下载落盘后的用户保留行为、外部日历客户端是否正确导入，不能由网页保证。
- IndexedDB 的浏览器存储回收、用户清除站点数据和隐私模式不属于持久备份。工作区需要定期下载备份；完整离线使用要求 HTTPS 或 localhost。
