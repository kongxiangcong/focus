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
