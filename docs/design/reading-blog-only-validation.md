# 带读博客单页输出验证

日期：2026-10-20。范围：ADR 0029、article-blog-v2；保留本次开始前未提交的阅读宽度、吸附讨论与引用删除修改。没有改动全局技能或用户已有博客目录。

## 实现

- 方法包仅保留带读写作与阅读排版；删除专用手册、分类、实现检索、独立写作和重试流程。
- Application、Core、Host、DSH worker、前端及原型统一为 `reading_blog / html`；保留 `all`。旧接口目标返回 HTTP 400，且没有创建生成任务。
- 生成 HTML 只有一个带读正文页；无标签页或占位页。来源绑定、图片、公式、引用、取消、迟到结果、幂等和发布校验继续保留。
- v1 兼容读取不写磁盘；分类或退役写作步骤的失败、运行中、待处理记录不阻塞当前产物。明确重渲染或重生成才升级元数据；旧 Markdown 与实现证据保持字节不变，包括无法按 UTF-8 解码的历史文件。

## 验证证据

- `test_blog*.py`：55 项通过，覆盖核心、Runtime、Host、HTML、失败重试、取消与发布。随后补充分类历史状态子场景，`test_blog_reading_artifact` 的 16 项再次通过。
- 方法包、DSH worker、批量导入/恢复、单篇导入、切换后端续跑和后端博客生成：最终集中运行 43 项通过，见 `feature-integration-final.log`。
- 前端：reader-ui 89 项、standalone 152 项通过；`pnpm reader:typecheck` 与 `pnpm reader:build` 通过。构建仍有大于 500 kB 的 chunk 提示。
- 方法包 `quick_validate.py` 通过；`git diff --check` 通过。
- `tests/blog_reading_browser.py` 使用临时工作区、真实 Host/Core 和确定性 Runtime，通过生成入口、首次写作失败后的重试、两项状态、单页内嵌查看器、图片加载及退役目标拒绝；无浏览器脚本错误。
- 全仓残余检查：退役名称仅见于历史验收/决策记录、兼容逻辑和否定/兼容测试。旧 ADR 0013 标记为由 ADR 0029 取代。

日志保存在本地 `.scratch/remove-value-analysis/`，未作为用户产物提交。系统 Python 缺少集成测试依赖，最终后端验证使用项目 `.venv`；技能校验使用带 PyYAML 的系统 Python。

## 扩展测试的既有失败

扩展运行覆盖 79 项测试。最终博客相关测试另行集中复核；以下四项在导出的 HEAD 基线与本次代码中均失败：

- `test_progress_worker_blocks_configuration_after_cursor_has_advanced`
- `test_codex_prepares_full_source_using_same_candidate_contract`
- `test_deepseek_prepares_full_source_without_moving_cursor`
- `test_long_discussion_carries_cumulative_summary_across_restart_and_backend`

前三项均因测试读取 `current=None` 抛出 TypeError；最后一项预期累计摘要至少两次，实际为零。未改写这些断言或宣称扩展套件全绿。测试启动器仅跳过 `test_focus_read` 对已移除 CLI 的未使用初始化，未替换业务实现。

浏览器和后端证据使用确定性模型替身；本次未调用真实外部模型，不代表真实写作质量验收。
