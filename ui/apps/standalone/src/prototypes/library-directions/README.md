# 知识库原型 · 方案 A（列表 + 详情面板）

只读参考实现，对应 `docs/design/FOCUS_LIBRARY_REDESIGN_SPEC.md`。数据为合成，未连接 Host；凡与规范冲突，以规范为准。

## 运行

```bash
cd ui/apps/standalone
npx vite --port 5281 --strictPort --host 127.0.0.1
# 打开 http://127.0.0.1:5281/prototypes/library-directions/index.html
```

URL 参数：`theme=light|dark`、`density=compact|comfortable`、`s=normal|empty|offline`。左下角控制台可切换主题、密度、低动态、4× 慢放与数据场景。生产构建（`vite build`）只打包 `index.html`，不含本原型。

## 文件

| 文件 | 内容 | 对应规范 |
| --- | --- | --- |
| `data.ts` | 合成来源、专题、入库任务；字段沿用 `@focus/reader-contracts` | — |
| `model.ts` | 状态词表、行内主动作、状态筛选、博客摘要 | §3 |
| `store.ts` | 本地模拟 Host：专题排序、入库进度与入库后转为来源；其余动作只提示 | — |
| `parts.tsx` | 材料行、卡片、影子行、⋯ 菜单、详情面板、空状态、FLIP 排序 | §4 |
| `Library.tsx` | 页面布局、继续阅读条、专题头、筛选、键盘、拖入上传 | §4–§5 |
| `library.css` | 样式；颜色/尺寸/动效全部取自生产 `focus-tokens.css` | §2、§6–§7 |

## 与生产实现的差异（有意保留在原型里）

- 上传直接加入模拟队列；生产必须打开现有上传对话框。
- 拖拽排序在 `dragover` 时即时改本地顺序；生产只在 `drop` 时提交一次 `manageTopic(reorder)`，失败回滚。
- 「编辑」「重新规划」「重新阅读」「删除」等只显示提示；生产沿用现有对话框与确认流程。
- 原型没有 Host 忙碌态；生产中所有动作仍受 `busy` / `active` / `managementBusy` 约束。
