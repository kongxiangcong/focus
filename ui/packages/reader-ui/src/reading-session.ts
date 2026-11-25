import type { ReadingWindow } from "@focus/reader-contracts";

export interface ReadingSession {
  view: ReadingWindow | null;
  generation: number;
  isCurrent: (generation: number, sourceId?: string) => boolean;
  accept: (view: ReadingWindow, generation: number, allowSourceChange?: boolean) => boolean;
}
