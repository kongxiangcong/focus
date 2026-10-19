import { createRoot } from "react-dom/client";
import { useEffect, useLayoutEffect, useState } from "react";
import { useDemo } from "./engine";
import { Reader, type Direction } from "./Reader";
import { units } from "./data";
import "./directions.css";

const names: Record<Direction, { title: string; note: string }> = {
  ab: { title: "A+B 选定", note: "A 的卡片与渐进隐退；宽屏且资料关闭时讨论移到卡片右栏并吸附。资料打开时临时退回单栏、正文让位，阅读行保持不动。" },
  a: { title: "A 聚光卡片", note: "段落与它的讨论组成一张卡；正在看的卡浮起，历史卡沉入纸面。" },
  b: { title: "B 原文旁注", note: "原文是主轴，讨论贴在所属段落旁并随长段落吸附；宽屏优先。" },
  c: { title: "C 阅读光标", note: "连续文档，一块面板随视线在段落间滑动；讨论按时间顺序。" },
};

function readParam<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  const v = new URLSearchParams(location.search).get(key) as T | null;
  return v && allowed.includes(v) ? v : fallback;
}

function Prototype() {
  const [direction, setDirection] = useState<Direction>(() => readParam("d", ["ab", "a", "b", "c"] as const, "ab"));
  const [theme, setTheme] = useState<"light" | "dark">(() => readParam("theme", ["light", "dark"] as const, "light"));
  const [reduced, setReduced] = useState(() => matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [slow, setSlow] = useState(false);
  const [autoFigures, setAutoFigures] = useState(false);
  const [yieldText, setYieldText] = useState(true);
  const [fullscreen, setFullscreen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const k = slow ? 4 : 1;
  const demo = useDemo(k);

  useLayoutEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.dataset.motion = reduced ? "reduced" : "full";
    root.style.setProperty("--k", String(k));
    const url = new URL(location.href);
    url.searchParams.set("d", direction); url.searchParams.set("theme", theme);
    history.replaceState(null, "", url);
  }, [direction, theme, reduced, k]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || e.metaKey || e.ctrlKey || e.altKey) return;
      const pick = ({ "1": "ab", "2": "a", "3": "b", "4": "c" } as const)[e.key as "1" | "2" | "3" | "4"];
      if (pick) setDirection(pick);
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);

  function demoAsk() {
    const unit = demo.frontier;
    demo.send("这一段的关键结论是什么？能代入数字算一下吗？", unit, units[unit - 1].title);
  }

  return <>
    <Reader key={direction} direction={direction} demo={demo} settings={{ k, reduced, autoFigures, yieldText }} fullscreen={fullscreen} setFullscreen={setFullscreen} />
    <aside className="fd-console" data-min={minimized} aria-label="原型控制">
      {minimized ? <button className="fd-ghost fd-sm" onClick={() => setMinimized(false)}>原型控制 · {names[direction].title}</button> : <>
        <header>原型控制<span className="fd-demo-tag">模拟数据</span><span className="fd-grow" /><button className="fd-ghost fd-icon fd-sm" aria-label="收起控制台" onClick={() => setMinimized(true)}>–</button></header>
        <div className="fd-seg" role="group" aria-label="设计方向">
          {(Object.keys(names) as Direction[]).map((d, i) => <button key={d} aria-pressed={direction === d} onClick={() => setDirection(d)} title={`快捷键 ${i + 1}`}>
            {names[d].title.split(" ")[0]}<small>{names[d].title.split(" ")[1]}</small></button>)}
        </div>
        <p style={{ marginTop: 0, marginBottom: 6 }}>{names[direction].note}</p>
        <label>深色主题<input type="checkbox" checked={theme === "dark"} onChange={e => setTheme(e.target.checked ? "dark" : "light")} /></label>
        <label>低动态模式<input type="checkbox" checked={reduced} onChange={e => setReduced(e.target.checked)} /></label>
        <label>动效慢放 4×（仅供观察）<input type="checkbox" checked={slow} onChange={e => setSlow(e.target.checked)} /></label>
        <label>新段落自动打开图片（现行为）<input type="checkbox" checked={autoFigures} onChange={e => setAutoFigures(e.target.checked)} /></label>
        <label>资料打开时正文让位<input type="checkbox" checked={yieldText} onChange={e => setYieldText(e.target.checked)} /></label>
        <div className="fd-console-row">
          <button className="fd-secondary" disabled={!!demo.streamingId} onClick={demoAsk}>演示回复</button>
          <button className="fd-secondary" onClick={() => location.reload()}>重置</button>
        </div>
        <p>文章、讨论、图片与回答均为演示内容，未连接后端或模型。快捷键 1–4 切换方向；切换时保留阅读进度与讨论。</p>
      </>}
    </aside>
  </>;
}

const root = createRoot(document.getElementById("root")!);
root.render(<Prototype />);
if (import.meta.hot) import.meta.hot.dispose(() => root.unmount());