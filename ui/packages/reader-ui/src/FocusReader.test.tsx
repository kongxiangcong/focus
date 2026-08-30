import "@testing-library/jest-dom/vitest";

import {
  readerSuccess,
  type ReaderHost,
  type ReadingWindow,
} from "@focus/reader-contracts";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FocusReader } from "./FocusReader";

afterEach(cleanup);

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
    fireEvent.click(screen.getByRole("button", { name: "Continue reading" }));

    await waitFor(() => expect(screen.getByText("The second chunk.")).toBeInTheDocument());
    expect(host.continueReading).toHaveBeenCalledWith({
      receipt: {
        sourceId: "fixture-paper",
        planId: "plan-001",
        chunkId: "chunk-001",
      },
    });
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
    fireEvent.change(screen.getByLabelText("Ask about the current chunk"), {
      target: { value: "Why?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Because.")).toBeInTheDocument();
    expect(host.sendMessage).toHaveBeenCalledWith({
      receipt: {
        sourceId: "fixture-paper",
        planId: "plan-001",
        chunkId: "chunk-001",
      },
      content: "Why?",
    });
    expect(host.continueReading).not.toHaveBeenCalled();
  });
});
