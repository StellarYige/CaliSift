# CaliSift 静态网页版自部署

目标在线入口为 https://stellaryige.github.io/CaliSift/ 。仓库仅维护网页，没有业务后端、账号、云同步、原生安装器或提醒服务。

## 使用完整静态 ZIP

1. 下载同版本 [完整静态 ZIP](https://stellaryige.github.io/CaliSift/downloads/CaliSift-web-0.4.0-alpha.1.zip) 及 [ZIP 校验文件](https://stellaryige.github.io/CaliSift/downloads/CaliSift-web-0.4.0-alpha.1.zip.sha256)，核对 ZIP 的 SHA-256。公开下载不要求登录。
2. 解压后，把 `web/dist/` **全部内容**放入静态服务器的站点根目录或任意子目录。不要漏掉模型、字典、Python/WASM、`sw.js` 或校验清单。
3. 用带末尾 `/` 的网址访问，例如 `/`、`/CaliSift/`、`/tools/calendar/`。服务器应将目录地址重定向到带 `/` 的地址；不要把缺失 `.wasm`、`.whl` 或 `.onnx` 的请求改写成 HTML。
4. 完整离线能力要求 HTTPS 或 localhost。`file://` 不是支持的部署方式。通过局域网 IP 使用时请配置 HTTPS。
5. 打开设置，点击“准备 / 修复离线资源”。页面显示总大小、进度和 SHA-256 校验结果，全部完成才显示“离线就绪”。

ZIP 内 `web/dist/SHA256SUMS` 覆盖所有应用资源文件；`offline-manifest.json` 记录当前构建的版本、大小、哈希。ZIP 中的模型与网页使用相同字节，运行时无第三方 CDN 请求。构建机器需要联网下载已经锁定的依赖。在线站点额外提供 `downloads/` 下的 ZIP 和独立 ZIP 校验文件；这些下载包不计入离线准备，也不嵌套在自身 ZIP 中。

快速本地静态服务：

```sh
python -m http.server 8080 --bind 127.0.0.1 --directory web/dist
```

然后访问 http://localhost:8080/ 。Python 在这里仅提供静态文件，不处理个人文件。

## Docker / Compose

解压 ZIP 后在其根目录执行：

```sh
docker compose up --build -d
```

访问 http://localhost:8080/ 或 http://localhost:8080/CaliSift/ 。提供的 Nginx 配置仅提供静态内容，Compose 默认绑定本机。面向其他用户部署时，在反向代理或负载均衡器配置 HTTPS。

镜像不会保存用户安排。用户数据只在各自浏览器的 IndexedDB 中。容器备份不能替代用户下载工作区备份。

## 更新与恢复

完整替换一版静态文件。建议先上传所有资源、最后切换 `index.html` 和 `sw.js`，或使用服务器的目录原子切换能力。SW 会校验资源，混合版本的资源不会被标成离线就绪。

旧页不会强制刷新。检测到新版后，先保存核对工作，再关闭本站所有标签页，重新打开并准备新版离线资源。SW 不删除个人数据库；旧版本资源缓存保留，以便正在工作的页面继续使用。清理站点数据会同时清理个人数据，所以请先下载备份。

数据范围是**浏览器配置 + 站点源（协议、主机、端口）+ 部署目录**。同一浏览器配置会共用同站点同目录的数据。工作区是整理功能，不是账号权限隔离。换浏览器、换站点、改变目录/端口或清理站点数据后，需要用备份恢复。隐私模式和浏览器存储回收也可能丢失本地数据。

导入旧 Windows ZIP 和旧小程序 v1/v2 JSON 均通过同一备份校验逻辑。默认恢复为独立工作区；替换当前工作区时保留两个最近恢复点。备份不包含未完成任务的原文件。确认或丢弃任务后清理原文件，长期只保留必要证据。

## 从源码构建与检查

```sh
python -m venv .venv
# 激活 .venv 后：
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
npm ci --prefix web
python -m pytest
npm test
npm run build
node web/node_modules/playwright/cli.js install chrome msedge firefox
npm run test:browser
npm run package
```

`resources/web-runtime-lock.json` 独立锁定浏览器依赖及下载哈希。常规构建只接受清单内字节；维护者调整版本时才运行 `python scripts/prepare-web.py --update-lock`，随后重新执行完整浏览器验收。开发预览可用 `npm run dev`，离线与发布验收针对 `npm run build` 的生产文件。

## GitHub Pages

仓库 Settings → Pages 的 Source 应为 **GitHub Actions**。`.github/workflows/web.yml` 在 `main` 上先执行 Python、Vue、Chrome、Edge、Firefox 验证，再从完整 ZIP 启动静态容器核验根路径、子路径、MIME 类型和全部文件哈希，全部通过后部署同一静态产物；PR 只检查，不部署。不创建发布分支，也不创建新的原生安装包。

参考：[GitHub Pages 自定义工作流](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)、[Pyodide 314.0.6 包清单](https://pyodide.org/en/stable/usage/packages-in-pyodide.html)、[ONNX Runtime Web WASM 参数](https://onnxruntime.ai/docs/tutorials/web/env-flags-and-session-options.html)。
