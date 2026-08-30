import "@testing-library/jest-dom/vitest";

import {
  readerFailure,
  readerSuccess,
  type ReaderHost,
  type ReadingWindow,
} from "@focus/reader-contracts";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FocusReader } from "./FocusReader";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const firstWindow: ReadingWindow = {
  status: "reading",
  source: { sourceId: "fixture-paper", title: "Fixture Paper", topicId: null },
  current: {
    sourceId: "fixture-paper",
    planId: "plan-001",
    chunkId: "chunk-001",
    index: 1,
    total: 2,
    sectionPath: ["Fixture Paper", "Method"],
    sourceLines: [1, 4],
    sourceMarkdown: "The first chunk.",
    translation: null,
    images: [],
    relevantGlossary: [],
    presentationStatus: "translation-required",
  },
  history: [],
  conversation: [],
};

const secondWindow: ReadingWindow = {
  ...firstWindow,
  current: {
    ...firstWindow.current!,
    chunkId: "chunk-002",
    index: 2,
    sourceMarkdown: "The second chunk.",
  },
  history: [firstWindow.current!],
};

describe("FocusReader", () => {
  it("loads and advances only through the injected ReaderHost", async () => {
    const host: ReaderHost = {
      getReadingWindow: vi.fn().mockResolvedValue(readerSuccess(firstWindow)),
      continueReading: vi.fn().mockResolvedValue(readerSuccess(secondWindow)),
      sendMessage: vi.fn(),
    };

    render(<FocusReader host={host} />);

    expect(await screen.findByText("The first chunk.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "继续阅读" }));

    await waitFor(() => expect(screen.getByText("The second chunk.")).toBeInTheDocument());
    expect(screen.getByText("The first chunk.").closest("article")).toHaveAttribute("data-depth", "1");
    expect(screen.getByText("The first chunk.").closest("article")).toHaveAttribute("data-settling", "true");
    expect(screen.getByText("The second chunk.").closest("article")).toHaveAttribute("data-depth", "0");
    expect(screen.getByRole("button", { name: "正在继续…" })).toHaveAttribute("aria-busy", "true");
    expect(host.continueReading).toHaveBeenCalledWith(
      {
        receipt: {
          sourceId: "fixture-paper",
          planId: "plan-001",
          chunkId: "chunk-001",
        },
      },
      expect.any(AbortSignal),
    );
  });

  it("sends questions without moving the cursor itself", async () => {
    const withConversation: ReadingWindow = {
      ...firstWindow,
      conversation: [
        { messageId: "m-1", chunkId: "chunk-001", role: "user", content: "Why?" },
        { messageId: "m-2", chunkId: "chunk-001", role: "assistant", content: "Because." },
      ],
    };
    const host: ReaderHost = {
      getReadingWindow: vi.fn().mockResolvedValue(readerSuccess(firstWindow)),
      continueReading: vi.fn(),
      sendMessage: vi.fn().mockResolvedValue(readerSuccess(withConversation)),
    };

    render(<FocusReader host={host} />);
    await screen.findByText("The first chunk.");
    expect(screen.queryByLabelText("针对当前 Reading Chunk 提问")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "针对这一段提问…" }));
    fireEvent.change(screen.getByLabelText("针对当前 Reading Chunk 提问"), {
      target: { value: "Why?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("Because.")).toBeInTheDocument();
    expect(host.sendMessage).toHaveBeenCalledWith(
      {
        receipt: {
          sourceId: "fixture-paper",
          planId: "plan-001",
          chunkId: "chunk-001",
        },
        content: "Why?",
      },
      expect.any(AbortSignal),
    );
    expect(host.continueReading).not.toHaveBeenCalled();
  });

  it("derives the three history depths from distance to the cursor", async () => {
    const oldest = { ...firstWindow.current!, chunkId: "chunk-oldest", sourceMarkdown: "Oldest." };
    const middle = { ...firstWindow.current!, chunkId: "chunk-middle", sourceMarkdown: "Middle." };
    const nearest = { ...firstWindow.current!, chunkId: "chunk-nearest", sourceMarkdown: "Nearest." };
    const current = { ...firstWindow.current!, chunkId: "chunk-current", sourceMarkdown: "Current." };
    const host: ReaderHost = {
      getReadingWindow: vi.fn().mockResolvedValue(
        readerSuccess({ ...firstWindow, history: [oldest, middle, nearest], current }),
      ),
      continueReading: vi.fn(),
      sendMessage: vi.fn(),
    };

    render(<FocusReader host={host} />);

    expect((await screen.findByText("Oldest.")).closest("article")).toHaveAttribute("data-depth", "3");
    expect(screen.getByText("Middle.").closest("article")).toHaveAttribute("data-depth", "2");
    expect(screen.getByText("Nearest.").closest("article")).toHaveAttribute("data-depth", "1");
    expect(screen.getByText("Current.").closest("article")).toHaveAttribute("data-depth", "0");
  });

  it("commits Continue Reading immediately when reduced motion is requested", async () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
    const host: ReaderHost = {
      getReadingWindow: vi.fn().mockResolvedValue(readerSuccess(firstWindow)),
      continueReading: vi.fn().mockResolvedValue(readerSuccess(secondWindow)),
      sendMessage: vi.fn(),
    };

    render(<FocusReader host={host} />);
    await screen.findByText("The first chunk.");
    fireEvent.click(screen.getByRole("button", { name: "继续阅读" }));

    expect(await screen.findByText("The second chunk.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "继续阅读" })).toBeEnabled());
    expect(screen.getByText("The first chunk.").closest("article")).not.toHaveAttribute("data-settling");
  });

  it("locks duplicate Continue Reading operations", async () => {
    let resolveContinue: ((value: ReturnType<typeof readerSuccess<ReadingWindow>>) => void) | undefined;
    const pending = new Promise<ReturnType<typeof readerSuccess<ReadingWindow>>>((resolve) => {
      resolveContinue = resolve;
    });
    const host: ReaderHost = {
      getReadingWindow: vi.fn().mockResolvedValue(readerSuccess(firstWindow)),
      continueReading: vi.fn().mockReturnValue(pending),
      sendMessage: vi.fn(),
    };

    render(<FocusReader host={host} />);
    await screen.findByText("The first chunk.");
    const button = screen.getByRole("button", { name: "继续阅读" });
    fireEvent.click(button);
    fireEvent.click(button);

    expect(host.continueReading).toHaveBeenCalledTimes(1);
    resolveContinue?.(readerSuccess(secondWindow));
    expect(await screen.findByText("The second chunk.")).toBeInTheDocument();
  });

  it("reloads the authoritative window after a stale cursor receipt", async () => {
    const host: ReaderHost = {
      getReadingWindow: vi
        .fn()
        .mockResolvedValueOnce(readerSuccess(firstWindow))
        .mockResolvedValueOnce(readerSuccess(secondWindow)),
      continueReading: vi.fn().mockResolvedValue(
        readerFailure("cursor-changed", "The Reading Cursor changed."),
      ),
      sendMessage: vi.fn(),
    };

    render(<FocusReader host={host} />);
    await screen.findByText("The first chunk.");
    fireEvent.click(screen.getByRole("button", { name: "继续阅读" }));

    expect(await screen.findByText("The second chunk.")).toBeInTheDocument();
    expect(host.getReadingWindow).toHaveBeenCalledTimes(2);
  });

  it("recovers from an initial host error through the single retry path", async () => {
    const host: ReaderHost = {
      getReadingWindow: vi
        .fn()
        .mockResolvedValueOnce(readerFailure("unavailable", "阅读宿主暂时不可用。", true))
        .mockResolvedValueOnce(readerSuccess(firstWindow)),
      continueReading: vi.fn(),
      sendMessage: vi.fn(),
    };

    render(<FocusReader host={host} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("阅读宿主暂时不可用。");
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("The first chunk.")).toBeInTheDocument();
  });

  it("keeps complete history visible when the host reports completion", async () => {
    const completed: ReadingWindow = {
      ...firstWindow,
      status: "completed",
      current: null,
      history: [firstWindow.current!],
      conversation: [],
    };
    const host: ReaderHost = {
      getReadingWindow: vi.fn().mockResolvedValue(readerSuccess(completed)),
      continueReading: vi.fn(),
      sendMessage: vi.fn(),
    };

    render(<FocusReader host={host} />);

    expect(await screen.findByRole("heading", { name: "阅读完成" })).toBeInTheDocument();
    expect(screen.getByText("The first chunk.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "继续阅读" })).toBeDisabled();
  });
});
