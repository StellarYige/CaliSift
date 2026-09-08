# alpha.2 架构与维护范围

本轮保持单体桌面应用：Vue / TypeScript + pywebview，独立 Python 核心，SQLite；桌面不需要业务服务器、账号、后台任务平台或数据库服务。用户选择的目标是 Windows 与 macOS，Linux 保留核心 CI，暂不发布桌面包。

界面分为导入、安排、模板、设置。导入页的结果选择、原文表格、更新对应和任务轮询已拆成独立组件及组合函数。来源历史进入导入的次级页签，导出进入安排工具栏与导入成功后的下一步。单项修改直接保存，后端仍执行版本检查与事务提交；批量及来源更新仍先预览。

SQLite schema 2 在 `documents` 内保存工作区偏好，拥有独立 `revision`；不会使日历变更预览过期。主题、字号、密度、每周起始日、配置起点、休息显示和分类随工作区备份。设备偏好保存最近工作区、窗口尺寸和面板比例，留在当前设备。覆盖恢复递增偏好版本，拒绝覆盖恢复前打开的旧编辑表单。

迁移先建立数据库恢复点，再在事务内迁移 schema；旧数据失败时保留。备份 v2 增加偏好及上次学期，恢复继续接受 v1。模板本体可编辑、复制、删除；来源持有规则副本，模板删除不会改变已有来源。课程批量展开和上次学期保存使用同一事务。

`desktop_contracts.py` 对偏好、设备补丁、课程、模板删除和任务查询提供共享验证；`desktop/src/types.ts` 定义对应 TypeScript 类型，`request()` 为这些命令提供参数及结果约束。旧命令继续经过既有领域验证与允许列表，兼容 CLI/API。无需额外引入 RPC 框架或生成服务。

macOS 使用原生 Cocoa / WKWebView，分别在 arm64 与 x86_64 主机构建。`platforms.py` 集中工作进程路径、原生剪贴板、打开目录和导航限制。静态资源服务保持原路径用于计算相对 URL，以适配 `.app` 中的符号链接；实际访问仍解析并检查资源根目录，不能借链接越界。

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
npm ci --prefix desktop
python -m scripts.build_macos
python -m scripts.smoke_macos
```

最低 macOS 15。构建使用本机架构、随包离线模型和 ad-hoc 签名，不购买 Developer ID，不做公证。DMG 包含 CaliSift.app 和 Applications 快捷入口。GitHub 在 macOS 15 构建，并将同一个 DMG 放到 macOS 26 执行冻结 OCR、UI 保存与导出测试。CI 不能替代从浏览器下载后的 Gatekeeper、Apple Calendar 和真实外设交互记录。

回归集和许可要求见[识别评测说明](accuracy-corpus.md)。`scripts/smoke_thunderbird.py` 是独立开发验证工具，不随应用启用自动化端口。历史小程序不继续新增功能；其 25 项 Node 内置测试不需要安装小程序自动化依赖。
