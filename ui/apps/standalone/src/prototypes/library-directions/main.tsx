import { createRoot } from "react-dom/client";
import { useLayoutEffect, useState } from "react";
import { Library } from "./Library";
import { useLibrary, type Scenario } from "./store";
import "../../../../../packages/reader-ui/src/focus-tokens.css";
import "./library.css";

function readParam<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  const v = new URLSearchParams(location.search).get(key) as T | null;
  return v && allowed.includes(v) ? v : fallback;
}

function Prototype() {
  const [theme, setTheme] = useState<"light" | "dark">(() => readParam("theme", ["light", "dark"] as const, "light"));
  const [density, setDensity] = useState<"compact" | "comfortable">(() => readParam("density", ["compact", "comfortable"] as const, "compact"));
  const [scenario, setScenario] = useState<Scenario>(() => readParam("s", ["normal", "empty", "offline"] as const, "normal"));
  const [reduced, setReduced] = useState(() => matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [slow, setSlow] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const k = slow ? 4 : 1;
  const lib = useLibrary(scenario, k);

  useLayoutEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme; root.dataset.density = density;
    root.dataset.motion = reduced ? "reduced" : "full";
    root.style.setProperty("--k", String(k));
    const url = new URL(location.href);
    url.searchParams.set("theme", theme); url.searchParams.set("density", density); url.searchParams.set("s", scenario);
    history.replaceState(null, "", url);
  }, [theme, density, scenario, reduced, k]);

  return <>
    <Library key={scenario} lib={lib} />
    <aside className="fd-console" data-min={minimized} aria-label="原型控制">
      {minimized ? <button type="button" onClick={() => setMinimized(false)}>原型控制</button> : <>
        <header>知识库 · 方案 A 列表＋详情<span className="fd-tag">模拟数据</span><span className="lb-grow" /><button type="button" aria-label="收起控制台" onClick={() => setMinimized(true)}>–</button></header>
        <label>数据场景<select value={scenario} onChange={e => setScenario(e.target.value as Scenario)}>
          <option value="normal">正常（13 份 · 3 专题）</option><option value="empty">空知识库</option><option value="offline">连接失败</option></select></label>
        <label>深色主题<input type="checkbox" checked={theme === "dark"} onChange={e => setTheme(e.target.checked ? "dark" : "light")} /></label>
        <label>舒适密度<input type="checkbox" checked={density === "comfortable"} onChange={e => setDensity(e.target.checked ? "comfortable" : "compact")} /></label>
        <label>低动态模式<input type="checkbox" checked={reduced} onChange={e => setReduced(e.target.checked)} /></label>
        <label>动效慢放 4×（仅供观察）<input type="checkbox" checked={slow} onChange={e => setSlow(e.target.checked)} /></label>
        <p>↑/↓ 在行间移动，Esc 关闭详情；专题视图中拖动序号或 Alt+↑/↓ 排序。可把任意 PDF/HTML 拖入页面观察入库影子行。未连接后端，操作只显示提示。</p>
      </>}
    </aside>
  </>;
}

const root = createRoot(document.getElementById("root")!);
root.render(<Prototype />);
if (import.meta.hot) import.meta.hot.dispose(() => root.unmount());
