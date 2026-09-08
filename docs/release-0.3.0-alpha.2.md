# CaliSift 0.3.0-alpha.2

这一版让个人日历更方便连续使用，并新增 macOS 桌面预览。文件在本机处理，无需微信、云服务器、账号或大模型密钥。

## 本次变化

- 界面收为导入、安排、模板、设置四个入口。来源历史放在导入页，导出放在安排页；单项修改直接保存，批量修改与来源更新仍先核对。
- 增加系统 / 浅色 / 深色主题、三档字号、间距、每周起始日及自定义分类颜色。外观有独立版本，不会使正在核对的日历预览失效。
- 模板可编辑、复制、删除；课程支持批量输入与复用上次学期。删除模板不会改动已绑定来源的规则副本。
- SQLite schema 2 升级前建立恢复点；备份 v2 携带个人偏好和上次学期，继续恢复旧备份。Windows 生成的固定备份加入跨系统恢复测试，保留事件 ID 与导出修订号。
- 增加 Apple 芯片与 Intel 的原生 macOS 包；修复 `.app` 内符号链接导致资源页无法打开的问题。
- 表头识别支持常见格式注释。识别评测改为按原文位置配对，并新增表格开发集；姓名继续精确匹配。
- 根据真实 Thunderbird 导入结果，在导出页说明重复导入的更新和取消限制。

## 下载文件

- `CaliSift-0.3.0-alpha.2-windows-x64-setup.exe`：Windows 11 x64 完整安装包，包含 Python、OCR、固定模型、字体和 WebView2 离线安装程序。
- `CaliSift-0.3.0-alpha.2-macos-arm64.dmg`：macOS 15+，Apple 芯片。
- `CaliSift-0.3.0-alpha.2-macos-x86_64.dmg`：macOS 15+，Intel。
- `CaliSift-models-ppocrv5-v1.zip`：设置页使用的离线模型修复包。
- `CaliSift-third-party-source-0.3.0-alpha.2.zip`：对应依赖源码与构建说明；安装包中也有一份。
- `SHA256SUMS.txt`：上述文件的 SHA-256 校验值。项目源码使用 GitHub 随标签提供的 Source code 归档。

Windows 安装包未签名；macOS 使用 ad-hoc 签名，没有 Developer ID 或公证。不要求关闭系统保护。macOS 浏览器下载后的 Gatekeeper 流程尚未真机验证，当前作为开发预览分发。

## 使用与升级

安装后可以先用“星辰奕歌”示例走通识别、核对、保存和导出。Windows 升级前自动建立恢复点，卸载保留数据；macOS 将应用复制到 Applications。旧工作区首次打开时自动迁移，迁移失败保留旧数据库。

Windows 数据位于 `%LOCALAPPDATA%\CaliSift`，macOS 位于 `~/Library/Application Support/CaliSift`。跨设备使用设置页的便携备份；恢复默认建立独立工作区。

## 验证与限制

Windows 已完成安装后真实 UI、原生文件对话框、OCR、ICS、重启、升级恢复点和卸载保留数据验证。macOS 15 / 26 的两种架构已通过 CI 中的真实打包程序启动、OCR、导入保存、备份和导出。完整自动回归及机器可读证据见[验收记录](desktop-verification.md)。

Thunderbird 155.0 的真实导入器正确保存中文、跨夜、全天、单点时间和提醒字段；重复导入不更新或删除旧安排。可将新版导入新的空专用日历，核对后再处理旧日历。ICS 是静态导出，不代表自动同步，通知实际弹出仍未测试。

本版仍是 alpha。20 种独立布局 / 20 张独立图片、真实照片验收、干净 Windows 离线安装、macOS 原生文件选择和 Gatekeeper、Apple Calendar / iOS / Android 日历仍有待验证。现有 5 个表格和 6 张合成图片回归均通过，不能据此宣称真实图片已达到 98% 精确率 / 95% 召回率目标。Linux 仅保留核心 CI。

欢迎提交有权公开的脱敏样本与兼容性结果；不要公开私人排班和真实姓名。
