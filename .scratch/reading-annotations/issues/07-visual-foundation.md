# 07 视觉基础：token 与组件样式

Status: resolved
Type: task
Blocked by: —
Covers: spec §7.1、§7.2、U3、A2、A14

## 目标

把原型的视觉数值落到产品 token 和一份新 CSS 中，后续交互工单只拼类名。

## 现状

- `ui/packages/reader-ui/src/focus-tokens.css`：唯一数值来源（文件头注释要求组件 CSS 不建第二张表）。浅色 `:root`（mark 类 38–41 行，motion 70–80 行），深色 `:root[data-theme=dark]`（约 120–150 行）。
- 组件 CSS 通过 `FocusReader.tsx:11–12` 引入（`reader-shell.css`、`mist-reader.css`）。
- 字体：`ui/apps/standalone/src/reading-fonts.css` 为 “FOCUS Source Han Serif” 提供 400 与 **700** 两个字重——加粗用 700，不会合成伪粗体。
- 减少动效约定：`:root[data-reduced-motion=true]` 与 `@media (prefers-reduced-motion: reduce)` 两者都要处理（参考 `mist-reader.css` 264–268 行写法）。
- 现有 `.focus-markdown mark`（`reader-shell.css:37`）是作者 `==高亮==` 样式，**不要**改动或复用。

## 设计

1. `focus-tokens.css`：按 spec §7.1 表加入全部 `--reader-anno-*` token（浅色与深色各一组）与 `--reader-ease-pop: cubic-bezier(.34,1.5,.64,1)`。
2. 新文件 `ui/packages/reader-ui/src/reader-annotations.css`，在 `FocusReader.tsx` 中 `import "./reader-annotations.css";`（放在 `mist-reader.css` 之后）。内容：
   - spec §7.2 代码块原样放入（`@property`、`.reader-anno*`、`.reader-anno-bulb*`）；
   - 按 spec §7.2 映射表，从 `prototype.html` `<style>` 移植：卡片、卡片引文/正文/操作、连接短线、联动态、`is-saved`；气泡、气泡按钮、分隔线、提示文字；浮层 `.reader-anno-pop`、箭头；编辑框（含类型单选 `.reader-anno-kinds`）；小段笔记区 `.reader-chunk-notes`（标题、条目、标签 `.reader-chunk-notes__tag` 与 `--dlg`、悬停操作、空态、按钮行）；折叠行 `.reader-chunk-notes-fold`；飞行层 `.reader-anno-ghost-layer`；
   - 所有颜色换成 token；尺寸、圆角、间距保持原型数值；
   - 动画 keyframes：`reader-anno-hl-in`（`from{--anno-hl-w:0%}`）、`reader-anno-ul-in`、`reader-anno-pulse`、`reader-anno-bulb-pop`、`reader-anno-pop-in`、`reader-anno-enter`、`reader-anno-fresh`、`reader-anno-settle`；类名与组合规则同原型（`.is-new-hl`、`.is-new-note`、二者同时、`--tail` 延迟）。具体时长见 spec §7.4；
   - 吸附开时灯泡隐藏：`.focus-reader[data-notes-layout=side] .reader-anno-bulb, .focus-reader[data-notes-layout=split] .reader-anno-bulb { opacity:0; transform:scale(.4); visibility:hidden; pointer-events:none; transition: opacity 140ms ease-in, transform 140ms ease-in, visibility 0s 140ms; }`（用 token），默认态 `transition: opacity/transform 240ms ease-out var(--bulb-delay,0s), visibility 0s var(--bulb-delay,0s)`。堆叠布局（工单 09 的 `data-anno-rail=stacked`）也隐藏灯泡；
   - 减少动效：本文件内所有 `animation`/`transition` 在两种条件下设为 `none`。
3. 删除：`mist-reader.css` 中仅服务旧 `AttachedNotes` 的 `.reading-group-notes*`、`.reading-note-*`、`.reading-notes-empty` 规则（约 282–300、382 行）**放到工单 09 完成替换后再删**，本工单只新增。

## 实施步骤

1. `Status: resolved`。
2. 写一个静态样式检查测试 `reader-annotations-css.test.ts`：读取 CSS 文本，断言没有十六进制颜色字面量；`rgba()` 只允许出现在阴影和白/黑半透明叠加层（如气泡按钮悬停 `rgba(255,255,255,.13)`、灯泡阴影 `rgba(29,33,37,.10)`），其余颜色一律引用 token、所有 `--reader-anno-*` 在 tokens 中都有浅/深两份定义、存在 reduced-motion 两种关闭规则、`.reader-anno--hl` 含 `font-weight:700`。
3. 实现。
4. 做一个临时 Storybook 式页面不需要；用工单 06 的单元测试渲染一次，人工检查计算样式即可（`getComputedStyle(el).fontWeight === "700"`，jsdom 中通过导入 CSS 不生效，此检查放到工单 13 浏览器测试）。

## 验收标准

- CSS 检查测试通过；`pnpm reader:build` 通过；无新增颜色字面量散落在组件 CSS。

## 测试

```bash
pnpm --filter @focus/reader-ui test -- reader-annotations-css
pnpm reader:build
```

## Comments
## Answer

已实现浅/深色批注 token、原型组件样式、700 字重、八类基础动效及浮层/折叠/灯泡样式；同时处理系统与应用减少动效设置。原有作者 mark 与 AttachedNotes 样式保留。

验证：reader-annotations-css.test.ts 4 项通过；直接调用现有 Vite 执行与 reader:build 相同的 standalone 生产构建通过（397 modules）。pnpm 在独立 worktree 触发依赖自动安装并遇到 sandbox symlink 权限，改用共享既有依赖与直接 CLI；浏览器计算样式/截图由工单 13 验收。
