# 识别评测与样本贡献

开发集与独立验收集分开。`tests/fixtures/accuracy/development.json` 包含 5 个表格样本、3 类布局；`tests/fixtures/ocr/regression-manifest.json` 包含同一明细布局的 6 张合成图片。两者都不能证明真实照片的通用准确率。

```sh
python -m scripts.evaluate_accuracy tests/fixtures/accuracy/development.json --output artifacts/table-accuracy.json
python -m scripts.evaluate_accuracy tests/fixtures/ocr/regression-manifest.json --output artifacts/image-accuracy.json
```

每条预期记录先标注 `anchors`：工作表、姓名单元格、日期或事项单元格；评测按这些原文位置配对。标题、日期、预测顺序不参与配对。没有位置依据或同一位置关联多条结果时，不给正确分。姓名位置按工作表区分，避免不同工作表的 `B2` 被当成同一个人。

报告分别列出提取精确率、召回率、日期正确率、时间正确率、姓名错误关联数、待确认比例和手动修正操作数。尚未实际记录的操作数使用 `null`。人工点击导入确认不算修正；更改 OCR 文字、补日期、改时间、设置一次布局映射分别记录一次操作。批量修改同时记录受影响条数，不能把一百条更改写成零次修正。

独立验收需 `split: acceptance`、样本来源与许可、独立人工复核和操作量记录，且覆盖 20 类表格布局和 20 张图片。相同模板的旋转、压缩、换色、月份或姓名变体不能增加布局数。真实照片与合成回归分别报告；保持表格完整无误提取、清晰图片 98% 精确率 / 95% 召回率的稳定版目标。`--acceptance` 未满足这些条件时返回失败。

请用仓库的 Layout support Issue 表单提交有权公开的脱敏样本。示例姓名统一使用“星辰奕歌”。姓名换行可能表示两个人，当前不会把文字片段自动拼接成另一姓名；请对照原图修正 OCR 文字。PDF、手写、严重透视及复杂无边框布局仍不属于公开支持范围。
