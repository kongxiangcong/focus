import type { ReactNode } from "react";

function Icon({ children }: { children: ReactNode }) {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{children}</svg>;
}

export function PanelLeft() { return <Icon><rect x="2" y="2" width="12" height="12" rx="2"/><path d="M6 2v12"/></Icon>; }
export function Pin() { return <Icon><path d="m10 2 4 4-3 1-2 4-2-2-4 4M7 9 5 7l4-2z"/></Icon>; }
export function Plus() { return <Icon><path d="M8 3v10M3 8h10"/></Icon>; }
export function Expand() { return <Icon><path d="M6 2H2v4m8-4h4v4M2 10v4h4m8-4v4h-4"/></Icon>; }
export function Collapse() { return <Icon><path d="M2 6h4V2m4 0v4h4M6 14v-4H2m12 0h-4v4"/></Icon>; }
export function ArrowRight() { return <Icon><path d="M3 8h10M9 4l4 4-4 4"/></Icon>; }
export function ChevronDown() { return <Icon><path d="m4 6 4 4 4-4"/></Icon>; }
export function ArrowUp() { return <Icon><path d="M8 13V3M4 7l4-4 4 4"/></Icon>; }
export function StopSquare() { return <Icon><rect x="4" y="4" width="8" height="8" rx="1" fill="currentColor" stroke="none"/></Icon>; }

export function Widen() { return <Icon><path d="M2 8h12M5 5 2 8l3 3m6-6 3 3-3 3"/></Icon>; }
export function Narrow() { return <Icon><path d="M1 8h5m-3-3 3 3-3 3m12-3h-5m3-3-3 3 3 3"/></Icon>; }
export function Close() { return <Icon><path d="m4 4 8 8m0-8-8 8"/></Icon>; }
export function ListOutline() { return <Icon><path d="M5 4h9M5 8h9M5 12h6M2 4h.01M2 8h.01M2 12h.01"/></Icon>; }
export function BookOpen() { return <Icon><path d="M2 3.5h4.2A2.3 2.3 0 0 1 8 4.8a2.3 2.3 0 0 1 1.8-1.3H14v9H9.8A2 2 0 0 0 8 13.5a2 2 0 0 0-1.8-1H2z"/></Icon>; }
export function ChatBubble() { return <Icon><path d="M3 4.5A1.5 1.5 0 0 1 4.5 3h7A1.5 1.5 0 0 1 13 4.5v5a1.5 1.5 0 0 1-1.5 1.5H6.5L3.5 13.5V11H4.5A1.5 1.5 0 0 1 3 9.5z"/></Icon>; }
export function DocText() { return <Icon><path d="M4 2.5h5.5L12.5 5.5v8a1 1 0 0 1-1 1h-7a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1z"/><path d="M9.5 2.5v3h3M5.8 8h4.4M5.8 10.6h3.2"/></Icon>; }
