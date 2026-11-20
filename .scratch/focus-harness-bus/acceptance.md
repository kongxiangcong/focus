# Backend 发布验收

票据 13 保持开放。第二个真实 ACP CLI 的原文往返和取消清理仍待完成。DSH 已单独通过真机准入、源文讨论和取消清理；其 SDK 路径在通过后移除。

## 正式入口与协议替身

| 场景 | 证据 |
| --- | --- |
| 首次进入知识库、四个固定 ID、错误文件与重复 ID、重新扫描、单独加载模型清单、回执复用、多页面同步、应用失败回滚、窄屏 | 在 `da608b2` 预验收通过。基于 `f3801fd` 的正式构建再次通过，两个 Chrome 页面使用 ACP 协议替身。重新扫描发现新增的 Manifest，390 px 视口无横向溢出。[Backend 设置浏览器验收](../../tests/backend_setup_browser.py) |
| 工作区切换、旧实例隔离、复制导入、重新定位 | 基于 `f3801fd` 的正式构建通过完整 Chrome 流程。切换工作区后，从新页面重新打开设置，再导入同一工作区的副本。[工作区浏览器验收](../../tests/workspace_binding_browser.py) |
| CLI 和环境覆盖、跨工作区沿用、无效选择保留知识库、原样恢复保存值、主动应用替换启动覆盖 | [CLI／HTTP 启动验收](../../tests/test_backend_startup.py) 启动实际 Host。测试模型使用本地替身。 |
| 首次请求先验证临时原文，再发送原问题；失败保留输入 | [准入验收](../../tests/test_backend_verification.py) 核对探针与业务请求顺序、请求负载和最终状态。 |
| 同一讨论跨 Backend 延续、HTTP 与 stdio MCP、新会话、取消和过期确认 | [ACP 讨论验收](../../tests/test_acp_discussion.py) 使用两个真实子进程替身和 Host 工具桥，核对来源、摘要、历史、确认状态和进程释放。 |
| 默认导入只解析、显式候选检查使用当前 Backend | [导入测试](../../tests/test_ingestion_application.py) 和 [候选检查测试](../../tests/test_ingestion_runtime.py) 分别覆盖默认导入与显式 AI 检查。 |

浏览器结果和截图默认写入 `tmp/workspace-portability/`。Backend 设置测试可用 `FOCUS_BROWSER_OUTPUT` 修改输出目录，通过 `FOCUS_PLAYWRIGHT_MODULE` 和 `FOCUS_CHROMIUM_EXECUTABLE` 使用本机安装。

发布相关 Host 测试复跑通过 28 项和 17 个子用例。较早一轮有一项间歇失败。单独重复确认 Windows 在发布临时探针来源目录时曾返回 `WinError 5`，发生在启动 CLI 之前。该失败已经交给集成审查修复。

## Windows 11 真机结果

Windows 11 25H2 x64，构建 26200.9974。正式 FOCUS HTTP 检查使用独立临时知识库、合成原文与随机标记。耗时为观测值。

| Backend | 版本和接法 | 已观察结果 | 启动至握手 | 发问至首段 |
| --- | --- | --- | --- | --- |
| Codex | 捆绑 Codex 0.154.0，App Server，`gpt-6-astra` | 集成基线 `f3801fd` 正式 HTTP 首次发送进入 `checking`，通过后回读正确标记。下一轮停止。用操作系统进程句柄核对两个进程退出和临时工作目录删除。按最新要求，本轮跳过 Codex 登录验证。 | 从 Host 启动会话到会话就绪 828 ms，握手未单独计时 | 8,012 ms，含首次准入的总历时 34.351 s |
| DeepSeek | DSH 0.2.1-rc.2，ACP agent 0.0.1，`dsh --profile acp`，`deepseek-v4-flash` | SDK 移除后的内置 `deepseek` 沿用已保存模型和显式凭据路径。首次请求在原文准入通过后自动继续，正式讨论读回随机标记。另一轮停止。操作系统进程句柄确认两轮进程退出，临时目录均已删除。 | 正式轮 1,673 ms，取消轮 1,678 ms | 6,862 ms，含首次准入的总历时 15.276 s |
| Antigravity CLI | 1.5.13，官方 Windows 便携版 | 直接 ACP 握手成功。服务返回 `FAILED_PRECONDITION (400)`，当前地区不可用。正式 FOCUS 原文往返及取消清理未实测。 | 423 ms | 未实测，首次服务错误耗时 1,393 ms |
| Cursor CLI | 2026.11.19-f005e9d，官方 Windows 便携版 | 直接 ACP 握手成功。CLI 要求登录，`session/new` 返回 `-32000`。正式 FOCUS 原文往返及取消清理未实测。 | 2,326 ms | 未实测 |

PATH 中的 Codex 0.130.0 无法读取本机此前已保存的 `service_tier = "default"`。原先由 FOCUS 使用的捆绑 0.154.0 能正常读取，验收保留现有系统 PATH 和用户 Codex 配置。早期预验收的会话就绪耗时为 754 ms，发问至首段 10,069 ms；当时复用现有 ChatGPT 登录的账号查询、4 项模型清单及发起／取消授权通过。

DSH 接入先以自定义 Manifest 验证。在 `734d501`，正式 HTTP 源文往返通过，握手 1,681 ms、取消轮 1,738 ms，首段 5,970 ms。在 `c81f22e`，首次发送观察到 `backendVerification: checking` 并自动继续，握手 1,776 ms，发问至首段 6,930 ms，含准入约 19.7 s。切到内置 `deepseek` 后、移除 SDK 前的复核记录为握手 1,812 ms、取消轮 1,845 ms、发问至首段 4,787 ms，含准入 17.031 s。

第二个真实 ACP CLI 的预验收与剩余条件见 [票据 12](issues/12-second-acp-cli.md)。本记录中的协议替身、握手和服务错误各按观测范围计入，发布门槛仍以正式 Workbench 原文往返和取消清理为准。
