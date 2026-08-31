import type { CSSProperties } from "react";

export function Icon({ name, size = 18, style }: { name: string; size?: number; style?: CSSProperties }) {
  const paths: Record<string, React.ReactNode> = {
    arrow: <><path d="M12 4v16m-6-6 6 6 6-6" /></>,
    up: <><path d="M12 20V4m-6 6 6-6 6 6" /></>,
    chevron: <path d="m9 5 7 7-7 7" />,
    book: <><path d="M12 6c-3-3-7-3-9-2v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-2-1-6-1-9 2Z" /><path d="M12 6v14" /></>,
    list: <><path d="M9 6h11M9 12h11M9 18h11" /><path d="M4 6h.01M4 12h.01M4 18h.01" strokeWidth="3" /></>,
    tune: <><path d="M4 7h5m4 0h7M4 17h9m4 0h3" /><circle cx="11" cy="7" r="2" /><circle cx="15" cy="17" r="2" /></>,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" /></>,
    sparkle: <><path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4Z" /></>,
    chat: <path d="M21 11a8 8 0 0 1-8 8H7l-4 3V11a9 9 0 1 1 18 0Z" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    copy: <><rect x="8" y="8" width="12" height="13" rx="2" /><path d="M15 8V3H3v12h5" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    focus: <><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5" /><circle cx="12" cy="12" r="3" /></>,
    bookmark: <path d="M6 3h12v18l-6-4-6 4Z" />,
    return: <><path d="M20 4v9H5m5-5-5 5 5 5" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}>{paths[name] ?? paths.sparkle}</svg>;
}

export function Emblem({ small = false }: { small?: boolean }) {
  return <span className={`lf-emblem ${small ? "lf-emblem-small" : ""}`} aria-hidden="true"><i /><i /><i /><i /></span>;
}
