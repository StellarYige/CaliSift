# CaliSift · 星程

把排班表、课表、培训通知和清晰截图整理成属于你的安排，在浏览器中对照原文核对，再下载 ICS 日历快照。

**[打开网页版](https://stellaryige.github.io/CaliSift/)** · [下载完整静态 ZIP](https://stellaryige.github.io/CaliSift/downloads/CaliSift-web-0.4.0-alpha.1.zip) · [自部署说明](docs/self-hosting.md) · [实际验证记录](docs/verification-web.md) · [English](README.en.md)

## 仅维护网页

从 0.4.0-alpha.1 起，唯一产品入口是网页版。没有手机 App、桌面 App、业务后端、账号或云同步。历史 Git 提交、标签和已发布安装包保留，当前代码不再构建或发布新的原生安装包。

电脑 Chrome、Edge、Firefox 是验收目标。手机网页保留基本响应式布局；手机和其他浏览器未进行专项适配、真机验收。

## 使用

1. 填写完整姓名或先用虚构示例体验。
2. 选择/拖入 XLSX、XLS、CSV、PNG、JPEG，或粘贴截图。每批最多 10 份文件、5 张图片；单文件最多 10 MiB，总计 30 MiB，图片最多 1200 万像素。
3. 识别后对照原文与局部证据，核对姓名、日期、跨夜时间、冲突和不确定项目，再预览并保存。
4. 在“安排”中补充修正，下载提取报告、ICS 或工作区备份。
5. 在设置中“准备 / 修复离线资源”。应用、Python/WASM 和 OCR 模型全部下载并校验成功后显示“离线就绪”，此后断网可以处理表格和图片。

表格和图片都在本地浏览器处理。运行时资源来自本站，无第三方 CDN。OCR 使用固定模型及单线程 WASM，逐张处理，支持取消和超时。模型识别结果不是日程准确率，始终需要核对。

## 数据与备份

数据属于**当前浏览器配置和站点部署目录**。同一配置会共用数据，工作区不是账号隔离。换浏览器、站点、目录或端口，以及清理站点数据后，需用备份恢复。无云端副本，请定期下载完整备份并检查下载列表。

IndexedDB 保存安排、草稿、规则、偏好和必要证据。多标签修改会核对版本，失败不会显示保存成功。未完成任务暂存原文件以便刷新恢复；确认或丢弃任务后清理原文件。旧 Windows ZIP 和旧小程序 v1/v2 JSON 备份可导入。

ICS 是导出时的安排快照。之后的修改或取消不会同步到外部日历；重复导入可能重复，不保证自动更新或删除。建议每一版导入新的专用日历并核对，再停用旧版显示与提醒。详见界面中的专用日历指引。

## 自部署与开发

完整静态 ZIP 包含运行依赖、模型、字典、校验清单、Docker/Compose 和部署说明。支持根路径和子路径，完整离线能力要求 HTTPS 或 localhost。

```sh
npm ci --prefix web
npm run build
python -m http.server 8080 --bind 127.0.0.1 --directory web/dist
```

开发环境、验证和打包步骤见[自部署说明](docs/self-hosting.md)和[开发说明](docs/development.md)。`main` 经 Actions 检查后部署 GitHub Pages，不使用额外发布分支。

项目代码为 Apache-2.0，依赖各自保留原许可证，见 [第三方声明](THIRD_PARTY_NOTICES.md)。仓库此前的 alpha.1/alpha.2 桌面验证文档属于历史记录，不代表当前网页验收。
