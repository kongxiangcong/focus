# Batch B 真实 PDF 验收

验收日期 2026-11-23。使用 Standalone 生产阅读工作区、实际 HTTP Host 和 Chromium。Inbox 使用本地 MinerU 4.2.3 Standard Tasks V1 处理真实原件。问答和中文译文使用确定性运行时复验。运行时提供问题和译文文本，实际的 `search`、`read_range`、`cite`、证据签发、讨论持久化、Plan、PDF.js 渲染和阅读导航均走应用实现。中文内容用于核对段落映射和阅读位置。

## 样本和入库

从 [论文页面](https://arxiv.org/abs/2211.02682) 下载 [Evaluating Emerging CXL-enabled Memory Pooling for HPC Systems](https://arxiv.org/pdf/2211.02682)。原件为双栏论文。用 pypdf 7.1.1 克隆全件，将第 8 页顺时针旋转 90°，得到本次阅读样本。

```python
from pypdf import PdfWriter

pdf = PdfWriter(clone_from="2211.02682.pdf")
pdf.pages[7].rotate(90)
pdf.write("2211.02682-rotated-page-8.pdf")
```

在同一空白工作区的 Inbox 依次上传旋转件和原件，分别确认并处理。HTTP 复验可调用 `POST /library/inbox?name=<filename>` 上传原件，用 `POST /library/inbox/<id>/confirm` 确认，再用 `POST /library/inbox/<id>/process` 启动，等待 `GET /library/inbox` 返回 `completed`。检查各自 `GET /library/sources/<sourceId>/document` 的版本及页面信息。

| 实际入库结果 | SHA-256 | Reading Source | 正文和位置 |
| --- | --- | --- | --- |
| 旋转后的 PDF | `8191eb8dc2457d8eb365550d18057c899877ad33009e0754ec4277085b142413` | `Evaluating Emerging CXL-enabled Memory Pooling for HPC Systems-paper` | 374 行，175 个已定位块片段，第 8 页 90° |
| 未旋转的 PDF | `52d1e1c9e9ce598c2b602da3ff3fdefacae2d45b0e193cf3629a04ee9827033d` | `Evaluating Emerging CXL-enabled Memory Pooling for HPC Systems-2-paper` | 389 行，176 个已定位块片段，第 8 页 0° |

两份原件普通入库生成了不同的 Reading Source。后续样本浏览使用旋转件。

## 签发和浏览器落点

在「对话」发送问题，运行时先 `search`，再以表中行号调用 `read_range`，确认 `source_text` 中包含逐字引文后用同一行范围和 `quote` 调用 `cite`。读取回答中由实际签发标记生成的编号。从文档开头点击，等 PDF.js 绘制完成后核对原件、证据卡和框。最后点 PDF 框上的编号验证焦点返回到发起定位的回答编号。

| 原句和行号 | 浏览器观察结果 |
| --- | --- |
| L127 `using the same emulated memory pool. The application is also executed` | 第 4 页，同一规范段落从左栏下部续到右栏上部。定位前目标画布宽度为 0。修正后两框同时完整进入阅读窗且覆盖对应段落片段，卡片保留原句，编号反跳到发起定位的回答。 |
| L236 `The performance of seven scientific applications` | 第 7 页，Fig. 8 图和图注各有一个独立框。定位前目标画布宽度为 0，定位后两框同时可见，分别贴合图和图注，编号反跳到对应回答。 |
| L266 `a scalable high-bandwidth system` | 旋转后的第 8 页。定位前目标画布宽度为 0，定位后单框贴合顺时针旋转的目标段落，编号反跳到对应回答。MinerU 遗漏了周边少量字词，因此使用能与实际原件逐字核对的短句。 |

以页面左上为原点记录的相对坐标，顺序为左、上、右、下。

| 页和对象 | 区域 |
| --- | --- |
| 4，左栏段末和右栏段首 | `[.086, .863, .494, .910]` · `[.535, .299, .924, .375]` |
| 7，Fig. 8 图和图注 | `[.106, .062, .481, .235]` · `[.099, .240, .487, .302]` |
| 8，旋转段落 | `[.473, .075, .732, .496]` |

第 4 页首次验收时，定位只按第一个框滚动，右栏框出现在阅读窗之外。用浏览器重现后，在现有 PDF 阅读测试中验证两框的可见范围，再修复同页框纵向范围能放入阅读窗时的初始落点。复验图像在本次运行的 `/tmp/focus-evidence-acceptance/standard-page-{4,7,8}-overlay.png`。

## 版面失配与译文

下面的变体各使用独立工作区副本。两种版面变体都修改 `parser-bundle/mineru/middle_json.json` 和 `structured_content.json` 的第 8 页 block index 2，并同步更新 `metadata.json` 对这两个产物记录的字节数和 SHA-256。保留 Source ID、PDF 字节、正文和图片。

| 复验步骤 | 浏览器观察结果 |
| --- | --- |
| 再次打开已保存的 L266 引文。副本只将该块 `bbox` 的左边界加 `0.01`。 | `bundleVersion` 仍为 `ac275872ad69f921cac5f4097282002ea46b7395a0d2c4c18c7adeaa453f5693`，`layoutVersion` 从 `95e1079007a626818b6a6c890a41c3d4f9d5f34011c587ad776e5bc232a6c7e2` 变为 `5324db27c3ca783789ecba38c0cf731507eb617a7509ad552b1dcea7f090e104`。点击直接落到中文译文对应段，证据卡显示同一原句，PDF 页及旧框均未渲染为导航目标。 |
| 另一个副本在同一块的 `coordinate_space` 填 `unspecified_pixels`，签发新的 L266 引文。 | 保持原版 PDF，跳到独立确认的第 8 页，仅显示页级证据标记。 |
| 在原旋转件签发 L103 `To capture memory usage metrics`，从 PDF 点编号。 | 没有可靠页码，直接进入中文译文对应段，证据卡显示逐字原句。 |
| 在原旋转件签发 L318 `On the memory underutilization`。准备译文时以 96、185、241 行为分段边界，末段到参考文献之前。译文就绪后在中文译文滚到 320 px，再点已保存的编号。 | L318 无对应译段。译文继续打开，位置保持 320 px，没有关联段标记，证据卡显示逐字原句。中文测试段各含 22 个短段落，使滚动范围可实测。 |

## 返回与竞态

在宽屏阅读窗等 PDF 就绪。再次发送绑定 L266 的问题后进入第 8 页，点回答编号再点 PDF 高亮编号，焦点返回发起定位的那个回答。重新打开工作区，在同一 PDF 块点「查看相关回答」，选择含「旋转页对象」的摘录，焦点返回该回答编号；另一条「旋转页复验」也在选择列表中。

手动中断复验在 Chromium 请求层暂停原 PDF 下载，点击已保存的 L266 回答编号，再在原文窗使用鼠标滚轮，然后放行下载。第 1 页绘制后位置为 0，未显示过期证据卡。随后手动滚到 240 px，仍留在第 1 页附近，第 8 页画布宽度保持 0。

暂停同一个 PDF 请求，依次点 L266（第 8 页）和 L236（第 7 页）再放行。只有第 7 页两个图框高亮，证据卡显示 L236 原句，原文窗位置为 5687 px。

切来源复验也从暂停原 PDF 请求、点击 L266 开始。由「知识库」点另一份原件的「阅读」，待第 1 页绘制后滚到 380 px，再分别放行或中断旧请求。新来源的阅读位置保持 380 px，旧证据卡和过期错误提示没有出现。首次复验发现 PDF.js 在旧 worker 启动尚未结束时报告未处理的 `Worker was terminated`。修复后对已离开的 PDF 延后清理至加载成功或失败，给卡死请求的清理等待设置 30 秒上限。重新运行两种请求结果时，Chromium 未报告未处理异常。

## 旧 Bundle 和自动回归

`test_legacy_discussion_can_append_line_citations_without_rewriting_the_bundle` 通过 HTTP 打开无 IR 的旧 Bundle，保留旧普通引文，提交新问题并签发带旧版面区域的新证据。关闭 Host 后再次打开，确认同一 Discussion 及新回答仍可读。测试按字节和修改时间核对原 Bundle；破损的可选旧版面仍可签发逐字引文。

以下测试命令在仓库根目录运行。Python 套件使用项目依赖中的 pypdf；HTTP 检查需要本地回环。

```sh
pnpm --filter @focus/standalone build
pnpm --filter @focus/standalone test WorkspaceEvidenceNavigation --testTimeout 30000 --maxWorkers 1
pnpm --filter @focus/reader-ui test PdfEvidenceNavigation ConversationReader source-evidence --testTimeout 30000 --maxWorkers 1
python -m unittest discover -s tests -p 'test_source_reading*.py'
python -m unittest discover -s tests -p test_pdf_reading.py
```

生产构建和 reader-ui 类型检查通过，前端相关测试 36 项通过，Python 的 Source Reading 和 PDF Reading 测试各通过 13 项和 7 项。
