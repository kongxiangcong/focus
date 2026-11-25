# 设计文档 01：对话阅读证据反标（含原文 PDF）、精读粗粒度联动与统一输入解析 IR（修订版）

> **所属序列**：Focus 重构体系 · 文档 01（数据与证据基座）
> **基线版本**：`focus-d4fb6a5a36af50e01611fe26ff949749226c0300`
> **实施策略**：**先验证版本指纹、引文签发与块级定位协议与单 PDF 垂直切片（Batch B），再切换三格式正向派生与精读联动（Batch C）**。

---

## 1. 问题诊断与核心根因

当前原文 PDF 视图（`ui/packages/reader-ui/src/PaperViews.tsx:3-4, 27-124`）已基于 `pdfjs-dist` 实现 `<canvas>` + `TextLayer` + 百分比 `.paper-region` 覆盖层，但证据反标在坐标链、校验链与多视图链上存在以下已核实缺陷：

1. **三链路无统一块级 IR**：PDF 依赖 `.agents/core/pdf_layout.py:32-110` 事后拿 `middle_json.json` 纯文本去 `content.md` 做去空白子串匹配（公式、图表、表格、重复短句大量丢块）；HTML（`.agents/core/html_article.py:68-90`）压扁丢弃 `data-focus-node`；Markdown（`.agents/core/library_import.py`）未接入 Inbox 状态机。
2. **MinerU 坐标断流与前端截断**：
   - 云端 `.agents/core/mineru.py:313-325` 仅硬编码查找 `middle_json.json / model_output.json / structured_content.json`，忽略 MinerU v4 常见的 `*_content_list.json`、`*_content_list_v2.json`、`*_middle.json`。
   - `.agents/core/pdf_layout.py:66-69` 对非 `[0, 1]` 坐标静默置 `None`。
   - 前端 `PaperViews.tsx:109-120` 合并同 `blockId` 片段时仅保留首个 `bbox`，丢弃跨栏/容器子框；`PaperViews.tsx:81` 将同页无框角标全部叠在 `{ top: 0, right: 0 }`；`PaperViews.tsx:101` 启动时 `Promise.all` 全页拉取 `PDFPageProxy` 阻塞长文档跳转。
   - `.agents/core/source_reading.py:118` vs `136` 混用 `splitlines()` 与 `split('\n')` 导致 `\r\n` 文件字符偏移漂移。
3. **版本身份与高亮失配**：
   - 现有 `bundleVersion` 只覆盖 `content.md` 与 `images/`，**不覆盖原始 `source.pdf`、页尺寸、块顺序或坐标**；若仅依赖 `bundleVersion` 绑定 PDF 坐标，在“正文相同、PDF 重排”场景下历史证据会高亮到错误位置。
   - 现有 `pdf_layout.py:118` 的 `layoutVersion` 实际由显式版本常量 `'1'` + `source.pdf` 摘要 + `content.md` 摘要 + `middle_json.json` 摘要拼接生成，语义正确，应当**继承并规范化升级**而非废弃。
4. **渲染态文本失配与工具参数限制**：
   - 后端校验含 Markdown 标记/LaTeX 的原始文本，前端 `source-evidence.ts:19-30` 在渲染态 HAST 纯文本中做 `indexOf` 易失败退化；
   - `host/core_bridge.py:18-40` 的 `ACTIONS` 参数白名单当前仅允许 `read_range(start, end, source_id, bundle_version)`，若直接让模型传 `block_ids` 会被参数校验拒绝。
5. **视图与精读断层**：精读 `ReadingChunk.tsx:77` 未调用 `citedMarkdown()` 导致对话产生的 `[[e:24位hex]]` 原始标记裸露。

---

## 2. 前置核心协议（必须先于解析器改造闭环）

### 2.1 双轨版本身份：保留 `bundleVersion`，新增独立 `layoutVersion`（防重排误标）

| 版本字段 | 覆盖范围 | 职责边界 |
| :--- | :--- | :--- |
| `bundleVersion`（保留现有） | `content.md` + `images/` 摘要 | 证明规范化正文与图片资产未变；决定文字引文与对话记录是否可读。 |
| `layoutVersion`（升级独立字段） | `sha256(ir_schema_version + source.pdf_sha256 + content.md_sha256 + normalized_pages_and_blocks_geometry_sha256)` | **唯一证明 PDF 版面与几何坐标身份**。只要 `source.pdf` 替换、页尺寸/旋转变化或块坐标重排，`layoutVersion` 必然变化。 |

- 普通导入按 PDF 原件识别来源。重排后的另一份 PDF 单独注册为新的 Reading Source，即使两者派生出相同正文与图片。
- **防误标铁律**：前端在原文 PDF 视图渲染高亮框时，**必须同时校验 `evidence.bundleVersion === doc.bundleVersion` 且 `evidence.layoutVersion === doc.pdf.layoutVersion`**。若正文相同但 PDF 重排（`bundleVersion` 相同、`layoutVersion` 不同），**历史证据仍可在证据卡中阅读原文引文，但严禁绘制到新版 PDF 坐标上**（明确提示“原文 PDF 版面已变更，仅保留文字引文”）。

同一 `sourceId` 与 `bundleVersion` 下重新分块时，使用历史证据保存的原文行范围、逐字引文与上下文重新验证。唯一命中后，按该区间覆盖的当前块关联中文译文及精读段落。验证失败时只展示历史引文。原文 PDF 绘框仍须匹配签发时的版面版本。

### 2.2 签发校验与界面高亮解耦（两道独立门禁）

严守 ADR 0034 对回答证据的可信承诺，**禁止**以“公式/表格/跨块”为由放宽 `cite` 的存在性与唯一性校验：

1. **门禁 1 · 证据签发校验（Backend `SourceReading.cite`，严格拒绝制）**：
   - 无论目标块是正文、公式、表格、图片还是跨块引用，`read_range` 返回可直接复制的规范 Markdown。模型**必须**提供在该 Markdown 的绑定范围内逐字且唯一命中的 `quote`（及可选 `prefix` / `suffix`；对无正文图片/图表须引用其精确 `caption` 或可在规范正文中逐字读取的块标识文本）。
   - 跨块引文必须在规范 Markdown 中连续，保留段间换行。`block_ids` 只缩小查找范围，整个命中区间都须落在所选范围内。隔着 B 块的 A、C 两处引文应分别签发。
   - 引文缺失、不存在或在绑定范围内匹配次数 `!== 1`（歧义）时，**一律拒绝签发**并返回明确错误，绝不降级放行。
2. **门禁 2 · 界面高亮粒度决策（仅在门禁 1 通过后执行）**：
   - 例如正文为 `uses **continual re-solving**`，仅提交 `uses continual re-solving` 须拒签。`plain_text` 用于签发后的显示投影。
   - 证据卡保留已签发的逐字引文。点击证据时以当前视图为首选。在中文译文中始终留在译文，关联可靠时标出对应译文段落，关联缺失时保留阅读位置并展示原文引文。在原文 PDF 中优先展示对应块的全部可靠框，仅有可靠页码时跳到该页。缺少可靠 PDF 位置或版面版本失配时，点击证据卡直接切换到中文译文并定位对应证据块。若译文也缺少可靠关联，则在译文视图展示原文引文。

### 2.3 可选的行内高亮扩展

字符偏移、行内着色和 PDF 行框均为可选增强。采用行内定位时遵循以下偏移契约。

Python `str` 索引按 Unicode 码点计，而浏览器 JavaScript `string.slice` 与 DOM `Text` 节点偏移按 **UTF-16 码元（Code Unit）** 计，含 Emoji 或扩展区汉字时直接传 Python 索引会发生偏移漂移。强制规定：

- **规范化文本函数 `canonical_plain_text(node)`**：前后端共用同一套确定性规则（LF 换行、连续空白折叠为单空格、剥离纯语法标记但不丢弃链接可见文字、保留公式/代码的稳定占位或源码文本）。
- **字符单位与区间边界**：`textOffsets: [{ blockId, start, end }]` 统一采用 **UTF-16 code units**（后端计算时通过 `len(text[:idx].encode('utf-16-le')) // 2` 换算）和**左闭右开区间 `[start, end)`**。

### 2.4 坐标系统一与未知坐标系安全降级规则

- **禁止仅靠 `page_size` 猜测坐标单位**：PDF 页尺寸（如 `612 × 792 pt`）无法区分 MinerU 输出的是 72 DPI 点坐标、150/200 DPI 渲染像素坐标还是 `[0, 1000]` 千分比坐标。
- **显式声明优先，未知一律降级**：`PdfIrBuilder` 仅在解析器产物携带明确坐标空间契约（例如本地 MinerU 4.2.3 已知 `[0, 1]` 归一化或带显式 `page_size` 与坐标基线的 Schema）时才换算为 `normalized_top_left`（`[0, 1]`，原点左上角，并计入页面 `rotation`）；凡坐标空间不明、越界或缺失参考基准的块，**强制降级为 `granularity: "page"`（页级定位）**，绝不盲猜绘制错位框。

---

## 3. 统一输入解析协议：`parser-bundle/source-ir.json`（v1）

```json
{
  "ir_version": 1,
  "source_kind": "paper_pdf",
  "bundle_version": "<sha256-content-and-images>",
  "layout_version": "<sha256-schema-pdf-content-geometry>",
  "coord_standard": "normalized_top_left_v1",
  "pages": [
    { "page_index": 0, "page_number": 1, "width": 612.0, "height": 792.0, "unit": "pt", "rotation": 0 }
  ],
  "sections": [
    { "section_id": "sec-001", "parent_id": null, "level": 1, "title": "Introduction", "block_ids": ["b-0001", "b-0002"], "source_lines": [1, 42] }
  ],
  "blocks": [
    {
      "block_id": "b-0002",
      "order": 2,
      "kind": "paragraph",
      "section_id": "sec-001",
      "section_path": ["Introduction"],
      "markdown": "DeepStack uses **continual re-solving** with $O(1)$ depth...",
      "plain_text": "DeepStack uses continual re-solving with O(1) depth...",
      "quote_hash": "sha256:9f86d0...",
      "anchors": {
        "markdown": { "source_lines": [5, 8], "char_span": { "start": 124, "end": 418 } },
        "text_span_utf16": { "start": 110, "end": 389 },
        "pdf": {
          "page_index": 0,
          "page_number": 1,
          "coord_space": "normalized_top_left",
          "regions": [
            { "page_index": 0, "bboxes": [[0.098, 0.142, 0.482, 0.215], [0.518, 0.085, 0.902, 0.130]], "raw_block_ref": "0-4" }
          ],
          "line_bboxes": [
            { "page_index": 0, "bbox": [0.098, 0.142, 0.482, 0.158], "text_range_utf16": [0, 68] }
          ],
          "confidence": "exact_ir"
        },
        "html": null
      }
    }
  ]
}
```

示例中的 `text_span_utf16` 和 `line_bboxes` 供可选的精细定位使用，Batch B 可省略。

### 3.1 工具参数白名单与 `cite` 契约扩展

- **更新 `host/core_bridge.py:18-40`**：
  - `ACTIONS['read_range']` 白名单同步放行可选 `block_ids: list[str]`（兼容现有 `start / end`）。
  - `TOOL` 描述同步更新 `search`、`read_range` 返回的 `block_id` 标头格式（`[b-0014 | p.3 | L88-93]`）及 `cite` 新增可选字段 `block_ids?: string[]`。
- **更新 `ui/packages/reader-contracts/src/source-document.ts`**：`ValidatedAnswerEvidence` 默认签发 `renderGranularity: "block"`，携带块定位字段 `blockIds`、`sectionIds`，PDF 定位使用 `pdfRegions: { pageIndex, pageNumber, bboxes, granularity: "line" | "block" | "page" }[]` 以及强校验 `layoutVersion`。其中 `"line"` 粒度以及原文可见文本的 `"exact"` 和 `textOffsets` 供可选增强使用。

---

## 4. 分两阶段落地策略（先单 PDF 垂直切片，再全格式推广）

### 4.1 Batch B：单 PDF 垂直切片（验证核心假设）

先**不改变**现有 `content.md` 的生成方式，优先拿 **1 份含跨栏与旋转页的真实 PDF** 跑通完整生产链路：

1. **修复前端多框合并与页级角标**（`PaperViews.tsx:81, 101, 109-120`）：保留同 `blockId` 的全部 `bboxes`；同页 `page-only` 角标聚合至页顶 flex 栏；改为基于 `pages[]` 宽高虚拟化占位与按需加载，点击 `[N]` 依据 `pageIndex + bbox[1]` 零延迟直达未渲染页。
2. **扩展 MinerU 归档扫描与坐标安全归一化**（`mineru.py:313` + `.agents/core/source_ir.py`）：兼容 `*_middle.json / *_content_list*.json`，已知坐标系归一化并处理旋转页，未知坐标系降级 `page_only`，计算独立 `layoutVersion`。
3. **打通工具链与两道门禁**（`host/core_bridge.py`、`reading_workspace.py`、`source_reading.py`、`METHOD.md`）：更新 `read_range` 参数白名单，签发逐字、连续且唯一的引文，证据卡显示原句，原文 PDF 定位到块或已知页面，端到端跑通 `入库 → read_range → cite → 点击回答 → 原文 PDF 多框高亮 & 反向定位`。

从来源证据块返回回答时，若点击的是刚从回答跳来时高亮的证据编号，直接返回该回答的出发位置。点击块上的通用标记时，单条关联直接返回，多条关联则列出回答摘录，由读者点选目标回答。

### 4.2 Batch C：全格式统一 IR 与精读粗粒度联动

在 Batch B 真实论文验收通过后，再推进三格式统一与精读联动：

1. **三格式 IR-First 正向派生**：PDF（`PdfIrBuilder`）、HTML（`HtmlIrBuilder`，按 DOM 块保留 `anchors.html`）、Markdown（`MarkdownIrBuilder`，接入 `IngestionApplication`）统一落盘 `source-ir.json` 并经 `IRSerializer` 确定性生成 LF `content.md`；旧 Bundle 缺失 `source-ir.json` 时只读使用现有解析资产，读者仍可继续提问并基于规范 Markdown 获得新的回答证据。
2. **原文 PDF 与中文译文联动**：读者主动切换视图时，按原文块与译文段落的对应关系同步位置。规范 Markdown 用于引文签发与重新定位。
3. **精读模式粗粒度反标（`FocusReader.tsx` / `ReadingChunk.tsx`）**：
   - `ReadingPlan` 为每个 `chunk` 写入 `blockIds[]`，以 chunk 的当前块集合与经原文验证定位的证据块集合的交集聚合关联证据。
   - 仅命中时在 `ReadingChunk` 底部渲染紧凑 **「对话证据 · N 条」折叠胶囊**。展开后点选证据，通过一次性 `PendingEvidenceJump` 切至对话 Tab，定位到对应回答并标出证据编号。读者再点击该编号，按当前阅读视图定位来源证据块（严守 00 契约，**绝不移动精读 Cursor**）。
   - 在 `ReadingChunk.tsx:77` 接入 `citedMarkdown()`，消除精读内历史回答裸露 `[[e:ID]]` 标记。

---

## 5. 验收标准（含正向与反向样本）

1. **版本防误标样本**：分别验证重排 PDF 普通导入会获得新的 `sourceId`，以及同一来源重新解析时的版本保护。后一样本固定 `sourceId`、PDF 原件、正文和图片，仅改变块坐标，验证 `bundleVersion` 不变而 `layoutVersion` 变化；旧证据在证据卡中仍可正常读原文引文，且**绝对不会绘制到新版 PDF 版面上**。
2. **签发拒绝与边界文本样本**：
   - 重复引文、缺失引文 → `cite` 严格拒绝；
   - 含链接目标文本、Emoji 前缀 → 点击证据可在证据卡核对逐字引文；
   - 公式或表格的引文验证通过 → 标出对应对象块。
3. **复杂 PDF 与坐标系降级样本**：含跨栏与旋转页的真实 PDF 端到端多框高亮命中并支持点击反跳回答；未知坐标系输入安全降级为 `page_only`，绝不绘制错位框。
   - 对同一条有可靠 PDF 框的证据，分别从原文 PDF 和已关联的中文译文点击，均应留在当前视图并命中对应位置。另从 PDF 点击仅有可靠页码的证据，应留在 PDF 并跳页；从 PDF 点击既无可靠框也无可靠页码、但有对应译文块的证据，应直接切到中文译文并定位该块。版面版本失配时同样验证此跳转。从中文译文点击缺少译文关联的证据，应留在译文原位置并显示原文引文。
   - 同一证据块关联两条回答时，点击通用标记可通过回答摘录选择目标；从第二条回答跳来再点击高亮编号，应直接返回第二条。仅有一条关联时直接返回。
4. **旧 Bundle 与精读兼容**：无 `source-ir.json` 的历史 Bundle 可展示历史证据并继续提问。用旧正文中的唯一引文签发一条新证据，验证原 Bundle 文件保持原样，按当前视图定位或展示引文。展开精读证据列表并选中一条，验证先定位到对应回答的证据编号，再点击编号才定位到来源，整个过程 Cursor 保持原位，历史回答无裸露 `[[e:ID]]`。
