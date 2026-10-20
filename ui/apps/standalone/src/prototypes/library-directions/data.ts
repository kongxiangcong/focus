import type { BlogArtifactName, BlogArtifactStatus, LibrarySource, LibraryTopic } from "@focus/reader-contracts";

/* Synthetic library. Field names follow @focus/reader-contracts so the prototype
   only shows what the Host already projects; prototype-only fields are marked. */

export type BlogDemo = {
  generated: boolean;
  running?: boolean;
  artifacts: Record<BlogArtifactName, BlogArtifactStatus>;
  valueAnalysisReason?: string;
};

export type DemoSource = LibrarySource & {
  blog: BlogDemo;
  /** Mirrors ReadingWindow.preparations[sourceId] for the running/failed cases. */
  preparing?: { completed: number; total: number; failed?: string };
};

export type DemoIngestion = {
  itemId: string;
  fileName: string;
  backend: "local-mineru" | "remote-mineru" | "html";
  percent: number;
  topicId: string | null;
  failed?: string;
};

const blogNone: BlogDemo = { generated: false, artifacts: { value_analysis: "pending", reading_blog: "pending", html: "pending" } };
const blogDone: BlogDemo = { generated: true, artifacts: { value_analysis: "completed", reading_blog: "completed", html: "completed" } };
const blogNoValue: BlogDemo = { generated: true, artifacts: { value_analysis: "not_applicable", reading_blog: "completed", html: "completed" }, valueAnalysisReason: "来源不涉及硬件架构、DSE、编译器、仿真器或性能建模。" };

function source(partial: Partial<DemoSource> & Pick<DemoSource, "sourceId" | "title" | "kind">): DemoSource {
  return {
    displayTitle: null, shortName: partial.sourceId.replace(/-(paper|article)$/, ""), format: partial.kind === "paper" ? "PDF" : "HTML",
    publishedAt: null, venue: null, parseStatus: "ready", error: null,
    progress: { completed: 0, total: 0, planId: null, chunkId: null }, noteCount: 0, topicIds: [], blog: blogNone,
    ...partial,
  };
}

export const initialTopics: LibraryTopic[] = [
  { topicId: "accelerator", title: "加速器架构", sourceIds: ["eyeriss-paper", "timeloop-paper", "accelforge-paper", "flashattention-paper", "maestro-paper"] },
  { topicId: "compiler-dse", title: "编译器与 DSE", sourceIds: ["timeloop-paper", "tvm-paper", "ansor-paper", "mlir-paper"] },
  { topicId: "zh-blogs", title: "中文技术长文", sourceIds: ["kv-cache-article", "moe-article", "hbm-article"] },
];

export const initialSources: DemoSource[] = [
  source({ sourceId: "flashattention-paper", kind: "paper", title: "FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness", displayTitle: "FlashAttention",
    venue: "NeurIPS", publishedAt: "2022", progress: { completed: 12, total: 40, planId: "plan-001", chunkId: "c013" }, readingStatus: "reading", noteCount: 4,
    topicIds: ["accelerator"], blog: blogDone }),
  source({ sourceId: "eyeriss-paper", kind: "paper", title: "Eyeriss: A Spatial Architecture for Energy-Efficient Dataflow for Convolutional Neural Networks", displayTitle: "Eyeriss 空间架构与行固定数据流",
    venue: "ISCA", publishedAt: "2016", progress: { completed: 31, total: 31, planId: "plan-001", chunkId: null }, readingStatus: "completed", noteCount: 9,
    topicIds: ["accelerator"], blog: blogDone }),
  source({ sourceId: "timeloop-paper", kind: "paper", title: "Timeloop: A Systematic Approach to DNN Accelerator Evaluation", displayTitle: "Timeloop",
    venue: "ISPASS", publishedAt: "2019", progress: { completed: 5, total: 26, planId: "plan-002", chunkId: "c006" }, readingStatus: "reading", noteCount: 2,
    topicIds: ["accelerator", "compiler-dse"], blog: { generated: true, artifacts: { value_analysis: "completed", reading_blog: "failed", html: "pending" } } }),
  source({ sourceId: "accelforge-paper", kind: "paper", title: "AccelForge: Generating Accelerator Mappings with Learned Cost Models and Constraint Programming", displayTitle: "AccelForge",
    venue: "MICRO", publishedAt: "2025", progress: { completed: 0, total: 0, planId: null, chunkId: null }, readingStatus: "unplanned",
    topicIds: ["accelerator"], blog: { generated: true, running: true, artifacts: { value_analysis: "completed", reading_blog: "generating", html: "pending" } },
    preparing: { completed: 14, total: 33 } }),
  source({ sourceId: "maestro-paper", kind: "paper", title: "MAESTRO: A Data-Centric Approach to Understand Reuse, Performance, and Hardware Cost of DNN Mappings", displayTitle: "MAESTRO",
    venue: "IEEE Micro", publishedAt: "2020", progress: { completed: 0, total: 22, planId: "plan-001", chunkId: "c001" }, readingStatus: "ready",
    topicIds: ["accelerator"], blog: blogNone }),
  source({ sourceId: "tvm-paper", kind: "paper", title: "TVM: An Automated End-to-End Optimizing Compiler for Deep Learning", displayTitle: "TVM",
    venue: "OSDI", publishedAt: "2018", progress: { completed: 0, total: 0, planId: null, chunkId: null }, readingStatus: "unplanned",
    topicIds: ["compiler-dse"], blog: blogNone, preparing: { completed: 3, total: 18, failed: "翻译第 4 段时后端连接中断" } }),
  source({ sourceId: "ansor-paper", kind: "paper", title: "Ansor: Generating High-Performance Tensor Programs for Deep Learning", displayTitle: "Ansor",
    venue: "OSDI", publishedAt: "2020", progress: { completed: 0, total: 0, planId: null, chunkId: null }, readingStatus: "unplanned",
    topicIds: ["compiler-dse"], blog: blogNone }),
  source({ sourceId: "mlir-paper", kind: "paper", title: "MLIR: Scaling Compiler Infrastructure for Domain Specific Computation", displayTitle: "MLIR",
    venue: "CGO", publishedAt: "2021", parseStatus: "invalid", error: "Parser Bundle 校验失败：content.md 引用了 3 张不存在的图片",
    topicIds: ["compiler-dse"] }),
  source({ sourceId: "kv-cache-article", kind: "article", title: "大模型推理中的 KV Cache：从原理到 PagedAttention", format: "HTML",
    publishedAt: "2024-03-12", venue: "知乎", progress: { completed: 18, total: 18, planId: "plan-001", chunkId: null }, readingStatus: "completed", noteCount: 3,
    topicIds: ["zh-blogs"], blog: blogNoValue }),
  source({ sourceId: "moe-article", kind: "article", title: "混合专家模型（MoE）的路由、负载均衡与通信开销", format: "HTML",
    publishedAt: "2024-08-02", venue: "微信公众号", progress: { completed: 2, total: 15, planId: "plan-001", chunkId: "c003" }, readingStatus: "reading", noteCount: 1,
    topicIds: ["zh-blogs"], blog: blogNone }),
  source({ sourceId: "hbm-article", kind: "article", title: "HBM 带宽为什么总是不够用", format: "Markdown",
    publishedAt: "2025-01-20", progress: { completed: 0, total: 9, planId: "plan-001", chunkId: "c001" }, readingStatus: "ready",
    topicIds: ["zh-blogs"], blog: blogNoValue }),
  source({ sourceId: "roofline-paper", kind: "paper", title: "Roofline: An Insightful Visual Performance Model for Multicore Architectures", displayTitle: "Roofline 模型",
    venue: "CACM", publishedAt: "2009", progress: { completed: 0, total: 12, planId: "plan-001", chunkId: "c001" }, readingStatus: "ready", noteCount: 0, blog: blogDone }),
  source({ sourceId: "systolic-article", kind: "article", title: "一文看懂脉动阵列（Systolic Array）", format: "HTML",
    publishedAt: "2023-11-05", venue: "博客园", progress: { completed: 0, total: 0, planId: null, chunkId: null }, readingStatus: "unplanned", blog: blogNone }),
];

/** Subset of ReadingWindow: `source.sourceId` and `(navigationCurrent ?? current)` index/total/sectionPath. */
export const currentReading = { sourceId: "flashattention-paper", index: 13, total: 40, sectionPath: ["3 方法", "3.1 分块与重计算"] as readonly string[] };

export const initialIngestions: DemoIngestion[] = [
  { itemId: "ing-1", fileName: "Sparse-Tensor-Core-ISCA24.pdf", backend: "local-mineru", percent: 42, topicId: "accelerator" },
  { itemId: "ing-2", fileName: "chiplet-interconnect.html", backend: "html", percent: 0, topicId: null, failed: "SingleFile HTML 缺少正文节点，请重新保存完整页面" },
];
