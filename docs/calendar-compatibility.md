# ICS 客户端兼容性

ICS 是静态文件。稳定 UID 和修订序号为客户端提供身份依据，不能要求客户端一定按它们更新或取消事项。

2026-09-08 在 Windows 11 x64 上运行 Mozilla 官方 Thunderbird **155.0**，使用独立临时用户配置，不登录邮件账号。测试启动真实 Thunderbird，调用与其导入界面相同的 `getItemsFromIcsFile` / `putItemsIntoCal`，再从 Thunderbird 本地日历读取实际保存值。**该检查覆盖真实导入器和本地存储，没有操作 Thunderbird 原生文件选择器，也没有验证通知实际弹出。**

| 内容 | 实测结果 |
| --- | --- |
| 中文、逗号、分号、反斜杠、换行、地点 | 正确保留 |
| 跨夜 20:00 至次日 08:00 | 保留 Asia/Shanghai 和实际结束日期 |
| 全天 | 保留日期值与排他结束日期 |
| 只有开始时间 | 导入后开始与结束同一时刻；CaliSift 没有编造结束时长 |
| 提前 15 分钟 | 保存为 -900 秒提醒；未验证通知权限与通知弹出 |
| 相同文件重复导入 | 仍有 3 项，已有 UID 触发导入错误，不会增加 3 项副本 |
| 改为 21:00 后导入同一日历 | 仍保留原 20:00；不能视为已同步改期 |
| 新版去掉一项再导入 | 旧日历仍保留 3 项，不自动删除 |
| 将最终新版导入空的专用日历 | 正确得到 2 项和新版 21:00 时间 |

推荐先为 CaliSift 建立专用日历。新版导入另一个空的专用日历，核对后再处理旧的专用日历；不要删除混有其他个人事项的日历。Thunderbird 的普通导入流程见[官方说明](https://support.mozilla.org/en-US/kb/exporting-and-sharing-a-calendar)。

复现：`python -m scripts.smoke_thunderbird <Thunderbird可执行文件>`。脚本使用临时数据及临时自动化端口，退出时关闭自己启动的进程。不要给日常使用的个人配置启用该测试端口。机器可读结果见 [thunderbird-ics.json](verification/thunderbird-ics.json)。

Apple Calendar、iOS、Android 暂无实测结论。macOS CI 启动成功不能替代 Apple Calendar 导入、Gatekeeper、真实文件选择、拖入或剪贴板验证。
