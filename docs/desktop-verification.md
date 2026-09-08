# 0.3.0-alpha.2 桌面验收记录

日期：2026-09-08。结论：Windows 本机和 macOS CI 的桌面预览流程已通过；**尚未达到 0.3.0 稳定版全部验收门槛**。本记录分别标明自动回归、实际应用运行和仍缺少的真实设备 / 数据。历史结果保留在 [alpha.1 记录](verification-alpha1.md)。

## 平台与实际验证

| 平台 | 已完成 | 仍未覆盖 |
| --- | --- | --- |
| Windows 11 x64，build 26200 | 本机完整安装、实际 WebView2 窗口、原生文件打开 / 保存、真实 OCR、ICS、重启、升级恢复点、卸载保留数据 | 无 WebView2 的干净机器离线安装、完整系统 DPI 矩阵、原生拖入和剪贴板操作记录 |
| macOS 15.7.9 arm64 / x86_64 | 分别原生构建；ad-hoc 签名校验；真实 WKWebView 导入并保存 4 项、冻结 OCR、ICS、备份、重新打开数据库后身份保留 | 浏览器下载后的 Gatekeeper、原生文件对话框、拖入和剪贴板、Apple Calendar |
| macOS 26.6.2 arm64 / 26.6.1 x86_64 | 挂载同一份 macOS 15 构建的 DMG，再运行冻结 OCR、实际 UI 保存、ICS、备份和数据库重新打开检查 | 与上一行相同；CI 不能替代独立用户设备验收 |
| Linux | GitHub Actions 的 Python 核心、SQLite 与迁移回归 | 暂不构建或分发 Linux 桌面包 |

实现提交 `74ec2ac` 的 [Windows / Linux 核心与真实 OCR CI](https://github.com/StellarYige/CaliSift/actions/runs/34218674219) 和 [macOS 四项原生打包检查](https://github.com/StellarYige/CaliSift/actions/runs/34218674342) 均成功。发行标签会重新运行核心、Windows 构建和 macOS 工作流；以 Release 中链接的最终检查为准。

macOS 报告：[15 arm64](verification/alpha2-macos-15-arm64.json)、[15 Intel](verification/alpha2-macos-15-x86_64.json)、[26 arm64](verification/alpha2-macos-26-arm64.json)、[26 Intel](verification/alpha2-macos-26-x86_64.json)。这些报告明确将原生文件对话框和实际 Gatekeeper 验证标为 `false`。

## 自动回归与日常交互

本机构建环境为 Python 3.11.9、Node.js 24、pywebview 6.2.1、RapidOCR 3.4.2、ONNX Runtime 1.23.2 CPU；三个 ONNX 模型与字体均按 `resources/models.json` 校验。Windows 机器为 i5-12500H、约 16 GB 内存。复现命令见[开发文档](development.md)。

| 项目 | 结果 |
| --- | --- |
| Python 完整回归 | 256 通过，1 跳过，0 失败；分支覆盖率 91.14%，门槛 90%。Windows 账号无法创建符号链接时跳过相应路径测试，该测试在 macOS CI 执行 |
| Vue 交互 | 11 项通过；含单项保存失败保留表单、任务切换后的过期响应、仅待确认筛选保留原始索引、偏好版本与过期提交 |
| 历史迁移 | 25 项 Node 测试通过；不再为这些内置测试安装小程序自动化依赖 |
| 外观 / 布局 | 浅色与深色、14 / 17 / 20 字号、舒适与紧凑间距、周日开头月历，720 宽窗口无全页横向溢出；实际 DPR 1.25 |
| 持续日历 | 追加与重复、跨来源贡献、保留修正、更新撤销、归档、过期 / 重复提交、写入失败、重启与损坏备份处理 |
| 个性化 / 迁移 | schema 2 升级恢复点、独立偏好版本、旧配置映射、覆盖恢复拒绝旧编辑表单；Windows 生成的备份在跨平台 CI 恢复，ID / SEQUENCE / 提醒 / 偏好保持 |
| 规则 / 导出 | 来源规则副本、模板修改及删除、批量课程与学期复用、单双周、跨年、跨夜、临时修改、ICS 字段与修订 |
| 资源与边界 | 模型缺失 / 超时 / 部分失败、原生命令验证、静态服务资源边界；Windows 原生导航限制通过，Mac 桥接来源检查与导航适配已实现 |
| 冻结工作进程 | CSV 与真实本地 ONNX OCR 都通过；在限制 PATH 的环境运行，不依赖开发目录里的 Python / Node |

机器可读记录：[自动回归](verification/alpha2-automated-checks.json)、[原生外观检查](verification/alpha2-desktop-ui.json)、[安装 / 升级 / 卸载](verification/alpha2-install-smoke.json)、[安装后 UI 与重启](verification/alpha2-packaged-ui.json)。截图：[核对工作台](images/workbench-alpha2.png)、[深色月历](images/events-dark.png)、[窄窗口与 20 号字](images/events-dark-narrow-20.png)。

测试使用独立临时数据目录和虚构样例。安装脚本发现当前用户已有 CaliSift 时会停止，避免覆盖正在使用的程序；未卸载电脑已有的共享 WebView2。故障注入覆盖写入失败处理，不等于耗尽真实磁盘。macOS 数据持久性检查是关闭并重新打开数据库，Windows 另有完整进程重启检查。

## 一次性能测量

| Windows 本机操作 | 本轮结果 |
| --- | --- |
| 完整安装，机器已有 WebView2 | 11.42 秒 |
| 安装后原生窗口至示例按钮可操作 | 5.02 秒 |
| 冻结 CSV 工作进程，2 项安排 | 0.898 秒，峰值工作集 56.7 MiB |
| 冻结 OCR 工作进程，1 张合成图 | 3.450 秒，峰值工作集 442.2 MiB |

原始值见[冻结工作进程](verification/alpha2-frozen-workers.json)。这些是构建机单次测量，OCR 进程内存不等于整套桌面应用内存。冷启动 5 秒目标没有全面达到；此前 5000 条日历查询的测量保留在 alpha.1 记录，本轮没有用旧数字冒充重新测试。

## 识别能力

本轮评测按人工指定的工作表和单元格位置配对，不用预测标题、日期或输出顺序决定哪条算正确。表头格式注释的支持仍采用有限规则，姓名继续精确匹配；不把换行文字片段自动拼成另一个人的姓名。

| 开发集 | 样本 / 预期安排 | 本次结果 |
| --- | --- | --- |
| 表格 | 5 个 CSV，3 类布局，8 项预期 | 8 项完整提取；精确率、召回率、日期及时间字段正确率均为 100%；姓名错误关联 0，待确认 0 |
| 图片 | 同一布局的 6 张合成变体，各 1 项预期 | 全部调用真实模型；6 项正确，姓名错误关联 0，日期和时间均正确，待确认 0 |

原始报告：[表格](verification/alpha2-table-accuracy.json)、[真实模型图片回归](verification/alpha2-ocr-regression.json)。两份报告的 `acceptance_passed` 都为 `false`；没有条目的另一类指标也不能当成该类准确率。手动修正操作量尚未完整记录，使用 `null`，没有编造为零。

这些是可复现开发样本。5 个 CSV 不代表 20 种 Excel 布局；同一模板的旋转、压缩、倾斜、合并表头与简单无边框变体也只算 1 种布局。尚无独立真实照片验收，不能据此宣称已经达到真实图片 98% 精确率 / 95% 召回率。`--acceptance` 会拒绝该开发集。样本来源、许可和贡献要求见[评测说明](accuracy-corpus.md)。

## 外部日历与剩余门槛

真实 Thunderbird 155.0 导入器与本地日历已验证：中文、转义、跨夜、全天、单点时间和 -900 秒提醒字段正确。相同文件重导入不增加副本，改期和取消也不会覆盖旧事项；导入新的空专用日历后，最终新版结果正确。没有测试 Thunderbird 原生文件选择器或提醒实际弹出，完整步骤见[日历兼容性](calendar-compatibility.md)。

稳定版仍需补齐独立 20 种布局 / 20 张图片、真实照片和人工复核记录、干净 Windows 离线安装与完整 DPI 矩阵，以及 macOS 原生交互 / Gatekeeper、Apple Calendar、iOS / Android 导入和实际通知。当前发布 alpha 预览，公开支持范围保持清晰打印体和简单布局；不承诺自动同步或任意表格识别。
