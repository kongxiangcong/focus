import type { ReadingWindow } from "@focus/reader-contracts";

export function ArticleStructure({ view, currentChunkId, blocked, onReview, onBody, preview = false }: {
  preview?: boolean; view: ReadingWindow; currentChunkId?: string; blocked: boolean;
  onReview: (chunkId: string) => void; onBody: () => void;
}) {
  const nodes = view.structure ?? [];
  const outline = view.outline ?? [];
  const frontier = view.navigationCurrent ?? view.current;
  const currentNode = outline.find(c => c.chunkId === currentChunkId)?.nodeId;
  function contains(id: string, child: string | undefined): boolean {
    const seen = new Set<string>();
    while (child && !seen.has(child)) {
      if (child === id) return true;
      seen.add(child);
      child = nodes.find(n => n.id === child)?.parentId ?? undefined;
    }
    return false;
  }
  function branch(parentId: string | null) {
    return <ul>{nodes.filter(n => n.parentId === parentId).map(node => {
      const chunks = outline.filter(c => contains(node.id, c.nodeId));
      const done = chunks.filter(c => view.status === "completed" || (view.readingStarted && frontier && c.index < frontier.index)).length;
      const visited = chunks.find(c => view.status === "completed" || (view.readingStarted && frontier && c.index <= frontier.index));
      const selected = contains(node.id, currentNode);
      const inProgress = !!view.readingStarted && !!frontier && chunks.some(c => c.index === frontier.index);
      const children = nodes.some(n => n.parentId === node.id);
      const ownChunk = chunks.find(c => c.nodeId === node.id && (view.status === "completed" || (view.readingStarted && frontier && c.index <= frontier.index)));
      const label = <><strong>{node.title}</strong><small hidden={preview}>{selected ? "当前位置 · " : ""}{done === chunks.length && done > 0 ? "已读完" : `${inProgress ? "阅读中" : done ? "已读" : "未读"} · ${done} / ${chunks.length}`}</small></>;
      return <li key={node.id} data-current={selected}>
        {children ? <details open><summary>{label}</summary>
          {node.description && <p>{node.description}</p>}
          {ownChunk && <button disabled={blocked} onClick={() => onReview(ownChunk.chunkId)}>回看本节</button>}{branch(node.id)}</details>
          : <><div className="article-structure-label">{visited
            ? <button disabled={blocked} onClick={() => onReview(visited.chunkId)}>{label}</button>
            : label}</div>{node.description && <p>{node.description}</p>}</>}
      </li>;
    })}</ul>;
  }
  return <section className="article-structure" aria-label="文章结构">
    <h1 tabIndex={-1}>{view.source.title}</h1>
    <p className="article-structure-kicker">文章结构</p>
    {branch(null)}
    {view.articleOverview?.guide && <section className="article-guide" aria-label="文章导读"><h2>文章导读</h2>
      {view.articleOverview.guide.split(/\n\s*\n/).map((paragraph, i) => <p key={i}>{paragraph}</p>)}
    </section>}
    {view.structureIntro && <button className="focus-primary" disabled={blocked} onClick={onBody}>进入正文</button>}
  </section>;
}
