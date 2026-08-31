import { type ComponentType } from "react";
import type { ReaderHost } from "@focus/reader-contracts";
import { Mist } from "./variants/Mist";
import { Folio } from "./variants/Folio";
import { Nocturne } from "./variants/Nocturne";
import { Current } from "./variants/Current";
import { Duet } from "./variants/Duet";

export type Direction = "mist" | "folio" | "nocturne" | "current" | "duet";
export interface VariantProps { host: ReaderHost }
export const directions: { name: string; english: string; axis: string; Component: ComponentType<VariantProps> }[] = [
  { name: "雾光", english: "SOFT FOCUS", axis: "漂浮玻璃 · 柔和聚焦", Component: Mist },
  { name: "留白", english: "THE QUIET PAGE", axis: "编辑式排版 · 纸上旁注", Component: Folio },
  { name: "极夜", english: "AFTER HOURS", axis: "暗色光场 · 星尘剧场", Component: Nocturne },
  { name: "流动", english: "A THREAD OF THOUGHT", axis: "会话时间轴 · 连续思路", Component: Current },
  { name: "共读", english: "SIDE BY SIDE", axis: "双页对照 · 原文与讲解", Component: Duet },
];
