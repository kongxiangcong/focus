# 11 动效 M1–M13

Status: resolved
Type: task
Blocked by: 09, 10
Covers: spec §7.4、A6、A12

## 目标

还原原型的全部动效，满足中断、减少动效和“业务不等动画”的约束。原型参照：`prototype.html` 中 `setAttached()`、`saveEditor()`、`deleteMark()`、`sweepOut()`、`sourcePoint()` 函数与 CSS keyframes。

## 现状

- 吸附开关：`FocusReader.tsx:843–846`，`preserveReading(() => { setAttachNotes(next); localStorage... })`。`preserveReading` 负责阅读位置保持（不要另写滚动补偿）。
- 减少动效判断模板：`FigurePanel.tsx:45` `document.documentElement.dataset.reducedMotion === "true" || matchMedia("(prefers-reduced-motion: reduce)").matches`。
- 纯 CSS 部分（M1–M4、M10–M13 的 keyframes/transition）已在工单 07 写好；本工单负责 JS 驱动的 M5–M9 和类名触发时机。

## 设计

### `annotations/useAnnotationMotion.ts`

```ts
export function motionAllowed(): boolean          // 上述模板
export function sweepOut(els: Element[], props: ("--anno-hl-w" | "--anno-ul-w")[], done: () => void): void
export function flyIn(card: HTMLElement, from: { x: number; y: number }, opts: { delay: number }): Animation | null
export function flyFromRect(card: HTMLElement, rect: DOMRect): Animation | null
export function flyGhostsToBulbs(ghosts: Ghost[], layer: HTMLElement, target: (key: string) => { x: number; y: number } | null): void
export function snapshotCards(root: HTMLElement): Ghost[]    // 视口内(±40px)卡片克隆 + 矩形
```

- 所有函数在 `!motionAllowed()` 时直接返回（`sweepOut` 立即调用 `done`）。
- 监听 `matchMedia` change：变为 reduce 时 `document.getAnimations()` 中带 `data-anno-motion` 标记目标的动画全部 `finish()`。
- 每次开关生成 token；新 token 出现时取消上一次所有动画并清空飞行层。

### 各效果落地

| 编号 | 触发点 | 实现 |
|---|---|---|
| M2/M3/M4 | 新建/编辑成功的乐观渲染 | 工单 08 已传 `fresh`；确认 `fresh` 只在那一次渲染存在（下一次渲染去掉，避免重放） |
| M5 | 取消重点、删除标注 | 先对该 key 的所有片段 `sweepOut`（240ms ease-inout，`fill:"forwards"`，400ms 兜底），完成后再提交乐观状态的渲染；**请求立即发出**，不等动画 |
| M6 | 删除 | 灯泡：`animate([{transform:"scale(1)"},{opacity:0,transform:"scale(.3)"}], 170ms ease-in, forwards)`；卡片：`[{opacity:1},{opacity:0, transform:translate(10px, ${top}px) scale(.97)}]` 170ms |
| M7 | 吸附开 | `useLayoutEffect` 依赖 `notesLayout` 从 off→side/split：① 开关前记录第一个可见 `.reading-group-passage` 正文列左边（在点击处理器里、`setAttachNotes` 之前存入 ref）；② 布局后算 `dx`，对视口内正文列 `animate(translateX(dx)→none, 380ms ease-out)`；③ 每张视口内卡片 `flyIn(card, 灯泡矩形左上 + dx)`，依次 35ms；④ 小段笔记区加 `is-entering`（CSS，240ms，delay 160ms） |
| M8 | 吸附开时编辑框提交 | 提交前取 `editorRect`；保存成功（乐观渲染）且卡片挂载后 `flyFromRect(card, editorRect)`：`translate(dx, top+dy) scale(editor.width/card.width)`、opacity .4 → 终态，380ms ease-out；`finished` 后加 `is-saved` |
| M9 | 吸附关 | 点击处理器中、状态切换前 `snapshotCards`；`useLayoutEffect` 中把克隆放入 `.reader-anno-ghost-layer`（`position:fixed; inset:0; pointer-events:none`，挂在 FocusReader 根下），飞向灯泡矩形（`scale(.1)` + 淡出，380ms ease-inout，依次 30ms，`finished`/取消都移除）；给所有灯泡设置 `--bulb-delay: ${260 + min(k,8)*30}ms`，900ms 后移除 |
| M10 | 点卡片 | 工单 09 已加 `is-pulse` |
| M11 | 小段笔记新条目 | 工单 10 已加 `is-new` |
| M12 | 折叠行 | CSS |
| M13 | 卡片重新排布 | 工单 09 `.no-anim` |

坐标说明：`flyIn` 的起点用灯泡 `getBoundingClientRect()`（吸附开时灯泡 `visibility:hidden` 但仍参与布局，可测量）；卡片终态矩形已经包含 `translateY(top)`，所以起始 transform 为 `translate(from.x - fr.left, top + from.y - fr.top) scale(.12)`，终止为 `translate(0, top) scale(1)`，`transform-origin: 0 0`，`fill:"backwards"`。

### 约束

- 状态、请求、焦点都不等待 `finished`。
- 不对视口外元素做动画。
- 不使用 `transition: all`；不常驻 `will-change`。

## 实施步骤

1. `Status: claimed`。
2. 单元测试（jsdom 不跑 WAAPI，用 `Element.prototype.animate` mock）：
   - reduce 时不调用 `animate`、`sweepOut` 同步调用 `done`；
   - 吸附开：每张视口内卡片调用一次 `animate`，起点为对应灯泡；再次切换取消前一次动画（mock `cancel` 被调用）、飞行层清空；
   - 删除：请求在动画开始前已发出；
   - `fresh` 只出现在一次渲染中。
3. 实现。
4. 浏览器中间帧截图（工单 13 自动化）。

## 验收标准

- 单元测试通过；浏览器中：开关期间 `document.getAnimations().length > 0`，结束后飞行层为空；reduce 下 `getAnimations()` 为 0 且最终状态正确。

## 测试

```bash
pnpm --filter @focus/reader-ui test -- useAnnotationMotion AnnotationRail annotations
```

## Comments

- 2026-10-23: visual claimed after 09/10 integration at 26aad9d. Implementing M5–M9 with the local animate skill; accepted spec timings and zero-animation reduced-motion rules take precedence over generic recipe defaults.
- 2026-10-23: Implemented `useAnnotationMotion` with cancellable WAAPI ownership, viewport filtering, safe inert/aria-hidden flying clones, editor→card geometry, retoggle/source/reset cleanup, and live media/root reduced-motion handling. All card/popup deletes share the same immediate-request wrapper; only their captured visual records remain until the 240ms sweep or 400ms fallback. M6 final opacity persists until the sweep releases the record. Existing CSS owns M1–M4/M10–M13; the bubble transform origin now reads the placement wrapper's actual side.
- Verification: public tests first failed on the missing motion module, then passed. Final focused regression: 51 tests across 11 suites, including 7 motion cases and a one-time fresh-flag regression. Reader UI + standalone TypeScript checks passed; standalone build passed (422 modules; existing bundle-size advisory). Root's real Chrome candidate passed A6 WAAPI intermediate-card target, 43px coarse hit target, A12 zero animations under reduced motion and business/geometry checks; final 13 error-gate rerun is owned by root after fixture-only HMR/about:blank fixes.

## Answer

M5–M9 are connected to the existing annotation actions and layout without delaying Host writes, business state, focus, or reading-position preservation. A fresh toggle cancels old flights and removes their ghost layer; media or root reduced-motion changes immediately finish/clear motion and release retained visual records. Ghosts cannot receive focus or participate in accessibility navigation. The existing fresh classes expire after their one-time entrance and do not return on later renders.
