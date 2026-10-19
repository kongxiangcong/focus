# editorial-ui 1.1.0 — 发布验证

验证日期：2026-10-17。本报告针对当前可下载技能包；不是 FOCUS 实施验收，也不是用户本地 external 的审查报告。

## 本次改动范围

升级开发工作流与元数据，新增参考库只读快照工具及单元测试，补齐参考采用、授权重构、参数优先级、阶段范围和交付规则。修正一处浏览器测试在原生关闭事件清理前即断言的时序问题。没有修改模板运行逻辑。

全部 16 个 `assets/` 文件（包括 JSON、CSS、JS、HTML）与 1.0.0 逐字节相同；证据见 `unchanged-assets.json`。数值资产中的 1.0.0 表示未改变的资产版本，不是 skill 版本遗漏。

## 当前结果

| 检查 | 结果 | 实际证据与边界 |
|---|---|---|
| 构建可重复性 | PASS | `build-check.txt`；5 个生成文件与源码一致 |
| 技能包有限元数据/本地引用检查 | PASS | `bundle-check.json`；自定义校验器，不是官方认证 |
| Python 单元回归 | PASS | 74 项，`unit-tests.txt`；原有 44 项＋新增 30 项 |
| 指定不透明色对比度 | PASS | 22 对；仅模板指定前景/背景，不含 FOCUS 的 CDS 目标色 |
| 三份 HTML 静态离线检查 | PASS | `offline-*.json`；启发式检查，不是安全证明 |
| Chromium 模板行为回归 | PASS | 最终 126 项，0 失败；`browser-inline/browser-results.json` |
| 测试路径中的外部请求/未捕获页面错误 | PASS | 各 0；仅所执行路径 |
| 原生 file:// 直开 | NOT_RUN | 页面导航被管理策略 `ERR_BLOCKED_BY_ADMINISTRATOR` 阻止；原始脚本执行失败保留在 `browser-file/`，不当作产品行为失败或通过 |
| 本次视觉截图检查 | PASS（有限范围） | 检查了 reader 390px light 和 flow-explorer 1440px dark；未见裁切/文字无法辨认；不等于全部截图人工审核 |
| 用户本地参考库/FOCUS UI | NOT_RUN | 本次依据上传分析与现有技能包编辑；未访问用户工作树或 external |
| Codex/Claude/Cursor 安装发现与实际 Agent 生成 | NOT_RUN | 本次核对相关元数据/部分文档；没有在这些产品中执行生成评测 |
| 原生系统 IME/读屏器/真机触摸/Safari/Firefox/200% 缩放 | NOT_RUN | Chromium 合成事件和模板测试不能代替这些项目 |

## 浏览器方法

Python 3.13.5，Chromium 144.0.7559.96。复用已安装 Playwright/Chromium，没有安装依赖。

先尝试 `python scripts/browser_smoke.py --transport file --out validation/browser-file`，导航被策略阻止。随后在未修改浏览器策略的情况下，采用允许的 `--transport inline`，把同一份 HTML 内容加载到全新断网 context，阻止 HTTP(S) 并记录请求。此方式验证内容渲染与交互，不验证 file origin。

最终命令：
```bash
python scripts/browser_smoke.py --transport inline --out validation/browser-inline
```

## 发现与修复的测试竞态

首次 inline 测试在“关闭正在运行的说明弹窗会取消工作”处失败，保留于 `browser-inline-initial/` 和对应日志。诊断记录 `dialog-close-diagnostic.json` 显示 Escape 后 `dialog.open` 已为 false，但原生 close 回调约 8ms 后才执行，届时 stop 控件转为 disabled，符合预期。

浏览器测试已改为在 2 秒超时内等待“弹窗已关闭且任务停止”的同一可观察终态，然后执行原断言。没有删除断言、改成宽松成功条件或修改模板 JS。最终重新运行整套测试通过。这里修的是测试同步方式，不是声称已修复一个 FOCUS 问题。

## 新增测试到底验证什么

参考快照：摘要一致、只检查声明文件、不写参考树、缺失/越界/外部符号链接/二进制/环境文件/超限处理、CLI JSON 与退出码、普通子目录不误用父 Git HEAD、独立仓库 clean/dirty 与未提交内容摘要。

文档/包契约：版本、三模式与两视觉策略、产品参数优先级、按需引用、显式调用策略、参考目录约束、历史证据归档、真实切片和必做范围措辞。它们是静态约束测试，不证明 Agent 在实际任务中必然遵循指令。

## 历史记录与边界

1.0.0 原证据保留在 `history/1.0.0/validation/`，没有冒充本轮结果。没有 FOCUS 性能/帧率基准、无障碍认证或“生成质量提升百分比”结论。技能使用效果仍须由本地执行与 FOCUS 自己的回归证明。
