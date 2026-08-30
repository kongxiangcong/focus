import type { ReaderChunk, ReadingWindow } from "@focus/reader-contracts";

export interface ReaderTransitionFrame {
  target: ReadingWindow;
  active: boolean;
}

export interface ReaderFrame {
  window: ReadingWindow;
  history: readonly ReaderChunk[];
  current: ReaderChunk | null;
  enteringCurrent: boolean;
  settlingChunkId: string | null;
}

export function projectReaderFrame(
  settledWindow: ReadingWindow,
  transition: ReaderTransitionFrame | null,
): ReaderFrame {
  if (transition === null) {
    return {
      window: settledWindow,
      history: settledWindow.history,
      current: settledWindow.current,
      enteringCurrent: false,
      settlingChunkId: null,
    };
  }

  return {
    window: transition.target,
    history:
      settledWindow.current === null
        ? transition.target.history
        : [...settledWindow.history, settledWindow.current],
    current: transition.target.current,
    enteringCurrent: !transition.active,
    settlingChunkId: settledWindow.current?.chunkId ?? null,
  };
}
