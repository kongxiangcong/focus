import { createRoot } from "react-dom/client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { LightfieldDemoHost } from "./demo-host";
import { directions } from "./variants";
import "./picker.css";
import "./reader.css";

function MountedVariant({ selected }: { selected: number }) {
  const [host] = useState(() => new LightfieldDemoHost());
  const Component = directions[selected].Component;
  return <Component host={host} />;
}

function Prototype() {
  const [selected, setSelected] = useState(() => {
    const value = Number(new URLSearchParams(location.search).get("v"));
    return Number.isInteger(value) && value >= 1 && value <= directions.length ? value - 1 : 0;
  });
  const [replay, setReplay] = useState(0);
  const picker = useRef<HTMLElement>(null);
  const highlight = useRef<HTMLSpanElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);

  useLayoutEffect(() => {
    const move = () => {
      const button = items.current[selected];
      if (button && highlight.current) {
        highlight.current.style.width = `${button.offsetWidth}px`;
        highlight.current.style.transform = `translateX(${button.offsetLeft}px)`;
      }
    };
    move();
    const url = new URL(location.href);
    url.searchParams.set("v", String(selected + 1));
    history.replaceState(null, "", url);
    requestAnimationFrame(() => requestAnimationFrame(() => picker.current?.setAttribute("data-ready", "")));
    window.addEventListener("resize", move);
    return () => window.removeEventListener("resize", move);
  }, [selected]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable || event.metaKey || event.ctrlKey || event.altKey) return;
      const num = Number(event.key);
      if (num >= 1 && num <= directions.length) setSelected(num - 1);
      else if (event.key === "ArrowRight") setSelected((i) => (i + 1) % directions.length);
      else if (event.key === "ArrowLeft") setSelected((i) => (i - 1 + directions.length) % directions.length);
      else if (event.key.toLowerCase() === "r") setReplay((i) => i + 1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return <>
    <MountedVariant key={`${selected}-${replay}`} selected={selected} />
    <nav className="proto-picker" aria-label="Prototype variants" ref={picker}>
      <span className="proto-picker-highlight" aria-hidden="true" ref={highlight} />
      {directions.map((direction, index) => <button
        className="proto-picker-item" key={direction.name}
        ref={(el) => { items.current[index] = el; }}
        data-active={selected === index ? "" : undefined}
        aria-current={selected === index ? "true" : undefined}
        aria-label={direction.name}
        title={`${index + 1} · ${direction.axis}`}
        onClick={() => { if (selected === index) setReplay((i) => i + 1); else setSelected(index); }}
      >{direction.name.split("").join("\u2060")}</button>)}
      <span className="proto-picker-divider" aria-hidden="true" />
      <button className="proto-picker-item proto-picker-replay" aria-label="Replay animation (R)" onClick={() => setReplay((i) => i + 1)}>↻</button>
    </nav>
  </>;
}

const root = createRoot(document.getElementById("root")!);
root.render(<Prototype />);
if (import.meta.hot) import.meta.hot.dispose(() => root.unmount());
