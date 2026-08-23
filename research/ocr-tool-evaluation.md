# 学术 PDF OCR / 文档解析工具评估

> **现行实现说明（2026-08-23）：** 本文保留为 2026-08-01 的本地解析器选型历史证据。项目现已按用户要求改为仅使用 MinerU 网页端精准解析 API；当前行为以 README、`paper-parser` 和 `paper-map` 为准，本文的“本地 Docling 默认”结论不再是运行时配置。

> 评估日期：2026-08-01  
> 范围：Paper Companion 的论文摄取（ingest）适配器  
> 证据边界：工具能力与许可只引用项目官方仓库、官方文档、官方模型卡、官方许可和云厂商官方定价页；另对工作区中的 `A04_FlexSA.pdf` 做了只读结构检查与页面抽样渲染，但没有运行候选 OCR/解析器的质量横评。

## 1. 结论先行

Paper Companion 的首个本地默认适配器应采用 **Docling 标准流水线**，开启公式增强，保留 lossless JSON，并以 referenced-image 模式导出图片。它最适合当前阶段，不是因为已经证明识别质量绝对最高，而是因为它同时满足以下工程约束：

- 官方明确支持 Windows、Linux、macOS，可完全本地和离线运行；
- 代码采用 MIT 许可证；
- `DoclingDocument` 原生保留页面、边界框、层级、表格、图片等结构和 provenance，适合生成可追溯的 source map；
- 可同时导出 Markdown、HTML、DocTags 与 lossless JSON，而不是把 Markdown 当成唯一真相源；
- 不要求 API Key、账号或把论文上传到第三方。

这些能力见 [Docling 官方仓库](https://github.com/docling-project/docling)、[安装说明](https://docling-project.github.io/docling/getting_started/installation/)、[DoclingDocument 数据模型](https://docling-project.github.io/docling/concepts/docling_document/)与[序列化说明](https://docling-project.github.io/docling/concepts/serialization/)。

同时应资格化 **MinerU pipeline** 作为第一质量回退：它对公式、表格、图片、图表、标题层级和页面坐标提供更直接的结构化输出，但本地资源成本更高，且代码、模型权重、商业使用附加条件必须分别锁定和审计。**PaddleOCR-VL / PP-StructureV3** 可作为隔离环境中的中文、扫描件和复杂版面实验后端。

不建议把 Marker + Surya、Nougat 或任何托管 API 设为默认路径。托管服务中，Mathpix 是公式密集论文最有针对性的人工授权回退；Azure Document Intelligence 与 Google Document AI 更适合已有相应云治理体系的组织。任何云上传都必须逐次得到用户明确同意。

因此，当前决策不是“选出永远唯一的 OCR 引擎”，而是建立一个稳定、可审计的后端适配器边界：

1. 默认在本地跑 Docling；
2. 默认结果未过质量门时，在新的 staging run 中完整重跑 MinerU；
3. 对中文扫描件或专用 GPU 场景，可显式选择 PaddleOCR-VL；
4. 只有用户明确批准上传时，才允许调用 Mathpix、Azure 或 Google；
5. 不在一次结果中静默拼接多个引擎，也不把无法追溯来源的“修复文本”写进 canonical artifact。

## 2. Paper Companion 所需的硬边界

根据 `paper_companion_skill_suit.md` 的摄取契约，解析器不应直接拥有工作区状态。它只负责在 staging run 中，把输入 PDF 转换为一组可验证候选产物：

- 原始 `source.pdf` 及其 SHA-256；
- 非空 `paper.md`；
- 可解析的 `metadata.json`；
- 可为空但引用必须有效的 `images/`；
- 后端的原始结构化输出；
- 页面、边界框或其它可用定位信息，用于构建 source map；
- 明确区分 blocking errors 与 warnings 的质量报告。

对公式、表格或关键图示的严重损坏不能降级成普通 warning；它会改变论文语义，应阻止 promotion。另一方面，工具未提供页码时可以保存 `page: null`，不能编造页码。由此得出三个实现原则：

### 2.1 Markdown 不是唯一真相源

Markdown 很适合阅读，却经常丢失合并单元格、精确坐标、阅读顺序置信度和图片裁切信息。适配器必须保存引擎原始 JSON，并从 JSON 生成标准化节点；Markdown 只是一个阅读投影。

### 2.2 许可证需要同时锁定代码与模型

现代文档解析器通常由开源代码、独立发布的模型权重、OCR 子引擎和可选 LLM 组成。仅记录仓库许可证不够。`metadata.json` 至少应记录：代码版本、模型仓库与 revision、各自许可证标识、下载来源、运行参数和运行环境。

### 2.3 回退是新的一次可审计运行

如果默认后端未过门，回退后端应生成新的 run id、原始输出和质量报告。系统可以比较两次结果，但不能悄悄用 A 的正文、B 的公式和 C 的图片拼成一个看似单一来源的文件。若未来允许对象级合并，每个节点都必须携带独立 provenance。

### 2.4 本地样本 `A04_FlexSA.pdf` 的预检结论

对工作区样本做了只读检查（SHA-256 `FBF6BE55D74985716C65F4132ABF745D80B69DB32212CD211AA3692D079EC93E`，1,670,654 bytes）。它是 pdfTeX 生成的 13 页、未加密、双栏学术 PDF；13 页都有原生文本层。`pypdf` 共抽取 71,915 个字符，各页为 1,362–8,496 个字符，没有空文本页。抽样渲染确认正文、双栏阅读顺序、算法块、公式与图示并存。

这份样本不应默认做整页 OCR。预检还发现：文本中有 160 个 `ﬁ`、25 个 `ﬂ`、3 个 `ﬀ` 连字以及少量控制字符，算法块和数学表达的空格会退化；PDF 页面资源中没有 raster image XObject，却有 16 个 vector Form XObject。也就是说，纯文本抽取会漏掉版面和矢量图示语义，而只导出内嵌位图的解析器会漏掉论文中的重要图形。

因此该样本的首选路径应是：先通过文本层健康门，保留原生文字；再用布局感知解析器恢复双栏顺序、标题、caption、表格和公式；对矢量 figure 按检测区域渲染/裁切，而不是只枚举 PDF 图片对象；最后规范化连字和控制字符，并对关键公式、算法块和图注做页面锚定抽检。只有文本层缺失、乱码或对象级质量门失败的页面才进入 OCR 回退。这个结论是 PDF 结构预检，不是 Docling、MinerU 等候选后端在该论文上的质量排名。

## 3. 总览矩阵

| 后端 | Windows / 本地可行性 | 代码与模型许可 | 主要输出与定位 | 公式、表格、图像能力 | 凭据与外部成本 | 建议角色 |
|---|---|---|---|---|---|---|
| **Docling** | 官方支持 Windows；CPU/GPU；可离线 | 代码 MIT；模型逐一审计 | Markdown、HTML、DocTags、lossless JSON；页码、bbox、层级 provenance | 公式增强可输出 LaTeX；表格和图片结构化；Markdown 会压平合并单元格 | 本地模型首次下载；无服务账号/API Key | **默认本地适配器** |
| **MinerU** | 官方支持 Windows；pipeline 可 CPU；VLM/高质量模式更重 | 代码为 MinerU 自定义开源许可；模型许可可能不同 | Markdown、content list / middle / model JSON；页码、bbox、公式 LaTeX、表格 HTML、图片 | 能力覆盖最完整；复杂扫描件仍需实测 | 本地安装约需较大内存/磁盘；公共模型下载，无云 Key | **首选质量回退** |
| **PaddleOCR-VL / PP-StructureV3** | Paddle/Transformers 可原生 Windows；vLLM/SGLang/FastDeploy 路径通常需 Linux/Docker | Apache-2.0 代码；官方模型通常 Apache-2.0，仍需按 revision 记录 | JSON、Markdown、表格 HTML/XLSX、图片；多页结果可重组 | 文字、公式、表格、图表，中文与扫描件有吸引力 | 约 0.9B VLM；依赖组合复杂；无服务 Key | **隔离的实验回退** |
| **Marker + Surya** | Python/PyTorch 本地；官方未把原生 Windows 作为明确支持承诺，优先视作 WSL2/Docker 待资格化 | 当前 `master` 代码均为 Apache-2.0；模型权重为带额外商业和竞争用途限制的修改版 OpenRAIL | Markdown、JSON、HTML、chunks、图片；多边形与 block tree | 数学、表格、图片较强；可选 LLM 会引入额外凭据与来源 | Surya 2 约 650M；服务启动和模型装载重 | **不作默认；研究用途可选** |
| **Nougat** | 可本地；Windows GPU 需先配置匹配的 PyTorch | 代码 MIT；权重 CC-BY-NC | Mathpix Markdown (`.mmd`) | 针对学术公式/表格；缺少完整图片资产与版面 provenance | nougat-base 权重体积较大；无 Key | **拒绝作为主适配器** |
| **Mathpix API** | OS 无关的 HTTPS API | 专有 SaaS | MMD、lines JSON、LaTeX、HTML、DOCX、XLSX、图片包；行级 bbox | STEM 公式、表格、化学式是强项 | 注册、`app_id`/`app_key`、付费；上传和保留风险 | **显式授权的公式回退** |
| **Azure Document Intelligence** | OS 无关 SDK/REST；无本地模型 | 专有 SaaS | 结构化 JSON、Markdown、HTML tables、figure crop、polygon/span | 公式为付费 add-on；公式阅读顺序有已知限制 | Azure 订阅、资源 endpoint/key 或身份、按页计费 | **已有 Azure 治理时可选** |
| **Google Document AI** | OS 无关 SDK/REST；无本地模型 | 专有 SaaS | `DocumentLayout` / OCR JSON、chunks、表格、图示 | Math OCR 输出 LaTeX/bbox；与 Layout Parser 可能需组合 | GCP 项目、billing、processor、ADC；按页计费 | **RAG/云治理场景可选** |

表中“能力强”只代表官方接口覆盖，不代表跨工具的实测质量排名。各厂商使用不同数据集、硬件和指标，官方 benchmark 不可直接横向比较。

## 4. 本地开源方案详评

### 4.1 Docling

#### 可行性与运行成本

Docling 官方列出 Windows、Linux、macOS，以及 x86_64 / arm64 支持；Python 要求为 3.10 及以上。标准流水线可在 CPU、CUDA、MPS 或 XPU 上运行，并允许提前下载模型后完全离线使用。模型可以通过 `docling-tools models download` 预取，再用本地 artifacts path 运行。远程服务默认关闭，适合“论文不得自动外传”的安全边界。[安装说明](https://docling-project.github.io/docling/getting_started/installation/)、[模型目录](https://docling-project.github.io/docling/usage/model_catalog/)

官方没有给出一个适用于所有流水线的固定最低 RAM/VRAM，因为成本取决于 OCR 引擎、TableFormer、公式增强和 VLM preset。适配器因此不应写死虚假的最低显存，而应记录实际 pipeline、device、模型 revision、耗时与峰值资源；首次资格化同时测 CPU 基线和可用 GPU。

#### 输出与 source map 适配性

`DoclingDocument` 是统一结构模型，包含文档层级、正文、表格、图片和 provenance。`ProvenanceItem` 提供页码、bbox 与字符区间；这正好可以映射为 Paper Companion 的 section / claim / evidence source anchors。[文档模型](https://docling-project.github.io/docling/concepts/docling_document/)、[provenance API](https://docling-project.github.io/docling/reference/docling_document/)

官方导出接口支持：

- Markdown、HTML、DocTags 与 lossless JSON；
- 页面图、figure/table 裁切图和引用式或嵌入式图片；
- 独立保存表格及图片资产；
- 通过标准序列化器保留层级和引用关系。

参见[支持格式](https://docling-project.github.io/docling/usage/supported_formats/)、[图片和表格导出示例](https://docling-project.github.io/docling/_generated/examples/export_figures/)与[序列化说明](https://docling-project.github.io/docling/concepts/serialization/)。

#### 公式、表格和图示

公式增强不是默认保证；需显式启用 `do_formula_enrichment`，由专用模型把公式转换为 LaTeX。表格在 lossless JSON / HTML 中可以保留 rowspan/colspan，但 Markdown 投影会压平合并单元格。因此质量门必须检查原始表格结构，不可只检查 Markdown 是否有竖线。[流水线选项](https://docling-project.github.io/docling/reference/pipeline_options/)、[序列化限制](https://docling-project.github.io/docling/concepts/serialization/)

图片可保存为外部文件并在 Markdown 中引用；适配器应使用 referenced-image 模式，把资产复制到 staging `images/`，验证路径、哈希和引用完整性后再 promotion。

#### 许可与限制

Docling 代码仓库是 MIT。默认模型与可选 OCR/VLM 模型的许可证并不自动等同于代码许可证；官方模型目录也明确区分模型。比如 IBM Granite Docling 258M 的模型卡列为 Apache-2.0，而其它 OCR 后端可能采用不同条款。[Docling 许可](https://github.com/docling-project/docling/blob/main/LICENSE)、[Granite Docling 模型卡](https://huggingface.co/ibm-granite/granite-docling-258M)

关键限制：

- Markdown 丢失部分表格结构；
- 公式质量取决于是否启用增强和具体模型；
- PDF 的视觉样式不会被无损复刻；
- 仓库当前把部分文档 metadata 提取仍列为后续能力，因此 Paper Companion 必须自己构造稳定的 `metadata.json`；
- 首次模型下载需要网络，离线环境必须提前预取并锁定模型。

#### 结论

**接受为 MVP 默认后端。** 推荐配置为标准 PDF pipeline、可用时启用 OCR、启用公式增强、生成 page/picture images，并同时导出 Markdown 与 lossless JSON。默认不调用 remote service，不启用需要外部 LLM 的增强。

### 4.2 MinerU

#### 可行性与运行成本

MinerU 官方 quick start 支持 Windows、Linux 和 macOS。Windows 上受 `ray` 兼容性约束，官方列出的 Python 范围比其它平台更窄；Windows Docker 路径依赖 WSL2。pipeline 后端可纯 CPU 运行，而 VLM、hybrid 和高吞吐后端对显存要求不同。[快速开始](https://opendatalab.github.io/MinerU/quick_start/)、[Windows FAQ](https://opendatalab.github.io/MinerU/faq/)

官方给出的本地部署量级是至少约 16 GB RAM、推荐约 32 GB；完整本地模型与环境需要显著磁盘空间，quick start 给出的本地部署预算约 20 GB。具体 GPU 最低显存随 backend 变化，不能统一成一个数字。Paper Companion 应优先资格化较轻的 pipeline 方案，再根据硬件显式启用 hybrid / VLM。

模型默认可从 Hugging Face 或 ModelScope 获取，也可提前下载到本地并指定模型源；本地公共模型路径不需要云推理 API Key。[模型源和离线下载](https://opendatalab.github.io/MinerU/usage/model_source/)

#### 输出与 source map 适配性

MinerU 的官方输出不只有 Markdown，还包括多个 JSON 层级与调试 PDF。`content_list.json` / 中间结构可以包含 `page_idx`、bbox、文本块、标题、图片、图表、caption、footnote、表格 HTML 和公式 LaTeX；调试 PDF 可可视化 layout/span 识别。这使它非常适合作为质量诊断后端。[输出文件说明](https://opendatalab.github.io/MinerU/reference/output_files/)

适配器应直接消费结构化 content list，而不是重新从 Markdown 反解析页码。图片和图表资产进入 `images/`，表格 HTML 与公式 LaTeX保存在原始 JSON，同时投影到 `paper.md`。

#### 许可与版本风险

MinerU 当前代码使用自己的开源许可证，而不是简单的 MIT/Apache 标签。官方许可基于 Apache-2.0 并附加商业规模与在线服务署名等条款；超过指定业务规模需要另行商业许可。[MinerU LICENSE](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md)

更重要的是，**不同模型 revision 的许可可能不同**。例如较早的官方 MinerU2.5 模型卡标示 AGPL-3.0，而较新的模型可能标示 Apache-2.0。不能用“仓库开源”推断“所有模型可无条件使用”。资格化记录必须固定代码 commit、模型完整 ID/revision、模型卡许可和文件哈希。[MinerU2.5 官方模型卡示例](https://huggingface.co/opendatalab/MinerU2.5-2509-1.2B)

#### 限制

- 安装、模型和资源成本高于 Docling MVP；
- pipeline、VLM、hybrid 的能力不同，例如较轻模式可能不包含图像理解，不能把一种 backend 的结论推广到另一种；
- 复杂版面、低质量扫描、手写内容依旧可能失败，官方也要求按场景评估；
- 版本、输出 schema 和许可变化较快，适配器不能追随浮动 `latest`；
- 自定义许可证需要在进入产品默认路径前做明确合规确认。

#### 结论

**接受为第一本地质量回退，但先通过代表性语料资格化。** 对数字原生论文先测 pipeline；只有硬件与质量收益证据充分时才启用更重的 hybrid-high / VLM。每种 backend 都作为不同的 parser identity 记录，不能统称为 `mineru`。

### 4.3 PaddleOCR-VL 与 PP-StructureV3

#### 可行性与运行成本

PaddleOCR 项目采用 Apache-2.0，当前文档解析路线包括 PP-StructureV3 和约 0.9B 参数的 PaddleOCR-VL。官方安装文档支持在 x64 CPU 或 NVIDIA GPU 上使用 PaddlePaddle / Transformers 本地推理，Python 3.9–3.13，PaddlePaddle 3.2.1 及以上。[PaddleOCR 官方仓库](https://github.com/PaddlePaddle/PaddleOCR)、[PaddleOCR-VL 使用说明](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/PaddleOCR-VL.html)

原生 Windows 可走 PaddlePaddle 或 Transformers；vLLM、SGLang、FastDeploy 等高性能 serving 路径不应被宣称为原生 Windows 支持，通常需要 Linux/Docker。不同 serving 框架对 CUDA 与计算能力还有额外要求。官方也提醒依赖组合可能冲突，因此应使用独立虚拟环境或容器，不能把它混入 Docling 默认环境。

#### 输出与能力

PaddleOCR-VL / PP-StructureV3 可把 PDF 页面解析为 JSON 和 Markdown，并覆盖文字、公式、表格、图表和版面元素；表格还可导出 HTML/XLSX，公式识别模块输出 LaTeX。多页 PDF 默认产生逐页结果，`restructure_pages` 可进行跨页重组、标题层级调整和表格拼接。[PP-StructureV3](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/PP-StructureV3.html)、[公式识别](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/formula_recognition.html)

Markdown 可引用相对图片路径或嵌入 Base64。Paper Companion 应选择外部图片文件，禁止把大型 Base64 塞入 canonical Markdown；同时保存逐页 JSON，避免跨页重组掩盖原始定位。

#### 限制

- 官方明确警告：只调用核心 VLM 并不等同于完整文档解析 pipeline，可能出现大量幻觉文本；
- 部分 Transformers 示例面向元素级识别而不是整页流水线；
- 高性能 serving 与原生 Windows 之间存在部署断层；
- 依赖、CUDA 版本和模型组合复杂，升级容易破坏可重复性；
- 跨页表格重组会改变结构，必须保留重组前的逐页输出和映射。

#### 结论

**接受为隔离的实验后端。** 它尤其值得在中文、扫描件和图表较多的代表性语料上与 MinerU 比较，但在依赖稳定性、Windows 路径和幻觉门控通过之前，不升为默认。

### 4.4 Marker + Surya

#### 架构与输出

Marker 是面向 PDF/图片的转换层，当前版本使用 Surya 进行 OCR、layout、reading order 与 table recognition，并可输出 Markdown、JSON、chunks 和 HTML。其 JSON 以页面和 block tree 表示内容，包含 block ID/type、polygon、section hierarchy 和图片；公式写入数学标记，表格可表示为 HTML。[Marker 官方仓库](https://github.com/datalab-to/marker)

Surya 也可独立输出逐页 JSON，包括按阅读顺序排列的 block、标签、HTML、bbox/polygon、confidence 与 error。它更像 OCR/layout 工具箱，不直接产生 Paper Companion 所需的完整 artifact pack，因此如采用应通过 Marker，而不是另建一个 Surya-only canonical adapter。[Surya 官方仓库](https://github.com/datalab-to/surya)

#### 本地、许可与运行成本

截至本报告评估日，Marker 与 Surya 官方 `master` 的代码许可证均为 Apache-2.0；两者模型权重使用带额外商业条件的修改版 AI Pubs Open Rail-M。其 Attachment A 的门槛是：所属实体上一年度 gross revenue **超过 500 万美元**，或累计 equity/debt funding **超过 500 万美元**时，不得作一般商业用途，个人或研究用途除外；许可还禁止用于与 licensor 或其 affiliates 的产品/服务竞争，并对 attribution / share-alike 作出要求。历史发行版的代码许可和门槛曾有变化，所以采用时必须固定 commit 和模型 revision，并按该快照中的完整 LICENSE 审查，不能沿用版本无关的摘要。代码许可与模型许可必须分开记录。[Marker 代码许可](https://github.com/datalab-to/marker/blob/master/LICENSE)、[Marker 模型许可](https://github.com/datalab-to/marker/blob/master/MODEL_LICENSE)、[Surya 代码许可](https://github.com/datalab-to/surya/blob/master/LICENSE)、[Surya 模型许可](https://github.com/datalab-to/surya/blob/master/MODEL_LICENSE)

Surya 2 约 650M 参数，并带来相对上一代的输出 schema 破坏性变化。官方本地推理路径依赖 Python/PyTorch；加速 serving 主要围绕 NVIDIA Docker/vLLM，CPU/Apple Silicon 可走 llama.cpp。官方并未把原生 Windows 作为清晰承诺，因此 Paper Companion 不能在没有实际安装证据时声称 Windows 开箱即用。

Marker 的可选 LLM 模式可改善行内数学和跨页表格，但 Gemini 等后端会引入 API Key、云上传和不可控生成；本地 Ollama 也会增加模型与 provenance。默认适配器不得自动启用该模式。官方还把内置 FastAPI 服务描述为面向小规模、鲁棒性有限的服务，不能直接当生产守护进程。

#### 结论

**不作为默认或首选回退。** 主要原因不是能力不足，而是模型权重许可、原生 Windows 路径、schema 变化与可选 LLM provenance 的综合成本。若未来研究使用，应锁定版本、关闭云 LLM、使用独立 WSL2/Docker 环境并完成许可审查。

### 4.5 Nougat

Nougat 是 Meta 发布的学术文档理解模型，代码采用 MIT，模型权重采用 CC-BY-NC。它直接把论文页转换为 Mathpix Markdown，擅长 LaTeX 数学和表格表示，适合把学术 PDF 恢复为 `.mmd`。[Nougat 官方仓库](https://github.com/facebookresearch/nougat)、[nougat-base 模型卡](https://huggingface.co/facebook/nougat-base)、[论文](https://arxiv.org/abs/2308.13418)

但它不适合作为 Paper Companion 主解析器：

- 训练数据主要来自 arXiv 与 PMC，官方说明英语表现最佳，中文、俄语、日语不工作；
- CPU 或旧 GPU 上可能误触发 `[MISSING_PAGE]`；
- 输出重点是 MMD，不提供同等完整的 figure asset、layout tree 与页面 source-map 契约；
- 权重是非商业许可；
- 模型与集成路线相对老，官方模型卡还提示 Transformers 新版本已移除对应通用 image-to-text pipeline，需要直接加载或固定旧版本。

**结论：拒绝作为主适配器。** 如需研究，可把它作为英语数学论文的离线比较 oracle，但结果不得自动进入 canonical artifact。

## 5. 托管服务详评

所有托管服务都意味着把原始论文或页面发送给第三方。即使技术上有 API Key，也不能视为用户已授权上传。Paper Companion 默认配置必须完全禁用这些后端；credentials 只从进程环境或系统凭据提供，绝不写入工作区、日志、run manifest 或 Markdown。

### 5.1 Mathpix

Mathpix PDF API 使用 `app_id` 与 `app_key` 鉴权，需要注册和计费设置。官方定价页在本次评估时列出一次性账号设置费用以及按页计费；价格会变化，运行前应重新读取官方定价，不能把本文数字写死进产品逻辑。[鉴权](https://docs.mathpix.com/reference/authentication)、[API 定价](https://website.mathpix.com/pricing/api)

它的主要优势是 STEM 输出：PDF 可转换为 Mathpix Markdown、LaTeX、HTML、DOCX、XLSX 等；`lines.json` 可包含行文本、数学类型、bbox、手写标志和置信度；压缩包可携带图片资产。[PDF 处理](https://docs.mathpix.com/guides/pdf-processing)、[支持格式](https://docs.mathpix.com/reference/supported-formats)

限制与风险：

- 专有云服务和按页成本；
- 需要账号、Key 和网络，不能成为无凭据工作流 blocker；
- 官方数据保留说明称源文档/页面图和派生输出可能按不同周期保留，虽有删除与设置能力，仍需用户知情同意和组织数据政策评估；
- 服务配额、PDF 大小与并发受限制。

参见[数据保留](https://docs.mathpix.com/concepts/data-retention/)与[限制和配额](https://docs.mathpix.com/reference/limits-and-quotas)。

**结论：托管方案中的首选公式回退。** 仅当本地结果因关键公式/表格损坏被质量门阻止，且用户明确批准该文档上传时启用。

### 5.2 Azure AI Document Intelligence

Azure 的 `prebuilt-layout` 可通过 REST/SDK 输出结构化 JSON，也可请求 Markdown；当前 Markdown 中的复杂表格使用 HTML 表示。figure 对象包含页码、polygon、spans、关联元素和 caption，并可通过单独接口获取裁切图。[Layout 模型](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0)

公式识别是额外付费能力，输出行内/展示公式的 LaTeX、polygon 与 spans。官方文档特别说明公式置信度为硬编码值，并且公式在初始结果中可能出现在每页末尾；因此不能盲信其阅读顺序，必须用 polygon/span 重新锚定。[附加能力与公式限制](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept/add-on-capabilities?view=doc-intel-4.0.0)

使用需要 Azure 订阅、Document Intelligence resource、endpoint 和 key 或受支持的云身份。页数、文件大小和层级限制随 F0/S0 等级不同，费用按页和 add-on 计算；具体地区价格应从官方页面实时读取。[服务限制](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/service-limits?view=doc-intel-4.0.0)、[定价](https://azure.microsoft.com/en-us/pricing/details/ai-document-intelligence/)

**结论：只在用户已有 Azure 租户、身份与数据治理时考虑。** 对公式密集论文，它不比 Mathpix 更直接，且公式阅读顺序限制需要额外修复。

### 5.3 Google Document AI

Google 有两条相关但并不完全重合的能力：

- Enterprise Document OCR 提供文字、版面与可选 Math OCR；Math OCR 可以输出 LaTeX 与 bbox；
- Gemini Layout Parser 输出 `DocumentLayout` 树、上下文 chunk、表格和图示，并可生成图表 verbalization，更偏向检索/RAG。

参见[Enterprise Document OCR](https://docs.cloud.google.com/document-ai/docs/enterprise-document-ocr)与[Layout Parser](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk)。

使用需要 GCP project、billing、启用 API、创建 processor，并通过 Application Default Credentials、用户登录或 service account 鉴权。它不是只填一个 API Key 即可运行的轻量回退。[客户端库与鉴权](https://docs.cloud.google.com/document-ai/docs/libraries)

官方当前定价按页区分 OCR、OCR add-ons 与 Layout Parser；在线请求和 batch 的页数/文件限制不同，较长论文通常需要 batch。某些较新的 Gemini Layout Parser 版本仍带 preview/区域与数据驻留限制，不能默认选择浮动最新版。[定价](https://cloud.google.com/document-ai/pricing)、[配额和限制](https://docs.cloud.google.com/document-ai/limits)

公式与结构可能需要组合 Enterprise OCR 和 Layout Parser 的两个结果，这会增加对象级 provenance 和计费复杂度。Layout Parser 的原生目标是 `DocumentLayout` / chunks，而不是 Paper Companion 的可阅读 Markdown 包。

**结论：不作为通用论文摄取回退。** 仅在已有 GCP 数据治理，且目标明确偏向 RAG/chunking 时采用；版本必须固定，preview 模型需显式 opt-in。

## 6. 推荐的 ingest adapter 设计

### 6.1 稳定接口

建议把具体引擎藏在一个窄接口之后，概念上只暴露：

```text
parse(source_pdf, run_dir, parser_config) -> ParseCandidate
validate(ParseCandidate, quality_profile) -> QualityReport
promote(ParseCandidate) -> CanonicalPaperArtifacts
```

`ParseCandidate` 至少包含：

- `paper_markdown_path`
- `metadata_path`
- `images_dir`
- `raw_output_paths[]`
- `source_anchors[]`：标准化为 page、bbox/polygon、char span、backend block id（能提供多少就提供多少）
- `parser_identity`：backend、代码 version/commit、模型 ID/revision、模型 hash、各许可证、pipeline options
- `runtime_evidence`：OS、Python、device、耗时、峰值内存/显存（可测时）、warning/error

具体后端映射：

| 标准字段 | Docling | MinerU | PaddleOCR | Marker/Surya | 云服务 |
|---|---|---|---|---|---|
| page | provenance `page_no` | `page_idx` | page result index | page index | page / pageAnchor |
| geometry | bbox | bbox | bbox/polygon | polygon | polygon / boundingPoly |
| formula | formula item / LaTeX enrichment | equation LaTeX | formula recognition LaTeX | math block | LaTeX / MMD |
| table | table object + cell spans | table HTML | table HTML/XLSX | HTML/block tree | table cells / HTML |
| figure | picture item + referenced image | image/chart + asset | image + Markdown reference | image block/base64 | figure crop / object |
| canonical raw | lossless JSON | content list + middle/model JSON | per-page JSON | JSON block tree | raw API JSON |

### 6.2 默认配置

建议注册下列明确身份，而不是一个含糊的 `auto`：

1. `docling-standard-formula@1`：默认；标准 pipeline、公式增强、referenced images、lossless JSON、remote services disabled。
2. `mineru-pipeline@1`：本地质量回退；优先 CPU/普通 GPU 可运行配置。
3. `mineru-hybrid-high@1`：只有资格化硬件和图像理解收益证据时可选。
4. `paddleocr-vl-local@1`：独立环境中的实验后端。
5. `mathpix-pdf@1`、`azure-layout-formula@1`、`google-layout-math@1`：默认 disabled，必须携带 `user_upload_consent` 证据。

Marker/Surya 和 Nougat 暂不进入生产 registry；研究脚本可使用，但不能形成看似受支持的空配置项。

### 6.3 选择与回退流程

```text
已有同 SHA-256 且通过当前 schema/质量门的 artifact？
  ├─ 是：复用，不重新解析
  └─ 否：运行 docling-standard-formula
          ├─ 通过：promote
          └─ blocking damage：新 run 运行 mineru-pipeline
                    ├─ 通过：promote，并保留两次 run 证据
                    └─ 仍失败：
                         ├─ 中文/扫描件且本地环境合格：显式运行 PaddleOCR-VL
                         ├─ 用户批准上传且问题是 STEM 公式/表格：Mathpix
                         └─ 否则：data_insufficient / parser_blocked，不伪造完整结果
```

不能仅凭“后端返回 200/exit 0”判为成功；promotion 只由质量门决定。

## 7. 资格化语料与质量门

在把任何后端称为“受支持”前，使用同一组固定语料、同一台机器和相同评分规则。最小语料应覆盖：

- 数字原生单栏与双栏论文；
- 扫描 PDF、倾斜、噪声和混合 OCR 层；
- 行内公式、展示公式、编号公式、多行推导；
- 普通表格、合并单元格、跨页表格；
- 矢量图、位图、子图、caption 与脚注；
- 中英混排、纯中文和符号密集页；
- 参考文献、页眉页脚、脚注和阅读顺序干扰。

每次资格化至少验证：

1. **完整性**：输入页数、输出页覆盖、空页和异常页；
2. **结构**：标题层级、段落顺序、caption/footnote 归属；
3. **公式**：公式数量、编号关联、关键公式 LaTeX 语义；
4. **表格**：行列、合并关系、跨页连续性、caption；
5. **图示**：资产存在、裁切可读、引用无 orphan、caption 匹配；
6. **可追溯**：抽样节点能回到准确页码和几何区域；
7. **幻觉**：不得出现源页不存在的段落、公式或表格内容；
8. **可重复**：相同 pinned 环境运行输出 schema 稳定，非确定性差异可解释；
9. **运行性**：安装成功、模型可离线复用、失败时错误可诊断；
10. **许可性**：代码、模型、OCR 子引擎和可选 LLM 条款全部记录。

自动规则可以检查页数、JSON schema、图片引用、block 数量和几何合法性，但公式等价、跨页表格与 caption 归属仍需对语义关键对象进行人工 spot check。官方 benchmark 只能帮助选择候选，不能替代这组本地验收。

## 8. 最终取舍

### 立即实现

- `docling-standard-formula@1` adapter；
- backend-neutral staging schema 和 raw-output 保存；
- page/bbox/source-anchor 标准化；
- 图片、公式、表格和幻觉质量门；
- parser/model/license identity 记录；
- 无凭据、无网络也能完成已预取模型的本地运行。

### 紧接着资格化

- `mineru-pipeline@1`，以同一语料与 Docling 比较；
- 对 Docling 失败样本评估 MinerU 是否实质修复，而不是只比较整体文字相似度；
- `paddleocr-vl-local@1` 只在中文/扫描件子集上评估，并保持独立环境。

### 暂不进入默认产品路径

- Marker + Surya：等待原生 Windows、模型许可和 schema 稳定性证据；
- Nougat：非商业权重、语言和 artifact 结构不匹配；
- 所有云 API：默认禁用，缺少账号/Key不能阻塞本地摄取；
- 任意 LLM-based “自动修复”：除非每个修改都保留源锚点、模型身份和用户授权，否则不得写入 canonical artifact。

最终推荐可概括为：**用 Docling 建立最小、许可清晰、Windows 可运行、source-map 友好的本地基线；用 MinerU 作为有证据才升级的质量回退；让 PaddleOCR-VL 保持隔离实验；把 Mathpix 等云服务留在用户明确授权的故障恢复层。** 这与 Focus 原则一致：先把摄取过程拆成可执行、可观察、可验证的中间状态，只有每个状态过门，论文学习结果才有资格被视为可靠。
