// Synthetic source and scripted answers. No published research or measured results.
export type Evidence = { id: string; target: string; label: string; quote: string; claim: string; kind?: "object"; status?: "block" | "unavailable" | "historical" };
export type Part = { text: string; evidence?: Evidence; external?: boolean };
export type Answer = { id: string; question: string; parts: Part[]; shown: number; complete: boolean; stopped?: boolean; quote?: string };
export const sections = [
  { id: "abstract", label: "问题与直觉", caption: "为什么计算更快，系统却仍在等待", en: "Abstract" },
  { id: "motivation", label: "瓶颈在哪里", caption: "不同计算阶段争用固定的片上空间", en: "1. Motivation" },
  { id: "method", label: "怎样重新分配", caption: "在阶段边界重分区，而非每周期调整", en: "2. Phase-aware partitioning" },
  { id: "evaluation", label: "实验支持什么", caption: "同等容量下比较访存量与模拟周期", en: "3. Controlled evaluation" },
  { id: "limitations", label: "适用边界", caption: "切换开销、预测误差与未覆盖场景", en: "4. Limitations" },
  { id: "conclusion", label: "回到核心判断", caption: "收益取决于能否减少足够的外部访问", en: "5. Conclusion" },
];
export const guide = "这篇文章讨论一个容易被忽略的问题：加速器算得很快，却可能一直在等数据。作者没有增加片上存储，而是根据计算阶段，把同一块 SRAM 在输入、权重和中间结果之间重新分配。理解它的关键是看清这条链：固定分区为什么浪费空间，重分区怎样减少外部访问，节省的时间又能否覆盖切换开销。接下来可以结合结构图和对照表来读；实验只支持所测试配置下的模拟结果，并不能直接推出所有模型或真实芯片都会更快。";
export const evidence: Record<string, Evidence> = {
  traffic: { id: "traffic", target: "ev-traffic", label: "§1 · 访存瓶颈", quote: "A fixed partition can leave capacity idle in one bank while another bank repeatedly spills data to external memory.", claim: "固定分区可能同时造成闲置和外部访存。" },
  capacity: { id: "capacity", target: "ev-capacity", label: "§2 · 等容量条件", quote: "All configurations use the same total SRAM capacity; only the allocation among data classes changes.", claim: "收益来自容量分配方式，不是增加 SRAM。" },
  boundary: { id: "boundary", target: "ev-boundary", label: "§2 · 切换时机", quote: "Repartitioning occurs only at phase boundaries, after all outstanding transfers have completed.", claim: "重分区在阶段边界发生，并等待未完成传输结束。" },
  table: { id: "table", target: "ev-table", label: "表 1 · 对照结果", quote: "Adaptive: 0.72 normalized external traffic, 0.84 normalized cycles. Fixed balanced: 1.00, 1.00.", claim: "合成示例中，外部访问与模拟周期下降；不是实测芯片数据。", kind: "object" },
  figure: { id: "figure", target: "ev-figure", label: "图 1 · 分区结构", quote: "The same SRAM is allocated differently across compute phases.", claim: "同一块 SRAM 在不同阶段分给不同类型的数据。", kind: "object" },
  limit: { id: "limit", target: "ev-limit", label: "§4 · 结论边界", quote: "These simulator results do not establish end-to-end speedups on a fabricated chip or across untested models.", claim: "模拟结果不能外推为真实芯片或所有模型的端到端加速。" },
  block: { id: "block", target: "ev-block", label: "§4 · 段落定位", quote: "Scheduling and transfer costs must be evaluated together.", claim: "这里只能确认相关段落，不能确定这句转述的逐字位置。", status: "block" },
  missing: { id: "missing", target: "", label: "无法定位原文", quote: "All models run twice as fast.", claim: "文章中没有找到这句断言，不把它标成已验证证据。", status: "unavailable" },
  old: { id: "old", target: "", label: "历史版本引用", quote: "An earlier draft used a different memory budget.", claim: "引用属于旧版本，不能在当前原文中套用高亮。", status: "historical" },
};
export function scriptedAnswer(question: string, scenario = "normal"): Part[] {
  if (scenario === "missing") return [
    { text: "不能据此说“所有模型都快两倍”。这条引用在当前原文中无法定位，所以不会在左侧显示高亮。", evidence: evidence.missing },
    { text: "能够核对的是作者明确保留了结论边界：这些是模拟结果，尚不能证明真实芯片和未测试模型的收益。", evidence: evidence.limit },
  ];
  if (scenario === "historical") return [{ text: "这条回答引用的是旧版本原文。当前文章已更新，旧引文保留供核对，但不会映射到新文章的相似句子上。", evidence: evidence.old }];
  if (scenario === "block") return [{ text: "这里讨论的是调度与数据搬运的共同开销。原文段落可以确认，但这句中文解释没有逐字对应的原句，因此只突出整个段落，并标明“段落定位”。", evidence: evidence.block }];
  if (scenario === "web" || /外部|联网/.test(question)) return [
    { text: "先把文章自身的结论说清楚：它并没有给出真实芯片的端到端加速证据。", evidence: evidence.limit },
    { text: "外部资料可以帮助理解存储层次的背景。这里演示独立的外部来源卡片：它留在对话中，不会把网页内容高亮到这篇文章里。原型没有实际执行联网检索。", external: true },
  ];
  if (scenario === "figure" || /图|表|实验/.test(question)) return [
    { text: "先看图 1：两个阶段使用同一块 SRAM，只是输入、权重和中间结果所占的比例变了。点击引用会突出整张图，而不是伪造一个文字选区。", evidence: evidence.figure },
    { text: "再看表 1。这个合成示例里，自适应方案的外部访问量为基线的 0.72，模拟周期为 0.84。两列不能混为一个“加速比”，表中也没有给出真实芯片功耗。", evidence: evidence.table },
    { text: "因此能讨论的是：在固定容量、这组示例配置下，减少访存与降低模拟周期是否一致。更广泛的收益还需要独立验证。", evidence: evidence.limit },
  ];
  if (/阶段|切换|继续/.test(question)) return [
    { text: "接着看它什么时候切换。作者将重分区放在计算阶段之间，并要求先等未完成的数据传输结束。这样可以减少数据仍在使用时改变分区带来的复杂度。", evidence: evidence.boundary },
    { text: "但安全切换不代表切换免费。应该把等待、搬运和重新配置的时间一起计入，再判断节省的外部访问是否值得。", evidence: evidence.block },
  ];
  return [
    { text: "关键不在于 SRAM 更多了，而在于原来分配得不合适：固定分区可能让一边闲着，另一边却装不下数据，不断访问外部内存。", evidence: evidence.traffic },
    { text: "作者保持 SRAM 总容量不变，只调整不同数据类型的份额。所以这里应比较“如何分”，不能把收益归因为硬件容量增加。", evidence: evidence.capacity },
    { text: "你可以把它想成一个总大小不变、隔板可以移动的工作台。这个类比帮助理解分配方式；实际效果仍需看访存、切换开销与实验范围。作者也明确没有把模拟结果外推到真实芯片和所有模型。", evidence: evidence.limit },
  ];
}
