# 专题知识库与 Mist 验收 — 2026-09-17

## 需求与实施

先完成本地 [PRD](../.scratch/library-foundation/prd.md) 与 [spec](../.scratch/library-foundation/spec.md)，随后按数据基础、上传工作流、知识库、阅读 UI 顺序实施。稳定目录与命令见 [工作流](library-workflow.md)，决策见 [ADR 0009](adr/0009-topic-library-foundation.md)。`.scratch/` 按仓库约定留在本地，不进入 Git。

此次差距来自工作流和视觉两层：原有上传只有 PDF、缺少专题/用户字段、完成后不规划；元数据和阅读开始事件没有统一投影。视觉层使用过于不透明的卡片、弱光场，右侧 Companion 占据阅读宽度。

## 已实现

- 沿用 workspace/ 唯一文件数据库，来源根目录是一份完整 bundle，专题通过 Source ID 建立多对多关系；已有私有目录未搬迁。
- 来源描述增加年月、期刊/会议、上传者投影，保留完整标题与稳定简称；专题同名复用，并防止不同名称的目录键碰撞。
- 在唯一 state.json 增加可选 reading_started，新 Plan 为待阅读、明确阅读为阅读中、Cursor 完成为已读完。旧数据原地兼容，不批量猜测阅读历史。
- PDF 与 HTML 分别走原有 parser；Markdown 是新增的明确本地导入路径，不冒充 MinerU 能力。保留原件字节，规范文本统一换行；缺失本地图片引用拒绝注册。
- 上传模态框填写专题、默认用户孔祥聪并选择文件；确认后启动 Agent。Host 验证同一原件、有效 bundle、已有计划才允许报告完成。失败保留输入，可重新上传相同原件复用并补做规划。
- 卡片状态黄/蓝/绿，有文字状态辅助；显示元数据、阅读和重读动作、底部专题 tags。重读只重新规划并留在知识库。
- 阅读页可选专题与材料；去掉上传和附件入口；中央底部扁平输入，右边缘横线定位当前会话的历史提问，聚焦显示提问名。Host 对话存储保留。
- 恢复暖白/蓝灰/淡紫光场、半透明玻璃、背景模糊、内高光和柔影，知识库、阅读和上传框使用相同材质。减少透明度/动态效果设置保留。
- 本地 paper-parser、article-parser、focus-map、focus-read 指向统一工作流；上传规划与显式阅读分开。内部执行指令不显示成用户聊天内容。

## 验证证据

- Python 全套：116 项，115 通过。唯一失败为既有 `test_active_skill_surface_contains_only_five_public_skills`：当前目录已有 12 个设计技能，未删除这些技能或修改该断言。
- 新增 7 项文件/Host 验证：同原件双专题、原件字节和 Windows 行号、缺图清理、元数据与专题命名、完整阅读生命周期、表单绑定、未规划不得报成功、HTML/Markdown HTTP 路由（部分场景合并于同一测试）。
- 前端：28 项通过（Reader 19 + Standalone 9）；typecheck、production build、diff check 通过。
- 本机 Node 内置实验性 Web Storage 与 jsdom 冲突；测试使用进程级 `NODE_OPTIONS=--no-experimental-webstorage`。没有修改用户全局环境。
- 构建仍有既有 >500 kB chunk 提示。
- 浏览器：本地生产构建 1280×720 知识库/上传框/阅读空态；独立样例 Host 验证黄蓝绿、双专题 tag、正文与历史提问、键盘聚焦提示；390×844 阅读与知识库实看。阅读 DOM 宽度 390，composer 为 x=14、宽 362、底部 y=832，无横向溢出，附件按钮计数为 0。
- 独立样例通过真实 Core 文件与 HTTP Host 投影，数据位于 ignored tmp/，没有修改真实来源或阅读进度。

## 尚未建立的证据与运行状态

真实 PDF/HTML → MinerU → Agent 规划的远端调用本次未重新执行；协议替身和独立本地 Markdown 验证不等于远端解析验收。未知年月/期刊字段允许为空，提取质量仍取决于原文与 Agent。

当前 8765 服务已确认空闲且 runtime check 通过，但自动审批拒绝终止/重启进程，返回 `blocked by policy`。因此前端 dist 已更新，8765 后端仍是旧进程。用户需重启现有 Host 后再使用新版上传表单：

```powershell
# 在项目目录中，先结束旧 Host，再启动：
.venv/Scripts/python.exe -B -m host --workspace ./workspace --network
```

未执行 Git commit 或 push。既有 `.focus-runtime/` 未纳入本次修改。
