# 01 验收证据

日期：2026-10-06。起点：`0138446c6d67329f4a4ef4f4b001442d0681dcfa`。

## 实现

- `focus-workspace.json` 的稳定 UUID 与格式／读写版本和业务修订分离；只接受新格式，非空旧目录和不兼容版本在锁定、业务存储及恢复前拒绝。
- 全部讨论、摘要、时间线、编辑／清除日志和业务回执进入工作区 `discussions/host.sqlite3`；绑定 UUID，上传引用相对于工作区。原生会话恢复引用不持久化，Runtime 清理诊断仅在机器进程中保留。
- Core 公共操作绑定当前 OS 独占租约，单次打开有新的 writer／instance 身份。停止实际写者、关闭 SQLite 并 checkpoint 后才释放；未停止的写者使关闭失败并保持锁定。
- 清除／重新阅读、讨论上下文及摘要策略、Source 编辑验证和向前恢复移至共享层。已提交 Notes 的幂等身份不依赖机器 writer 字符串。

## 通过

- 项目 `.venv` 下 `test_workspace_portability`：7 项，包括独立进程第二写者拒绝、杀进程后接管、旧进程释放后的迟到操作拒绝、旧 Core 对象拒绝、格式写前拒绝、移动后的讨论恢复、Notes 重开后回执重放。
- `test_stage6b_clear_retention`：8 项，包括 Source 隔离、清除范围与原阅读资产保留、清除中断向前恢复、重复请求不扩大清除、活动写者拒绝。
- 针对性组合运行 100 项：98 项通过；两项 HTML 上传检查受 5 秒客户端等待限制失败，保留全部断言并将测试等待设为 30 秒后，两项单独复验通过（24.161 秒）。日志：`tmp/workspace-portability/ticket01-accepted.txt`、`upload-timeout-recheck.txt`。包含阅读准备、进度、候选保留、清除、讨论、批次断点、删除和博客。
- 上传 HTTP、共享 Source 编辑恢复、生命周期再次合并复验 7 项通过；相对引用正确读取原件。
- `pnpm reader:typecheck` 和 `pnpm reader:build` 通过。
- 真实 Chrome + 隔离 Host + 受控 Runtime 浏览器旅程 10 项通过，页面错误 0。涵盖阅读、锚定提问、Notes 编辑／删除／撤销、重新阅读、回看与正式前沿、窄屏、键盘 Escape、任务及博客展示。结果：`tmp/workspace-portability/focus-browser-results.json`，截图在同目录。

## 基线与限制

- 最终审查补充：受支持 CLI 明确拒绝缺少 manifest 的布局；Store 持有实例租约，过期写入拒绝；retention 写者未结束则保持锁。SQLite 预检通过临时 DB＋WAL 副本保护崩溃回执，损坏 session 在任何业务写入前拒绝，合法 MinerU 数组保留。Core 统一校验删除回执只能清理所属 Source 的待清理路径，不能删除其他 Source 或业务根。最终 29 项删除／工作区复验通过，详见 03。

- 起始提交隔离副本的 `test_web_host`：22 项，1 failure、18 errors；主要为已退休的原文引用／聊天导航和提示词契约。当前同套件同样存在这些失败；本轮上传相对引用导致的额外断言错误已修复且复验通过，不宣称该旧套件全绿。
- Parser／Runtime 为受控替身，上述结果不证明实际供应商内容质量或真实 Runtime 验收。真实双 Backend 验收属于 03；完整目录复制后的组合数据和继续处理属于 02。
- 测试使用本项目 `.venv`。系统 Python 缺少 HTML 依赖且受沙箱临时目录 ACL 影响，其失败不作产品验收证据。
- 未清理任何已有用户运行目录。开始时的 6 个无关文档保持原内容，散列存于 `tmp/workspace-portability/preexisting.json`。
