import type { ReaderChunk } from "@focus/reader-contracts";
import {
  type PointerEvent,
  type ReactNode,
  useEffect,
  useId,
  useRef,
} from "react";

export function ReaderIcon({
  name,
  size = 18,
}: {
  name: string;
  size?: number;
}) {
  const paths: Record<string, ReactNode> = {
    arrow: <path d="M12 4v16m-6-6 6 6 6-6" />,
    up: <path d="M12 20V4m-6 6 6-6 6 6" />,
    chevron: <path d="m9 5 7 7-7 7" />,
    book: (
      <>
        <path d="M12 6c-3-3-7-3-9-2v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-2-1-6-1-9 2Z" />
        <path d="M12 6v14" />
      </>
    ),
    list: (
      <>
        <path d="M9 6h11M9 12h11M9 18h11" />
        <path d="M4 6h.01M4 12h.01M4 18h.01" strokeWidth="3" />
      </>
    ),
    tune: (
      <>
        <path d="M4 7h5m4 0h7M4 17h9m4 0h3" />
        <circle cx="11" cy="7" r="2" />
        <circle cx="15" cy="17" r="2" />
      </>
    ),
    sun: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" />
      </>
    ),
    sparkle: (
      <path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4Z" />
    ),
    chat: <path d="M21 11a8 8 0 0 1-8 8H7l-4 3V11a9 9 0 1 1 18 0Z" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    check: <path d="m5 12 4 4L19 6" />,
    focus: (
      <>
        <path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5" />
        <circle cx="12" cy="12" r="3" />
      </>
    ),
    return: <path d="M20 4v9H5m5-5-5 5 5 5" />,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

export function ReaderMark() {
  return (
    <span className="focus-reader__mark" aria-hidden="true">
      <i />
      <i />
      <i />
      <i />
    </span>
  );
}

export function ReaderProgress({
  chunks,
  current,
  onReview,
}: {
  chunks: readonly ReaderChunk[];
  current: ReaderChunk | null;
  onReview: (chunk: ReaderChunk) => void;
}) {
  const total = current?.total ?? chunks.at(-1)?.total ?? 0;
  const finished = current ? current.index - 1 : total;
  const position =
    total > 1 ? Math.min(finished / (total - 1), 1) : current ? 0 : 1;
  return (
    <aside className="focus-reader__rail" aria-label="Chunk 阅读进度">
      <span className="focus-reader__rail-label">
        READING
        <br />
        JOURNEY
      </span>
      <div className="focus-reader__rail-track">
        <div
          className="focus-reader__track"
          role="progressbar"
          aria-label={
            current
              ? `阅读位置：第 ${current.index} 段，共 ${total} 段`
              : "阅读完成"
          }
          aria-valuemin={0}
          aria-valuemax={total || 1}
          aria-valuenow={finished}
          aria-valuetext={
            current
              ? `已读 ${finished} 段，当前第 ${current.index} 段`
              : "阅读完成"
          }
        >
          <span className="focus-reader__track-line" />
          <span
            className="focus-reader__track-done"
            style={{ transform: `scaleY(${position})` }}
          />
          <span
            className="focus-reader__track-cursor"
            style={{ transform: `translateY(${position * 100}%)` }}
          >
            <i />
            <span>{String(current?.index ?? total).padStart(2, "0")}</span>
          </span>
        </div>
        <div className="focus-reader__rail-links" aria-label="回看已加载段落">
          {total <= 24 &&
            chunks.map((chunk) => (
              <button
                key={chunk.chunkId}
                aria-label={`回看第 ${chunk.index} 段：${chunk.sectionPath.at(-1)}`}
                aria-current={
                  chunk.chunkId === current?.chunkId ? "step" : undefined
                }
                style={{
                  top: `${total > 1 ? ((chunk.index - 1) / (total - 1)) * 100 : 0}%`,
                }}
                onClick={() => onReview(chunk)}
              >
                <span />
              </button>
            ))}
        </div>
      </div>
      <div className="focus-reader__percentage">
        <strong>
          {total ? Math.round((finished / total) * 100) : 100}
          <small>%</small>
        </strong>
        <span>阅读位置</span>
      </div>
    </aside>
  );
}

export function ReaderAppearance({
  intensity,
  onIntensity,
  particles,
  onParticles,
  largeText,
  onLargeText,
}: {
  intensity: number;
  onIntensity: (value: number) => void;
  particles: boolean;
  onParticles: (value: boolean) => void;
  largeText: boolean;
  onLargeText: (value: boolean) => void;
}) {
  const sliderId = useId();
  const details = useRef<HTMLDetailsElement>(null);
  function point(event: PointerEvent<HTMLInputElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    onIntensity(
      Math.max(
        0,
        Math.min(
          100,
          Math.round(
            ((event.clientX - rect.left - 7) / (rect.width - 14)) * 100,
          ),
        ),
      ),
    );
  }
  useEffect(() => {
    function outside(event: globalThis.PointerEvent) {
      if (
        details.current?.open &&
        !details.current.contains(event.target as Node)
      )
        details.current.open = false;
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, []);
  return (
    <details
      className="focus-reader__appearance"
      ref={details}
      onKeyDown={(event) => {
        if (event.key === "Escape" && details.current) {
          details.current.open = false;
          details.current.querySelector("summary")?.focus();
        }
      }}
    >
      <summary aria-label="阅读氛围">
        <ReaderIcon name="tune" size={16} />
        <span>阅读氛围</span>
      </summary>
      <div className="focus-reader__appearance-panel">
        <h2>
          <ReaderIcon name="sun" />
          把光调到刚刚好
        </h2>
        <label htmlFor={sliderId}>
          光场强度 <span>{intensity}%</span>
        </label>
        <input
          id={sliderId}
          aria-label="光场强度"
          type="range"
          min={0}
          max={100}
          value={intensity}
          onInput={(event) => onIntensity(Number(event.currentTarget.value))}
          onPointerDown={(event) => {
            event.currentTarget.setPointerCapture(event.pointerId);
            point(event);
          }}
          onPointerMove={(event) => {
            if (
              event.buttons === 1 &&
              event.currentTarget.hasPointerCapture(event.pointerId)
            )
              point(event);
          }}
          onKeyDown={(event) => {
            const values: Record<string, number> = {
              ArrowLeft: intensity - 1,
              ArrowDown: intensity - 1,
              ArrowRight: intensity + 1,
              ArrowUp: intensity + 1,
              Home: 0,
              End: 100,
            };
            if (event.key in values) {
              event.preventDefault();
              onIntensity(Math.max(0, Math.min(100, values[event.key])));
            }
          }}
        />
        <label className="focus-reader__toggle">
          微光粒子
          <input
            type="checkbox"
            checked={particles}
            onChange={(event) => onParticles(event.target.checked)}
          />
          <span />
        </label>
        <label className="focus-reader__toggle">
          大字阅读
          <input
            type="checkbox"
            checked={largeText}
            onChange={(event) => onLargeText(event.target.checked)}
          />
          <span />
        </label>
        <p>跟随系统的减少动态效果设置</p>
      </div>
    </details>
  );
}

export type ReaderDialogState =
  | { kind: "contents" }
  | { kind: "source"; chunk: ReaderChunk };

export function ReaderDialog({
  state,
  sourceTitle,
  chunks,
  current,
  onClose,
  onReview,
}: {
  state: ReaderDialogState | null;
  sourceTitle: string;
  chunks: readonly ReaderChunk[];
  current: ReaderChunk | null;
  onClose: () => void;
  onReview: (chunk: ReaderChunk) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    if (!state) return;
    const trigger = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    element?.showModal();
    return () => {
      element?.close();
      trigger?.focus({ preventScroll: true });
    };
  }, [state]);
  return (
    <dialog
      ref={dialog}
      className="focus-reader__dialog"
      aria-labelledby={titleId}
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === dialog.current) onClose();
      }}
    >
      <button
        type="button"
        className="focus-reader__icon-button focus-reader__dialog-close"
        aria-label="关闭"
        onClick={onClose}
      >
        <ReaderIcon name="close" />
      </button>
      {state === null ? null : state.kind === "source" ? (
        <>
          <span className="focus-reader__kicker">SOURCE ANCHOR / 原文锚点</span>
          <h2 id={titleId}>{state.chunk.sectionPath.at(-1)}</h2>
          <p className="focus-reader__dialog-source">
            {state.chunk.sourceMarkdown}
          </p>
          <p className="focus-reader__dialog-note">
            {sourceTitle} · L{state.chunk.sourceLines.join("—")}
          </p>
        </>
      ) : (
        <>
          <span className="focus-reader__kicker">
            READING PLAN / 已加载的阅读内容
          </span>
          <h2 id={titleId}>{sourceTitle}</h2>
          <div className="focus-reader__contents">
            {chunks.map((chunk) => (
              <button
                key={chunk.chunkId}
                onClick={() => {
                  onReview(chunk);
                  onClose();
                }}
              >
                <span>{String(chunk.index).padStart(2, "0")}</span>
                <span>{chunk.sectionPath.at(-1)}</span>
                {chunk.chunkId === current?.chunkId ? (
                  <small>当前</small>
                ) : (
                  <ReaderIcon name="check" size={14} />
                )}
              </button>
            ))}
          </div>
          <p className="focus-reader__dialog-note">
            回看不改变阅读位置。尚未加载的段落由「继续阅读」逐段展开。
          </p>
        </>
      )}
    </dialog>
  );
}

export function ReaderParticles() {
  return (
    <div className="focus-reader__particles" aria-hidden="true">
      {Array.from({ length: 24 }, (_, index) => (
        <i
          key={index}
          style={{
            left: `${(index * 37 + 7) % 100}%`,
            top: `${(index * 23 + 11) % 100}%`,
            animationDelay: `${-index * 1.7}s`,
            animationDuration: `${18 + (index % 5) * 4}s`,
          }}
        />
      ))}
    </div>
  );
}
