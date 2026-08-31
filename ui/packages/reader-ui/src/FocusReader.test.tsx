import "@testing-library/jest-dom/vitest";

import {
  readerFailure,
  readerSuccess,
  type ReaderHost,
  type ReadingWindow,
} from "@focus/reader-contracts";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
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

    const firstArticle = (await screen.findByText("The first chunk.")).closest(
      "article",
    );
    expect(firstArticle).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "继续阅读" }));

    await waitFor(() =>
      expect(screen.getByText("The second chunk.")).toBeInTheDocument(),
    );
    expect(screen.getByText("The first chunk.").closest("article")).toBe(
      firstArticle,
    );
    expect(firstArticle).toHaveAttribute("data-depth", "1");
    expect(firstArticle).toHaveAttribute("data-settling", "true");
    expect(
      screen.getByText("The second chunk.").closest("article"),
    ).toHaveAttribute("data-depth", "0");
    expect(screen.getByRole("button", { name: "正在继续…" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
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
        {
          messageId: "m-1",
          chunkId: "chunk-001",
          role: "user",
          content: "Why?",
        },
        {
          messageId: "m-2",
          chunkId: "chunk-001",
          role: "assistant",
          content: "Because.",
        },
      ],
    };
    const host: ReaderHost = {
      getReadingWindow: vi.fn().mockResolvedValue(readerSuccess(firstWindow)),
      continueReading: vi.fn(),
      sendMessage: vi.fn().mockResolvedValue(readerSuccess(withConversation)),
    };

    render(<FocusReader host={host} />);
    await screen.findByText("The first chunk.");
    expect(
      screen.getByLabelText("针对当前 Reading Chunk 提问"),
    ).toBeInTheDocument();
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
    const oldest = {
      ...firstWindow.current!,
      chunkId: "chunk-oldest",
      sourceMarkdown: "Oldest.",
    };
    const middle = {
      ...firstWindow.current!,
      chunkId: "chunk-middle",
      sourceMarkdown: "Middle.",
    };
    const nearest = {
      ...firstWindow.current!,
      chunkId: "chunk-nearest",
      sourceMarkdown: "Nearest.",
    };
    const current = {
      ...firstWindow.current!,
      chunkId: "chunk-current",
      sourceMarkdown: "Current.",
    };
    const host: ReaderHost = {
      getReadingWindow: vi
        .fn()
        .mockResolvedValue(
          readerSuccess({
            ...firstWindow,
            history: [oldest, middle, nearest],
            current,
          }),
        ),
      continueReading: vi.fn(),
      sendMessage: vi.fn(),
    };

    render(<FocusReader host={host} />);

    expect(
      (await screen.findByText("Oldest.")).closest("article"),
    ).toHaveAttribute("data-depth", "3");
    expect(screen.getByText("Middle.").closest("article")).toHaveAttribute(
      "data-depth",
      "2",
    );
    expect(screen.getByText("Nearest.").closest("article")).toHaveAttribute(
      "data-depth",
      "1",
    );
    expect(screen.getByText("Current.").closest("article")).toHaveAttribute(
      "data-depth",
      "0",
    );
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
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "继续阅读" })).toBeEnabled(),
    );
    expect(
      screen.getByText("The first chunk.").closest("article"),
    ).not.toHaveAttribute("data-settling");
  });

  it("locks duplicate Continue Reading operations", async () => {
    let resolveContinue:
      | ((value: ReturnType<typeof readerSuccess<ReadingWindow>>) => void)
      | undefined;
    const pending = new Promise<
      ReturnType<typeof readerSuccess<ReadingWindow>>
    >((resolve) => {
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
      continueReading: vi
        .fn()
        .mockResolvedValue(
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
        .mockResolvedValueOnce(
          readerFailure("unavailable", "阅读宿主暂时不可用。", true),
        )
        .mockResolvedValueOnce(readerSuccess(firstWindow)),
      continueReading: vi.fn(),
      sendMessage: vi.fn(),
    };

    render(<FocusReader host={host} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "阅读宿主暂时不可用。",
    );
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

    expect(
      await screen.findByRole("heading", { name: "阅读完成" }),
    ).toBeInTheDocument();
    expect(screen.getByText("The first chunk.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "继续阅读" })).toBeDisabled();
  });

  it("leaves only recovery available after an operation error", async () => {
    const host: ReaderHost = {
      getReadingWindow: vi.fn().mockResolvedValue(readerSuccess(firstWindow)),
      continueReading: vi
        .fn()
        .mockResolvedValue(
          readerFailure("unavailable", "继续阅读暂时不可用。", true),
        ),
      sendMessage: vi.fn(),
    };

    render(<FocusReader host={host} />);
    await screen.findByText("The first chunk.");
    fireEvent.click(screen.getByRole("button", { name: "继续阅读" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "继续阅读暂时不可用。",
    );
    expect(screen.getByRole("button", { name: "继续阅读" })).toBeDisabled();
    expect(screen.getByLabelText("针对当前 Reading Chunk 提问")).toBeDisabled();
    expect(screen.getByRole("button", { name: "重试" })).toBeEnabled();
  });

  it("locks the companion and Continue Reading while a message is in flight", async () => {
    let resolveMessage:
      | ((value: ReturnType<typeof readerSuccess<ReadingWindow>>) => void)
      | undefined;
    const pending = new Promise<
      ReturnType<typeof readerSuccess<ReadingWindow>>
    >((resolve) => {
      resolveMessage = resolve;
    });
    const host: ReaderHost = {
      getReadingWindow: vi.fn().mockResolvedValue(readerSuccess(firstWindow)),
      continueReading: vi.fn(),
      sendMessage: vi.fn().mockReturnValue(pending),
    };

    render(<FocusReader host={host} />);
    await screen.findByText("The first chunk.");
    fireEvent.change(screen.getByLabelText("针对当前 Reading Chunk 提问"), {
      target: { value: "Why?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(screen.getByLabelText("针对当前 Reading Chunk 提问")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "给我一个具体例子" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "继续阅读" })).toBeDisabled();
    resolveMessage?.(readerSuccess(firstWindow));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "继续阅读" })).toBeEnabled(),
    );
  });

  it("preserves the host projection and draft while adjusting the Mist presentation", async () => {
    const host: ReaderHost = {
      getReadingWindow: vi.fn().mockResolvedValue(readerSuccess(secondWindow)),
      continueReading: vi.fn(),
      sendMessage: vi.fn(),
    };
    const { container } = render(<FocusReader host={host} />);
    const currentArticle = (
      await screen.findByText("The second chunk.")
    ).closest("article");
    fireEvent.change(screen.getByLabelText("针对当前 Reading Chunk 提问"), {
      target: { value: "Unsent thought" },
    });
    expect(container.firstChild).toHaveAttribute("data-theme", "mist");
    fireEvent.keyDown(screen.getByLabelText("光场强度"), { key: "End" });
    fireEvent.click(screen.getByLabelText("大字阅读"));
    fireEvent.click(screen.getByLabelText("微光粒子"));
    fireEvent.click(screen.getByRole("button", { name: "专注模式" }));
    fireEvent.click(screen.getByRole("button", { name: "退出专注模式" }));
    fireEvent.click(
      screen.getByRole("button", { name: "回看第 1 段：Method" }),
    );
    expect(
      screen.getByText("The first chunk.").closest("article"),
    ).toHaveAttribute("data-reviewing", "true");
    expect(screen.getByText("The second chunk.").closest("article")).toBe(
      currentArticle,
    );
    expect(currentArticle).toHaveAttribute("data-current", "true");
    expect(screen.getByLabelText("针对当前 Reading Chunk 提问")).toHaveValue(
      "Unsent thought",
    );
    expect(host.getReadingWindow).toHaveBeenCalledTimes(1);
    expect(host.continueReading).not.toHaveBeenCalled();
    expect(host.sendMessage).not.toHaveBeenCalled();
  });

  it("sends a suggested question without overwriting the unsent draft", async () => {
    const host: ReaderHost = {
      getReadingWindow: vi.fn().mockResolvedValue(readerSuccess(firstWindow)),
      continueReading: vi.fn(),
      sendMessage: vi
        .fn()
        .mockResolvedValue(
          readerSuccess({
            ...firstWindow,
            conversation: [
              {
                messageId: "suggestion",
                chunkId: "chunk-001",
                role: "assistant",
                content: "Host example.",
              },
            ],
          }),
        ),
    };
    render(<FocusReader host={host} />);
    await screen.findByText("The first chunk.");
    fireEvent.change(screen.getByLabelText("针对当前 Reading Chunk 提问"), {
      target: { value: "My draft" },
    });
    fireEvent.click(screen.getByRole("button", { name: "给我一个具体例子" }));
    await screen.findByText("Host example.");
    expect(host.sendMessage).toHaveBeenCalledWith(
      {
        receipt: {
          sourceId: "fixture-paper",
          planId: "plan-001",
          chunkId: "chunk-001",
        },
        content: "给我一个具体例子",
      },
      expect.any(AbortSignal),
    );
    expect(screen.getByLabelText("针对当前 Reading Chunk 提问")).toHaveValue(
      "My draft",
    );
    expect(host.continueReading).not.toHaveBeenCalled();
  });

  it("ignores Space while typing or composing and locks repeated keyboard advances", async () => {
    const host: ReaderHost = {
      getReadingWindow: vi.fn().mockResolvedValue(readerSuccess(firstWindow)),
      continueReading: vi.fn().mockReturnValue(new Promise(() => {})),
      sendMessage: vi.fn(),
    };
    render(<FocusReader host={host} />);
    await screen.findByText("The first chunk.");
    fireEvent.keyDown(screen.getByLabelText("针对当前 Reading Chunk 提问"), {
      code: "Space",
      key: " ",
    });
    fireEvent.keyDown(document.body, {
      code: "Space",
      key: " ",
      isComposing: true,
    });
    fireEvent.keyDown(document.body, { code: "Space", key: " ", repeat: true });
    expect(host.continueReading).not.toHaveBeenCalled();
    fireEvent.keyDown(document.body, { code: "Space", key: " " });
    fireEvent.keyDown(document.body, { code: "Space", key: " " });
    expect(host.continueReading).toHaveBeenCalledTimes(1);
    expect(host.sendMessage).not.toHaveBeenCalled();
  });

  it("aborts a pending advance when the host changes and ignores its late result", async () => {
    let resolveContinue!: (
      value: ReturnType<typeof readerSuccess<ReadingWindow>>,
    ) => void;
    const host: ReaderHost = {
      getReadingWindow: vi.fn().mockResolvedValue(readerSuccess(firstWindow)),
      continueReading: vi.fn().mockReturnValue(
        new Promise((resolve) => {
          resolveContinue = resolve;
        }),
      ),
      sendMessage: vi.fn(),
    };
    const replacement: ReaderHost = {
      getReadingWindow: vi.fn().mockResolvedValue(
        readerSuccess({
          ...firstWindow,
          current: {
            ...firstWindow.current!,
            chunkId: "replacement",
            sourceMarkdown: "Replacement host.",
          },
        }),
      ),
      continueReading: vi.fn(),
      sendMessage: vi.fn(),
    };
    const { rerender } = render(<FocusReader host={host} />);
    await screen.findByText("The first chunk.");
    fireEvent.click(screen.getByRole("button", { name: "继续阅读" }));
    const signal = vi.mocked(host.continueReading).mock.calls[0][1];
    rerender(<FocusReader host={replacement} />);
    await screen.findByText("Replacement host.");
    expect(signal?.aborted).toBe(true);
    await act(async () => resolveContinue(readerSuccess(secondWindow)));
    expect(screen.queryByText("The second chunk.")).not.toBeInTheDocument();
    expect(screen.getByText("Replacement host.")).toBeInTheDocument();
  });
});
