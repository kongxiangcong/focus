import { useEffect, useRef, useState } from "react";
import { createReaderId, type ArticleOverview, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";
import { ArticleStructure } from "./ArticleStructure";
import "./article-structure.css";

export function ArticleOverviewPanel({ host, sourceId, title, view, currentChunkId, blocked = false, onReview = () => {}, onBody = () => {} }: {
  host: ReaderHost; sourceId: string; title: string; view?: ReadingWindow; currentChunkId?: string;
  blocked?: boolean; onReview?: (id: string) => void; onBody?: () => void;
}) {
  const [resultData, setData] = useState<ArticleOverview | null>(view?.articleOverview ?? null);
  const data = resultData?.sourceId === sourceId ? resultData : null;
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const scope = useRef(0);
  const locked = useRef(false);
  const retryId = useRef<string | null>(null);
  useEffect(() => {
    const version = ++scope.current;
    let timer: ReturnType<typeof setTimeout>;
    setData(view?.articleOverview ?? null); setError(""); setSending(false); locked.current = false; retryId.current = null;
    async function refresh() {
      try {
        const result = await host.getArticleOverview!(sourceId);
        if (scope.current !== version) return;
        if (result.ok) { setData(result.value); setError(""); } else setError(result.error.message);
      } catch (e) { if (scope.current === version) setError(String(e)); }
      if (scope.current === version) timer = setTimeout(refresh, 1500);
    }
    void refresh();
    return () => { scope.current++; clearTimeout(timer); };
  }, [host, sourceId, view?.navigationCurrent?.planId]);
  async function prepare() {
    if (locked.current || !host.prepareArticleOverview) return;
    locked.current = true; setSending(true); setError("");
    const version = scope.current;
    retryId.current ??= createReaderId();
    try {
      const result = await host.prepareArticleOverview(sourceId, retryId.current);
      if (version !== scope.current) return;
      if (result.ok) { setData(result.value); retryId.current = null; } else setError(result.error.message);
    } catch (e) { if (version === scope.current) setError(String(e)); }
    finally { if (version === scope.current) { locked.current = false; setSending(false); } }
  }
  if (data?.status === "ready") {
    const base: ReadingWindow = view ?? { status: "empty", source: { sourceId, title, topicId: null }, current: null, history: [], conversation: [] };
    const ready = { ...base, structure: data.structure, articleOverview: data,
      outline: base.outline?.map((chunk, i) => ({ ...chunk, nodeId: data.chunkNodes?.[i] })) };
    return <ArticleStructure view={ready} preview={!view} currentChunkId={currentChunkId} blocked={blocked} onReview={onReview} onBody={onBody} />;
  }
  const running = sending || data?.status === "running";
  return <section className="article-structure" aria-label="文章结构"><h1>{title}</h1>
    <p role="status">{!data ? "正在读取文章结构…" : running ? "正在准备中文骨架与导读…" : data.status === "missing" ? "尚未准备文章结构与导读。" : "文章结构与导读尚未就绪。"}</p>
    {(error || data?.error) && <p role="alert">{error || data?.error}</p>}
    {!running && host.prepareArticleOverview && <button disabled={blocked} onClick={() => void prepare()}>{data?.status === "missing" ? "准备文章结构" : "重试准备"}</button>}
  </section>;
}
