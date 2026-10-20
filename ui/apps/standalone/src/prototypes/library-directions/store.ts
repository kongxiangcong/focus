import { useEffect, useRef, useState } from "react";
import type { LibraryTopic } from "@focus/reader-contracts";
import { initialIngestions, initialSources, initialTopics, type DemoIngestion, type DemoSource } from "./data";

export type Scenario = "normal" | "empty" | "offline";

/* Local stand-in for the Host. Only Topic order and the
   ingestion → Source hand-off change; every other action is a toast. */
export function useLibrary(scenario: Scenario, k: number) {
  const [sources, setSources] = useState<DemoSource[]>(initialSources);
  const [topics, setTopics] = useState<LibraryTopic[]>(initialTopics);
  const [ingestions, setIngestions] = useState<DemoIngestion[]>(initialIngestions);
  const [fresh, setFresh] = useState<ReadonlySet<string>>(new Set());
  const [toast, setToast] = useState<{ id: number; text: string } | null>(null);
  const toastTimer = useRef(0);

  function say(text: string) {
    window.clearTimeout(toastTimer.current);
    setToast({ id: Date.now(), text });
    toastTimer.current = window.setTimeout(() => setToast(null), 2600);
  }

  useEffect(() => {
    if (!ingestions.some(i => !i.failed && i.percent < 100)) return;
    const timer = window.setInterval(() => {
      setIngestions(list => list.map(i => i.failed || i.percent >= 100 ? i : { ...i, percent: Math.min(100, i.percent + 3 + Math.round(Math.random() * 4)) }));
    }, 700 * k);
    return () => window.clearInterval(timer);
  }, [ingestions, k]);

  useEffect(() => {
    const done = ingestions.filter(i => !i.failed && i.percent >= 100);
    if (!done.length) return;
    setIngestions(list => list.filter(i => !done.includes(i)));
    const added: DemoSource[] = done.map(i => {
      const shortName = i.fileName.replace(/\.(pdf|html)$/i, "").toLowerCase();
      const kind = /\.pdf$/i.test(i.fileName) ? "paper" as const : "article" as const;
      return {
        sourceId: `${shortName}-${kind}`, title: i.fileName.replace(/\.(pdf|html)$/i, "").replace(/-/g, " "), kind, format: kind === "paper" ? "PDF" : "HTML",
        parseStatus: "ready", error: null, shortName, readingStatus: "unplanned", noteCount: 0,
        progress: { completed: 0, total: 0, planId: null, chunkId: null }, topicIds: i.topicId ? [i.topicId] : [],
        blog: { generated: true, running: true, artifacts: { reading_blog: "pending", html: "pending" } },
      };
    });
    setSources(list => [...added, ...list]);
    setTopics(list => list.map(t => { const ids = added.filter(a => a.topicIds.includes(t.topicId)).map(a => a.sourceId); return ids.length ? { ...t, sourceIds: [...t.sourceIds, ...ids] } : t; }));
    setFresh(new Set(added.map(a => a.sourceId)));
    say(`${added.map(a => a.title).join("、")} 已入库`);
  }, [ingestions]);

  function reorder(topicId: string, sourceIds: string[]) {
    setTopics(list => list.map(t => t.topicId === topicId ? { ...t, sourceIds } : t));
  }
  function upload(names: string[], topicId: string | null) {
    setIngestions(list => [...names.map((fileName, n) => ({ itemId: `ing-${Date.now()}-${n}`, fileName, topicId,
      backend: /\.pdf$/i.test(fileName) ? "local-mineru" as const : "html" as const, percent: 0 })), ...list]);
  }
  function retryIngestion(itemId: string) {
    setIngestions(list => list.map(i => i.itemId === itemId ? { ...i, failed: undefined, percent: 8 } : i));
  }

  const empty = scenario !== "normal";
  return {
    sources: empty ? [] : sources, topics: empty ? [] : topics, ingestions: empty ? [] : ingestions,
    offline: scenario === "offline", fresh, toast, say, reorder, upload, retryIngestion,
  };
}
export type Library = ReturnType<typeof useLibrary>;
