import { useCallback, useEffect, useRef, useState } from "react";
import { demoReply, initialFrontier, initialMessages, units, type Message } from "./data";

export type Entry = { kind: "unit"; index: number } | { kind: "msg"; id: string };
export type Note = { id: string; unit: number; text: string };

function initialTimeline(): Entry[] {
  const list: Entry[] = [];
  for (let i = 1; i <= initialFrontier; i++) {
    list.push({ kind: "unit", index: i });
    for (const m of initialMessages) if (m.unit === i) list.push({ kind: "msg", id: m.id });
  }
  return list;
}

// Math stays atomic so a half-streamed formula never renders as raw TeX.
function atoms(text: string): string[] {
  return text.match(/\$\$[\s\S]+?\$\$|\$[^$\n]+\$|[\s\S]/g) ?? [];
}

export function useDemo(k: number) {
  const [frontier, setFrontier] = useState(initialFrontier);
  const [timeline, setTimeline] = useState<Entry[]>(initialTimeline);
  const [messages, setMessages] = useState<Record<string, Message>>(() => Object.fromEntries(initialMessages.map(m => [m.id, m])));
  const [pending, setPending] = useState(false);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [notes, setNotes] = useState<Note[]>([{ id: "n-1", unit: 2, text: "解码 GEMV 的 I≈1，距脊点两个数量级：先优化 batch 与 KV 布局，而不是内核指令。" }]);
  const timer = useRef<number | null>(null);
  const delay = useRef<number | null>(null);
  const kRef = useRef(k); kRef.current = k;
  const seq = useRef(10);

  const streamRef = useRef<string | null>(null); streamRef.current = streamingId;
  const stop = useCallback(() => {
    if (timer.current) window.clearInterval(timer.current);
    if (delay.current) window.clearTimeout(delay.current);
    timer.current = null; delay.current = null;
    const id = streamRef.current;
    if (!id) return;
    setMessages(old => ({ ...old, [id]: { ...old[id], streaming: false, text: `${old[id].text}${old[id].text ? "\n\n" : ""}*（已停止生成）*` } }));
    setStreamingId(null);
  }, []);
  useEffect(() => () => { if (timer.current) window.clearInterval(timer.current); }, []);

  const continueReading = useCallback(() => {
    if (pending || streamingId) return;
    if (frontier >= units.length) { setCompleted(true); return; }
    setPending(true);
    // Stand-in for Host latency; the UI never waits for an animation before calling it.
    window.setTimeout(() => {
      const next = frontier + 1;
      setFrontier(next);
      setTimeline(old => [...old, { kind: "unit", index: next }]);
      setPending(false);
    }, 160);
  }, [frontier, pending, streamingId]);

  const send = useCallback((text: string, unit: number, quote?: string) => {
    if (streamingId || !text.trim()) return null;
    const qid = `m-${++seq.current}`, aid = `m-${++seq.current}`;
    const reply = demoReply(unit, text);
    const parts = atoms(reply.text);
    setMessages(old => ({
      ...old,
      [qid]: { id: qid, role: "user", unit, text, quote, fresh: true },
      [aid]: { id: aid, role: "assistant", unit, text: "", streaming: true, fresh: true },
    }));
    setTimeline(old => [...old, { kind: "msg", id: qid }, { kind: "msg", id: aid }]);
    setStreamingId(aid);
    let at = 0;
    const tick = () => {
      at = Math.min(parts.length, at + 4);
      const done = at >= parts.length;
      setMessages(old => ({ ...old, [aid]: { ...old[aid], text: parts.slice(0, at).join(""), streaming: !done, figure: done ? reply.figure : undefined } }));
      if (done) { if (timer.current) window.clearInterval(timer.current); timer.current = null; setStreamingId(null); }
    };
    delay.current = window.setTimeout(() => { delay.current = null; timer.current = window.setInterval(tick, 38 * kRef.current); }, 420 * kRef.current);
    return qid;
  }, [streamingId]);

  const newSession = useCallback(() => {
    if (streamingId || pending) return;
    setTimeline([]);
  }, [streamingId, pending]);

  const addNote = useCallback((unit: number, text: string) => {
    setNotes(old => [{ id: `n-${++seq.current}`, unit, text }, ...old]);
  }, []);

  return { frontier, timeline, messages, pending, streamingId, completed, notes, continueReading, send, stop, newSession, addNote };
}

export type Demo = ReturnType<typeof useDemo>;