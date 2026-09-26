# Stage 6B / 02 — 统一业务链路验收

日期：2026-09-26。固定 review 基线：`6409e02`。票 02 的三个内部验收段完成；不代表 Stage 6B 发布验收完成。

## 实现和确定性证据

- Reading Preparation、Reading Progress、Reading Blog、Value Analysis、实现检索及 Source Discussion 共用 Backend 工厂；业务结果仍由原 Application/Core 校验和发布。
- 外部协议替身经过公开 Host 操作及真实 Core，覆盖双 Backend 准备/博客、跨 Backend 讨论接续、重启、新建/恢复讨论、越界工具拒绝和显式 Notes。
- 新增公开 Host 回归覆盖 DeepSeek 启动中取消、停止后新建讨论、审批超过旧 120 秒期限后答复、累计长历史摘要和 Codex 关闭完成前保留临时目录。
- 多轮独立 standards/spec review。发现生命周期竞态、取消不唤醒 Host、审批答复超时丢失、早期历史截断，以及解除实验标签后旧切换接口归档讨论；均修复，最后复审无剩余明确缺陷。
- Stage 4 阅读测试 28 passed；Stage 5 batch recovery 7 passed。后者原有未提交测试的 cancel 替身签名随 Source 级取消扩展为可选 source_id，其测试主体保留在未暂存修改中。
- UI 61 tests passed，typecheck/build passed（`02-ui-tests.txt`、`02-typecheck.txt`、`02-ui-build.txt`）。
- 首轮全量 Python 为 344 tests / 9 failures / 30 errors，其中新增一项为上述旧 cancel 替身签名不匹配，已修复。后续一次漏加 `-X utf8` 的运行新增两个编码错误；该运行不用于与 UTF-8 基线比较。UTF-8 全量 349 tests / 8 failures / 30 errors，与初始基线逐个失败身份比较完全相同。最后切换接口修复的公共测试单独通过，最终代码全量正在完成。

## 真实 Runtime 与浏览器

当次运行：Codex 0.154.0 / gpt-6-astra；DeepSeek official SDK/runtime 0.1.5rc1 / deepseek-v4-flash。仅记录版本，不产生版本限制。

- 两种真实 Runtime 均在独立测试知识库产生新 Plan、准备全部三段译文并通过检查，未推进 Cursor（`02-reading-real.json`）。材料是 synthetic fixture，不作为完整论文内容认可。
- 两种真实 Runtime 多轮 Source 问答及明确请求保存 Notes 成功（`02-real/result.json`）。DeepSeek 首次 Blog 失败；显式重试后 Reading Blog、适用 Value Analysis、HTML 完成（`deepseek-blog-retry.json`）。无法确认官方实现时如实记录 paper_reading，不声称运行实现。
- 浏览器 8768（DeepSeek）、8769（Codex）：点击进入阅读→准备完成→打开；引用提问和明确保存 Notes；推进到下一 Chunk 并显示 Reading Progress 摘要；新建讨论保留 Notes/Cursor，选择旧讨论恢复完整历史。
- 浏览器暴露新建讨论后显示 0/0 的投影错误，已修复并验证 DeepSeek 3/3、Codex 2/3 仍保留。Core Cursor 始终未被新建讨论改变。
- 新增确认工具时，真实 Codex 报 canonical/legacy dynamicTools 混用。适配器统一协议格式后，真实浏览器再次问答、保存 Notes 和进度摘要成功；失败用户消息保留，没有伪装第一次通过。
- DeepSeek 真实模型通过 MCP 调用 focus_user_input，浏览器选择 Runtime 后提交；随后显示 focus_confirm，点击拒绝；模型收到拒绝并结束，Notes 数量保持 2。
- Codex 浏览器点击重新生成→生成中→取消，旧 Reading Blog/HTML 保持完成且可在内嵌浏览器打开。
- 浏览器 DeepSeek 完成重新生成，合并 HTML 可打开且 Reading Blog/Value Analysis 两个页签可切换，含合法来源图片。Codex 取消后再点击重新生成，最终恢复完成并可打开 HTML。
- 阶段 1 留存的公开 DeepStack Parser Bundle，在新的隔离知识库重新生成双 Backend 完整 Reading Blog/Value Analysis/HTML，三项均 completed。复用的只有来源材料，不复用旧 Runtime 生成结果或验收结论。
- DeepSeek 首次 Reading Blog Runtime 失败；显式重试 Reading Blog 成功但 Value Analysis 多出右花括号，严格 JSON 校验拒绝该候选。再次只重试 value_analysis 成功，Reading Blog 更新时间不变（15:34:43Z），Value Analysis/HTML 更新于 15:40:11Z/15:40:13Z。没有通过修复非法 JSON 绕过校验。
- Codex DeepStack 三产物分别完成（Reading Blog 15:35:46Z，Value Analysis 15:40:12Z，HTML 15:40:13Z）。两种 Backend 的官方实现检索均留下真实 Host 请求回执及缺口；源码读取未完成，核查层级如实为 paper_reading，不声称 static_review 或执行验证。
- 结果：`02-public/codex-result.json`、`02-public/deepseek-value-retry-result.json`；保留前次失败报告及候选诊断以区分失败/重试。synthetic fixture 与完整公开论文内容证据分别记录。

## 最终结论

- 全量 `python-ticket02-final.txt`：350 tests，8 failures / 30 errors，逐个失败身份与初始基线完全相同。最后补充业务启动错误脱敏后，16 个 Stage 6B 公共 Host 测试全部通过，Backend registry/proxy 10 tests 通过；脱敏修复也经独立复审。
- `02-artifact-audit.json` 记录最终文件哈希；每个 Backend 的 27 个图像资产均与本 Source 原图哈希一致，合并 HTML 分别有 5 / 11 个内嵌图片、50 / 18 个原文锚点链接。生成内容保留结构校验与内容认可的区别。
- 原有未提交修改保留；reading_application、reading_runtime、stage4 测试的原有修改从提交索引中排除，Stage 5 原有新增测试仍未暂存。
- 本票可以提交。票 03–05 尚未实施；设置刷新、跨 Backend 批次恢复、清除/日志及干净 Windows 发布仍必须完成。
