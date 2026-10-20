// 模拟数据：文章、讨论与回答均为演示内容，未连接 FOCUS Host 或任何模型。

export type FigureRef = { id: string; label: string; caption: string; src: string; unit: number };
export type Unit = { index: number; section: string; title: string; body: string; figures: string[] };
export type Message = {
  id: string; role: "user" | "assistant"; unit: number; text: string;
  quote?: string; figure?: string; streaming?: boolean; fresh?: boolean;
};

const svg = (w: number, h: number, body: string) =>
  `data:image/svg+xml;charset=utf-8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" font-family="system-ui,sans-serif">${body}</svg>`)}`;

const roofline = svg(640, 400, `
<rect width="640" height="400" fill="#fbfaf7"/>
<g stroke="#c9c6bd" stroke-width="1">${[80, 160, 240, 320].map(y => `<line x1="70" x2="610" y1="${y}" y2="${y}"/>`).join("")}${[150, 260, 370, 480, 590].map(x => `<line y1="40" y2="340" x1="${x}" x2="${x}"/>`).join("")}</g>
<line x1="70" y1="340" x2="610" y2="340" stroke="#333" stroke-width="1.5"/><line x1="70" y1="40" x2="70" y2="340" stroke="#333" stroke-width="1.5"/>
<polyline points="70,330 330,90 610,90" fill="none" stroke="#2d5f7f" stroke-width="4"/>
<circle cx="330" cy="90" r="7" fill="#c47f17"/><text x="342" y="80" font-size="15" fill="#7a4d0b">脊点 I* = π / β</text>
<g fill="#2d5f7f" font-size="14"><circle cx="150" cy="262" r="6"/><text x="160" y="280">Attention (decode)</text><circle cx="250" cy="170" r="6"/><text x="190" y="160">LayerNorm+GEMV</text><circle cx="500" cy="90" r="6"/><text x="470" y="120">GEMM (prefill)</text></g>
<text x="340" y="380" font-size="15" text-anchor="middle" fill="#333">算术强度 I (FLOP/Byte, 对数轴)</text>
<text x="24" y="190" font-size="15" fill="#333" transform="rotate(-90 24 190)" text-anchor="middle">可达性能 P</text>
<text x="180" y="230" font-size="13" fill="#555" transform="rotate(-42 180 230)">带宽受限 β·I</text><text x="480" y="78" font-size="13" fill="#555">计算受限 π</text>`);

const hierarchy = svg(640, 380, `
<rect width="640" height="380" fill="#fbfaf7"/>
${[["寄存器", "≈ 256 KB / SM", "~ 100 TB/s", 220, "#2d5f7f"], ["共享内存 / SRAM", "228 KB / SM", "~ 30 TB/s", 300, "#3f7598"], ["L2 缓存", "50 MB", "~ 7 TB/s", 380, "#6a96b3"], ["HBM3", "80 GB", "3.35 TB/s", 460, "#9db9cc"]]
    .map(([n, c, b, w, f], i) => `<rect x="${320 - Number(w) / 2}" y="${40 + i * 78}" width="${w}" height="62" rx="8" fill="${f}"/><text x="320" y="${68 + i * 78}" text-anchor="middle" font-size="16" fill="#fff" font-weight="600">${n}</text><text x="320" y="${90 + i * 78}" text-anchor="middle" font-size="13" fill="#fff">${c} · ${b}</text>`).join("")}
<text x="560" y="70" font-size="13" fill="#555">更快</text><text x="560" y="330" font-size="13" fill="#555">更大</text>
<line x1="575" y1="80" x2="575" y2="310" stroke="#888" stroke-width="1.5" marker-end="url(#a)"/>
<defs><marker id="a" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8z" fill="#888"/></marker></defs>`);

const tiling = svg(640, 360, `
<rect width="640" height="360" fill="#fbfaf7"/>
<g stroke="#9aa7b0" fill="none">${Array.from({ length: 6 }, (_, i) => `<line x1="40" x2="280" y1="${40 + i * 48}" y2="${40 + i * 48}"/><line y1="40" y2="280" x1="${40 + i * 48}" x2="${40 + i * 48}"/>`).join("")}</g>
<rect x="88" y="88" width="96" height="96" fill="#2d5f7f" fill-opacity=".85"/><text x="160" y="310" text-anchor="middle" font-size="14" fill="#333">Q 分块 (B_r × d)</text>
<g stroke="#9aa7b0" fill="none">${Array.from({ length: 6 }, (_, i) => `<line x1="360" x2="600" y1="${40 + i * 48}" y2="${40 + i * 48}"/><line y1="40" y2="280" x1="${360 + i * 48}" x2="${360 + i * 48}"/>`).join("")}</g>
<rect x="360" y="88" width="240" height="48" fill="#c47f17" fill-opacity=".75"/><text x="480" y="310" text-anchor="middle" font-size="14" fill="#333">K/V 流式块 (B_c × d)</text>
<path d="M190 136 C 260 120, 300 112, 352 112" stroke="#333" stroke-width="2" fill="none" marker-end="url(#b)"/>
<defs><marker id="b" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8z" fill="#333"/></marker></defs>
<text x="320" y="345" text-anchor="middle" font-size="13" fill="#555">每个 Q 块驻留 SRAM，K/V 块依次流入，部分和在片上累积</text>`);

const validation = svg(640, 360, `
<rect width="640" height="360" fill="#fbfaf7"/>
<line x1="70" y1="300" x2="600" y2="300" stroke="#333"/><line x1="70" y1="40" x2="70" y2="300" stroke="#333"/>
<line x1="70" y1="300" x2="600" y2="40" stroke="#c9c6bd" stroke-dasharray="6 6"/>
${[[120, 270], [170, 236], [230, 214], [300, 170], [360, 150], [420, 112], [480, 98], [540, 70], [260, 230], [400, 160]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="7" fill="#2d5f7f" fill-opacity=".8"/>`).join("")}
<text x="335" y="335" text-anchor="middle" font-size="14" fill="#333">模型预测延迟 (μs)</text><text x="28" y="170" font-size="14" fill="#333" transform="rotate(-90 28 170)" text-anchor="middle">实测延迟 (μs)</text>
<text x="420" y="60" font-size="13" fill="#555">y = x</text>`);

export const figures: Record<string, FigureRef> = {
  "fig-1": { id: "fig-1", label: "图 1", unit: 2, src: roofline, caption: "图 1：Roofline 模型。斜线为带宽上限 β·I，水平线为峰值算力 π，两者交点为脊点。" },
  "fig-2": { id: "fig-2", label: "图 2", unit: 3, src: hierarchy, caption: "图 2：典型加速器的片上/片外存储层次（数值取自公开规格，量级示意）。" },
  "fig-3": { id: "fig-3", label: "图 3", unit: 6, src: tiling, caption: "图 3：分块注意力的数据驻留方式。Q 块固定在 SRAM，K/V 块流式进入。" },
  "fig-4": { id: "fig-4", label: "图 4", unit: 8, src: validation, caption: "图 4：分析模型预测延迟与实测延迟的对比，虚线为理想一致。" },
};

export const units: Unit[] = [
  { index: 1, section: "1 引言", title: "为什么推理首先是访存问题", figures: [], body: `大模型推理被普遍描述为“算力密集”，但在实际部署中，决定延迟的往往不是乘加单元的数量，而是数据能否及时到达这些单元。以解码阶段为例，每生成一个 token，模型需要把全部权重从高带宽存储（HBM）读入片上，再与一个很小的激活向量相乘。乘加次数与读入字节数之比极低，于是计算单元大部分时间都在等待数据。

本文从性能建模的角度讨论这一现象：先用 Roofline 模型给出可达性能的上界，再沿存储层次分析注意力算子的数据流，最后讨论编译器如何通过算子融合与分块（tiling）把访存压力转移到更快的片上存储。我们关心的不是某一块芯片的绝对数字，而是一套可以迁移到不同架构上的推理方法：**先数字节，再数乘加**。` },
  { index: 2, section: "2 Roofline 模型", title: "用两条直线界定可达性能", figures: ["fig-1"], body: `Roofline 模型把一个内核的可达性能写成峰值算力与带宽约束中的较小者：

$$
P = \\min\\left(\\pi,\\; \\beta \\cdot I\\right), \\qquad I = \\frac{\\text{FLOPs}}{\\text{Bytes moved}}
$$

其中 $\\pi$ 是峰值算力（FLOP/s），$\\beta$ 是某一级存储的可持续带宽（Byte/s），$I$ 是算术强度。两条约束的交点称为**脊点** $I^* = \\pi/\\beta$。算术强度低于脊点的内核处于带宽受限区，提升算力不会带来收益；高于脊点的内核处于计算受限区，此时才值得讨论张量核利用率。

见图 1。对于一块峰值约 990 TFLOP/s（BF16 稠密）、HBM 带宽约 3.35 TB/s 的加速器，脊点约为 295 FLOP/Byte。解码阶段的 GEMV 每读入 2 字节权重只做 2 次浮点运算，$I \\approx 1$，距离脊点两个数量级——这就是为什么批大小和 KV 缓存布局对吞吐的影响远大于内核本身的指令调度。` },
  { index: 3, section: "3 存储层次", title: "每一级存储都有自己的屋顶", figures: ["fig-2"], body: `Roofline 中的 $\\beta$ 并不唯一。数据从 HBM 进入 L2，再进入共享内存和寄存器，每一级都有不同的容量和带宽，因此一个内核会同时面对多条“屋顶”。分层 Roofline 的做法是对每一级分别统计搬运字节，取最紧的那条约束。

| 层级 | 典型容量 | 可持续带宽 | 访问延迟 | 建模时的角色 |
| --- | --- | --- | --- | --- |
| 寄存器 | ≈ 256 KB / SM | ~100 TB/s | 1 周期 | 复用的终点 |
| 共享内存 / SRAM | 228 KB / SM | ~30 TB/s | ~30 周期 | 分块驻留区 |
| L2 缓存 | 50 MB | ~7 TB/s | ~200 周期 | 跨 SM 复用 |
| HBM3 | 80 GB | 3.35 TB/s | ~600 周期 | 权重与 KV 缓存 |

图 2 给出了这些层级的相对关系。建模时最常见的错误，是只用 HBM 带宽估算，而忽略了中间层级在融合内核中的瓶颈：当分块尺寸选得过大，共享内存放不下，数据被迫回写 L2，带宽骤降为原来的四分之一。` },
  { index: 4, section: "4 注意力的访存分析", title: "注意力算子到底搬运了多少字节", figures: [], body: `考虑序列长度 $N$、头维度 $d$ 的单头注意力。朴素实现按三步执行：计算 $S = QK^\\top$，对 $S$ 做 softmax 得到 $P$，再计算 $O = PV$。如果每一步都是独立内核，中间矩阵 $S$ 与 $P$ 都要写回 HBM 再读出，搬运量为

$$
\\text{Bytes}_{\\text{naive}} \\approx \\underbrace{4Nd}_{Q,K,V,O} + \\underbrace{4N^2}_{S,P\\ \\text{读写}} \\quad (\\text{以元素计})
$$

当 $N \\gg d$ 时，$N^2$ 项占主导。以 $N = 8192$、$d = 128$ 为例，$4N^2$ 约为 $2.7 \\times 10^8$ 个元素，而 $4Nd$ 只有 $4.2 \\times 10^6$，前者是后者的 64 倍。换言之，朴素注意力的绝大部分时间花在搬运一个只为了下一步而存在的中间矩阵上。这个矩阵既不是模型参数，也不是最终输出，它只是把计算拆成三个内核的副作用。

进一步看浮点运算量：两次矩阵乘共约 $4N^2 d$ 次运算，softmax 约 $5N^2$ 次。于是朴素实现的算术强度约为 $I \\approx \\frac{4N^2 d}{2 \\cdot 4N^2} = d/2$（BF16 每元素 2 字节），对 $d = 128$ 得到 $I \\approx 64$，仍低于前述 295 的脊点。也就是说，即使在预填充阶段，朴素注意力也处于带宽受限区；而在解码阶段，每步只有一个查询向量，$S$ 退化为长度 $N$ 的向量，算术强度进一步跌到个位数。

这个分析给出两条直接的优化方向。第一，消除 $S$ 和 $P$ 的片外读写，让它们只存在于片上——这正是算子融合要做的事。第二，在解码阶段，真正的大头是 KV 缓存的读取，$2Nd$ 个元素每步都要从 HBM 读一次；这部分无法靠融合消除，只能靠压缩（量化、分组查询注意力 GQA）或者通过批处理让多个请求共享权重读取来摊薄。很多系统论文把这两类优化混为一谈，但从字节账本看，它们针对的是完全不同的项：前者针对 $N^2$，后者针对 $Nd$ 与批大小的乘积。

还有一个容易被忽视的细节：softmax 需要每一行的最大值和归一化分母，朴素实现因此要对 $S$ 至少扫描两遍。如果把它当作一个独立内核，这两遍扫描都要访问 HBM。后文介绍的在线 softmax 通过维护运行中的最大值与分母，把两遍扫描压缩到一遍，并允许在分块之间增量更新，这是让注意力完全驻留片上的关键数学前提。` },
  { index: 5, section: "5 算子融合与分块", title: "把中间结果留在片上", figures: [], body: `算子融合的本质是改变数据的生命周期：让生产者的输出在被消费之前不离开片上存储。对逐元素算子（如 bias、GELU、残差加）而言，融合几乎没有代价；对归约类算子（softmax、LayerNorm），融合要求分块方式与归约维度兼容。

下面是一段用类张量 DSL 表达的融合调度示意，\`tile\` 决定每个线程块处理的子矩阵，\`cache_read\` 把输入搬入共享内存：

\`\`\`python
# 示意：融合 GEMM + bias + GELU，输出直接写回 HBM
s = Schedule(gemm_bias_gelu)
i, j, k = s.axes()
io, ii = s.split(i, factor=128)      # 行分块：每块 128 行
jo, ji = s.split(j, factor=128)      # 列分块
ko, ki = s.split(k, factor=64)       # 归约维分块
s.reorder(io, jo, ko, ii, ji, ki)
A_sh = s.cache_read(A, "shared", at=ko)
B_sh = s.cache_read(B, "shared", at=ko)
s.fuse_epilogue(bias_add, gelu)      # 尾部逐元素算子在寄存器中完成
s.bind(io, "blockIdx.x"); s.bind(jo, "blockIdx.y")
\`\`\`

分块尺寸受三方面约束：共享内存容量（$2 \\times 128 \\times 64 \\times 2$ 字节 = 32 KB 每级流水）、寄存器压力（累加器 $128 \\times 128$ 的 FP32 分摊到线程），以及流水级数。编译器的任务是在这些约束下最大化每字节的复用次数。` },
  { index: 6, section: "6 分块注意力", title: "在线 softmax 让注意力驻留片上", figures: ["fig-3"], body: `分块注意力把 $Q$ 按行切成大小为 $B_r$ 的块，把 $K, V$ 按行切成大小为 $B_c$ 的块（图 3）。每个 $Q$ 块驻留在 SRAM 中，依次与所有 $K,V$ 块计算，并用在线 softmax 增量更新输出：

$$
m^{(j)} = \\max\\left(m^{(j-1)},\\, \\operatorname{rowmax}(S^{(j)})\\right), \\quad \\ell^{(j)} = e^{m^{(j-1)} - m^{(j)}}\\ell^{(j-1)} + \\operatorname{rowsum}\\left(e^{S^{(j)} - m^{(j)}}\\right)
$$

$$
O^{(j)} = e^{m^{(j-1)} - m^{(j)}} O^{(j-1)} + e^{S^{(j)} - m^{(j)}} V^{(j)}
$$

最后再除以 $\\ell$ 完成归一化。这样 $S$ 与 $P$ 只以 $B_r \\times B_c$ 的小块形式存在于片上，HBM 搬运量降为 $O(N d \\cdot N d / M)$，其中 $M$ 是 SRAM 容量。对典型参数，这意味着 HBM 读写减少一个数量级，注意力从带宽受限进入计算受限区。` },
  { index: 7, section: "7 编译器视角", title: "调度空间与代价模型", figures: [], body: `从编译器的角度看，前面讨论的每一种优化都是调度空间中的一个点：融合边界、分块尺寸、循环顺序、流水级数、线程绑定。一个中等规模的融合注意力内核，其合法调度数量可以轻易超过 $10^6$。穷举实测不可行，因此需要代价模型对候选调度排序，只把排名靠前的少数候选送去真机测量。

代价模型大致分为三类。**分析模型**直接套用本文的字节与运算计数，加上对各级存储带宽和流水重叠的假设，优点是可解释、无需训练数据，缺点是对缓存冲突、bank conflict 和指令发射瓶颈不敏感。**学习模型**从历史测量中拟合延迟，能捕捉复杂的硬件效应，但迁移到新架构时需要重新采集数据，且出错时难以诊断。**混合模型**用分析特征作为学习模型的输入，在两者之间折中，是目前多数自动调优框架的选择。

对于做架构探索的人，分析模型的价值常被低估。在芯片尚未流片时没有测量数据可学，分析模型是唯一可用的工具；它还能回答“如果把 SRAM 翻倍会怎样”这类反事实问题，而学习模型只能在见过的分布内插值。一个实用的做法是：先用分析模型在大空间中剪枝，把候选缩小到百量级，再用少量实测校准模型中最不确定的参数（通常是有效带宽和流水重叠系数），最后迭代。

这一流程对代价模型的要求不是绝对准确，而是**排序正确**。只要模型能把好调度排在坏调度前面，即使绝对误差达到 30%，调优结果依然可靠。因此验证代价模型时，Kendall τ 或 top-k 命中率往往比平均绝对误差更有意义。` },
  { index: 8, section: "8 模型验证", title: "预测与实测的对比", figures: ["fig-4"], body: `我们在一组融合注意力与 GEMM 内核上验证分析模型，覆盖不同的序列长度与分块尺寸。结果见下表和图 4。

| 内核 | 配置 | 预测 (μs) | 实测 (μs) | 误差 |
| --- | --- | ---: | ---: | ---: |
| 朴素注意力 | N=4096, d=128 | 412 | 455 | −9.5% |
| 分块注意力 | N=4096, B=128 | 96 | 108 | −11.1% |
| 分块注意力 | N=8192, B=128 | 371 | 402 | −7.7% |
| 融合 GEMM+GELU | 4096³ | 151 | 163 | −7.4% |
| 解码 GEMV | batch=1 | 38 | 51 | −25.5% |

除解码 GEMV 外，误差均在 12% 以内且符号一致（系统性低估），说明主要偏差来自未建模的固定开销，而非字节计数本身。解码场景误差偏大，原因是内核启动与同步开销在 40 μs 量级的内核中占比显著。` },
  { index: 9, section: "9 结论", title: "先数字节，再数乘加", figures: [], body: `本文用 Roofline 与分层存储模型分析了 Transformer 推理中的主要算子，说明了朴素注意力为何处于带宽受限区，以及分块与在线 softmax 如何把它推入计算受限区。对编译器与架构设计而言，最重要的结论是：性能建模首先是一份**字节账本**。只要能准确数出每一级存储搬运了多少字节，大部分优化方向在动手实现之前就已经清晰可见。` },
];

export const initialFrontier = 3;

export const initialMessages: Message[] = [
  { id: "m-1", role: "user", unit: 2, quote: "脊点约为 295 FLOP/Byte", text: "这个 295 是怎么算出来的？如果用 FP8 会变吗？" },
  { id: "m-2", role: "assistant", unit: 2, text: `脊点就是两条屋顶的交点：

$$
I^* = \\frac{\\pi}{\\beta} = \\frac{990 \\times 10^{12}}{3.35 \\times 10^{12}} \\approx 295\\ \\text{FLOP/Byte}
$$

换成 FP8 时，峰值算力大约翻倍（约 1980 TFLOP/s），而 HBM 带宽不变，所以脊点也翻倍到约 **590**。同时每个元素只占 1 字节，同一内核的算术强度也翻倍。两者相抵，GEMV 依然深陷带宽受限区——FP8 对解码的收益主要来自**少搬一半字节**，而不是更高的峰值算力。` },
];

type Reply = { text: string; figure?: string };
const replies: Record<number, Reply> = {
  2: { figure: "fig-1", text: `可以把图 1 当作一张“预算表”来读：横轴是每搬一个字节能做多少运算，纵轴是能拿到的性能。

1. 先算内核的算术强度 $I$，在横轴上找到位置；
2. 如果 $I < I^*$，向上碰到的是斜线，性能 $= \\beta I$；
3. 否则碰到水平线，性能 $= \\pi$。

解码阶段的点几乎贴着左下角，这解释了为什么增大 batch（让多条请求共享同一次权重读取）比优化内核指令更有效。` },
  3: { text: `表中最值得注意的是 **SRAM 与 HBM 之间约 10 倍的带宽差**。分块设计的目标，就是让每个从 HBM 读入的字节在 SRAM 中被复用足够多次。

一个粗略的判据：若分块后每字节复用次数为 $r$，则有效算术强度约为 $I_{\\text{eff}} = r \\cdot I_{\\text{tile}}$。只要 $I_{\\text{eff}}$ 超过 HBM 脊点，瓶颈就转移到片上层级，此时应改用 SRAM 那条屋顶检查。` },
  4: { text: `这一段的核心是区分两类字节：

- **$4N^2$ 项**：中间矩阵 $S, P$ 的往返。融合与分块能把它几乎消掉。
- **$2Nd$ 项**：解码时每步都要读的 KV 缓存。只能靠 GQA、量化或批处理摊薄。

把 $N=8192, d=128$ 代入，前者约是后者的 64 倍——所以预填充阶段收益来自融合，解码阶段收益来自 KV 压缩。很多论文的加速比来自哪一项，用这张账本一查便知。` },
  6: { figure: "fig-3", text: `在线 softmax 的关键在于**缩放因子** $e^{m^{(j-1)} - m^{(j)}}$：当新块出现更大的最大值时，之前累积的 $O$ 和 $\\ell$ 需要按比例缩小，才能与新块对齐。

这样每个 $K,V$ 块只读一次，$S$ 只在片上以 $B_r \\times B_c$ 的小块出现。分块尺寸一般取能让 $Q$ 块、一个 $K/V$ 块和累加器同时放进 SRAM 的最大值。` },
};

export function demoReply(unit: number, question: string): Reply {
  return replies[unit] ?? { text: `（演示回复，未调用模型）针对第 ${unit} 段的提问“${question.slice(0, 24)}”，一个可靠的分析顺序是：

1. 先列出该算子涉及的张量及其形状，统计每一级存储的读写字节；
2. 再统计浮点运算量，计算算术强度 $I = \\text{FLOPs} / \\text{Bytes}$；
3. 与对应层级的脊点 $I^* = \\pi / \\beta$ 比较，判断瓶颈位置。

如果需要，我可以把这段的具体数字代入，给出一张逐级的字节账本。` };
}