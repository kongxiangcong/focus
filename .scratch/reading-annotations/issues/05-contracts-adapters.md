# 05 合同与适配器（含演示数据）

Status: resolved
Type: task
Blocked by: 03, 04
Covers: spec §4.5、§4.3（前端）、A8–A9（数据部分）

## 目标

前端类型、HTTP 适配器、fixture 适配器支持 Reading Highlight（重点），以及 Reading Note 的 `placement` 与 `sentence`（句子备注）；提供一份与原型相同内容的演示数据，供单元测试、浏览器测试和手动演示共用。

## 现状

- `ui/packages/reader-contracts/src/index.ts`
  - `SourceNote`（86–100）：`anchor: {sourceId; bundle; sourceLines; quote?} | null`，无 `placement`。
  - `SourceNoteOperation`、`SourceNoteRequestResult`（120–128）。
  - `ReadingWindow` 的 `sourceNotes?`、`noteFeedback?`、`noteOperation?`（181–185）。
  - `CreateSourceNoteInput`（396–404）；`ReaderHost` 的 `createSourceNote?`、`changeSourceNote?`、`sourceNoteRequestResult?`（406–450）。
- `ui/apps/standalone/src/adapters/http-reader-host.ts:414–436`：`createSourceNote`、`changeSourceNote`、`sourceNoteRequestResult` 的请求写法（`this.request(path, {method, headers, body})`，instance 头由 `request` 统一加）。
- `ui/apps/standalone/src/adapters/fixture-reader-host.ts:27–51`：`FixtureReaderHost` 内存笔记实现（没有 `changeSourceNote`）。
- 测试：`ui/apps/standalone/src/adapters/direct-note.test.ts`（7–11 行断言请求体）。

## 设计

### 1. 合同

```ts
export interface NotePlacement { sourceId: string; bundle: string; sourceLines: readonly [number, number] }
export type AnnotationLayer = "source" | "translation";
export interface SentenceQuote { exact: string; prefix: string; suffix: string }
export interface SentenceLocator {
  planId: string; chunkId: string; layer: AnnotationLayer;
  range: { start: number; end: number }; quote: SentenceQuote;
}
export interface SentenceInput { layer: AnnotationLayer; range: { start: number; end: number }; quote: SentenceQuote }

// SourceNote 增加（均可选，兼容旧 Host）：
placement?: NotePlacement | null;
sentence?: SentenceLocator | null;
// CreateSourceNoteInput 增加：
sentence?: SentenceInput;            // 必须同时给 chunk；kind 必须 "thought"，origin 必须 "user"

export interface ReadingHighlight extends SentenceLocator {
  highlightId: string; sourceId: string; revision: number; bundle: string;
  sourceLines: readonly [number, number]; deleted: boolean; canUndo: boolean; sourceUpdated: boolean;
}
export interface CreateHighlightInput extends SentenceInput {
  sourceId: string; requestId: string; chunk: { planId: string; chunkId: string };
}
export interface HighlightOperation {
  sourceId: string; status: "saved" | "changed" | "conflict";
  operation?: "delete" | "undo"; highlight?: ReadingHighlight; current?: ReadingHighlight;
}
// ReadingWindow 增加：
sourceHighlights?: readonly ReadingHighlight[];
highlightOperation?: HighlightOperation | null;
// ReaderHost 增加（全部可选）：
createHighlight?(input: CreateHighlightInput): Promise<ReaderHostResult<ReadingWindow>>;
changeHighlight?(sourceId: string, highlightId: string, operation: "delete" | "undo",
  expectedRevision: number, requestId: string): Promise<ReaderHostResult<ReadingWindow>>;
highlightRequestResult?(sourceId: string, requestId: string): Promise<ReaderHostResult<HighlightOperation | { status: "cancelled" } | null>>;
```

另导出纯函数 `sentenceNoteText(note: SourceNote): string`（放在 `reader-contracts`，便于 UI 与将来的导出共用）：有 `sentence` 时返回 `` `「${note.sentence.quote.exact}」\n${note.content}` ``，否则返回 `note.content`。

### 2. HTTP 适配器

照抄 `createSourceNote` 写法：
- `createHighlight({sourceId, ...input})` → `POST /library/sources/${enc(sourceId)}/highlights`，body 为其余字段。
- `changeHighlight` → `POST .../highlights/${enc(id)}/${operation}`，body `{expectedRevision, requestId}`。
- `highlightRequestResult` → `GET .../highlights/requests/${enc(requestId)}`。
- `createSourceNote`：`sentence` 存在时原样放进 body（现有实现若是逐字段拼 body，需要加上这一项）。
- 错误码沿用 `request` 的统一映射，确保 `highlight_bundle_changed`、`note_sentence_invalid` 以 `code` 透出。

### 3. Fixture 适配器

在 `FixtureReaderHost` 增加：
- `highlights: ReadingHighlight[]` 与 `requests` 幂等表，校验规则与 Core 一致（spec §4.1），`sourceLines` 取 fixture Chunk 行范围，`bundle = "fixture-bundle-v1"`。
- `createSourceNote` 支持 `sentence`（规则同 spec §4.3：要有 chunk、kind/origin 限定），记录带完整 `sentence`。
- 补上 `changeSourceNote`（edit/delete/undo，修订号冲突返回 conflict）——句子备注与小段笔记的编辑删除都要用。
- `writeOutcome: "success" | "failed" | "bundle_changed"` 开关，同时作用于重点与笔记写操作（失败场景测试用）；另加 `failNext(entity: "highlight" | "note")` 让下一次某一类写操作失败，用于“删除只成功一半”测试。
- `snapshot()` 返回 `sourceHighlights`、`highlightOperation`。

### 4. 演示数据 `tests/fixtures/reading-annotations-demo.json`

内容取自 `prototype.html` 的 `CHUNKS`、`SEED_MARKS`、`SEED_CNOTES`、`DIALOGUE_NOTE`（原文逐字复制，不要改写）：

- `source`：`{ sourceId: "demo-anno", title: "片上缓冲区的动态分区（示例文本）" }`
- `chunks`：3 个 ReaderChunk，`planId: "plan-anno"`，`chunkId: "c1"/"c2"/"c3"`，`index 1–3`，`total 3`，`bundleVersion: "anno-v1"`，`sourceLines: [1,4] / [5,8] / [9,12]`，`sourceMarkdown` = 两段原文以 `"\n\n"` 连接，`translation: null`，`presentationStatus: "source-ready"`，其余字段空数组/空值。
- `sourceNotes`（小段笔记）：c1 一条 `kind:"thought", origin:"user"`，`anchor` 指向 c1 行范围；c2 一条 `kind:"conclusion", origin:"dialogue"`，`anchor: null`，`placement` 指向 c2 行范围（证明 placement 投影生效）。
- `markSeeds`：6 条 `{chunkId, exact, highlight: boolean, note: string}`，与原型 `SEED_MARKS` 一致。测试辅助函数 `seedMarks(json)`（`ui/packages/reader-ui/src/test-support/annotation-demo.ts`）用工单 06 的 `hastAnnotatableText` 算出 `range`/`prefix`/`suffix`，然后：`highlight: true` → 生成一条 `ReadingHighlight`；`note` 非空 → 生成一条带 `sentence` 的 `SourceNote`（`kind:"thought"`, `origin:"user"`, `content = note`, `anchor` = 该 Chunk 行范围）。二者都有时区间相同，渲染时合成一个标注。返回 `{ highlights, notes }`。
- `dialogueNote`：原型 `DIALOGUE_NOTE`，`placement` 指向 c3。

## 实施步骤

1. `Status: resolved`。
2. 失败测试：
   - `direct-note.test.ts` 旁新增 `highlights-adapter.test.ts`：HTTP 三个方法的 URL、方法、body、instance 头；`createSourceNote` 带 `sentence` 时 body 含 `sentence`；fixture 重点创建/重放/冲突/各校验分支/delete/undo；
   - fixture 句子备注：无 chunk、kind 不对 → 拒绝；`changeSourceNote` edit/delete/undo；
   - `sentenceNoteText` 两种情况；
   - 合同类型编译（`pnpm reader:typecheck`）。
3. 实现。

## 验收标准

- 测试与类型检查通过；旧 Host（不返回 `placement`/`sentence`/`sourceHighlights`）下 UI 编译与运行不受影响（字段可选）。

## 测试

```bash
pnpm reader:typecheck
pnpm --filter @focus/standalone test -- highlights-adapter direct-note
```

## Comments
## Answer

已扩展 SentenceLocator/ReadingHighlight/NotePlacement 与可选 Host 能力；HTTP 重点接口、instance 头及错误码透传；fixture 创建/修改/删除/撤销、幂等、修订冲突、按实体一次性失败与统一写失败模式。FixtureReaderHost 支持传入 source/chunks/notes/highlights 供共享演示使用，默认数据与旧 noteCreateOutcome 保持兼容。演示 JSON 按原型逐字提取 3 段、6 标注种子、2 小段笔记与讨论示例。

依赖修正：05 创建演示 JSON；依赖 hastAnnotatableText 的 seedMarks 辅助函数移至 06，避免 05→06→05 循环。

验证：highlights-adapter + direct-note 共 9 项通过；CSS 静态检查 4 项通过；reader-contracts、reader-ui、standalone 三个 TypeScript 项目检查均通过。CSS 检查改用 Vitest 动态 actual Node 文件读取，避免浏览器包额外引入 @types/node（Vitest 默认会把 CSS ?raw 导入替换为空字符串）。
