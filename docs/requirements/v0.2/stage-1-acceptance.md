# 阶段 1 入库验收记录

日期：2026-09-21。此记录区分确定性、Host、浏览器、真实 Parser、真实 Runtime 与内容证据。

## 确定性与 Host

- `IngestionApplication` 的公开边界覆盖暂存、更新、确认、处理、查询、续接和取消。未确认项目可重开且零外发；文件或 Topic 变化会清除确认。
- Parser 只生成候选，`IngestionCore` 才能校验并发布。发布要求匹配预期版本、请求 ID、写入方和未取消 attempt；Topic 关联单独提交。
- 可控故障覆盖远端引用持久化、最多两次自动续接、受理不明待核对、重启后续接、无效候选、版本冲突、第二写入方、关联失败只补关联、取消后迟到候选拒绝和 Runtime 取消。
- 相关 Parser／Application／Host／Core 分段回归 58 项通过；最终完整 Python 回归 125 项、UI 回归 40 项通过，UI 类型检查、生产构建与 Python `compileall` 通过。Vite 仅报告既有单块大于 500 kB 的非阻断警告。

## Host 与浏览器

- `POST /library/inbox` 只接收单 PDF 并本地暂存；`confirm`、异步 `process`、`continue`、`cancel` 和 `GET /library/inbox` 分别投影同一个 Application。旧 `/library/sources` 上传规划入口已删除，不再有“入库顺带 Plan／全文准备”的第二路径。
- 网页只保存展示状态；刷新和处理中轮询均重新读取 Host 权威 Inbox。界面覆盖待确认、处理中、状态待核对、可续接失败、取消、文档已发布但 Topic 待恢复和完成，不展示 batch／run／attempt 等内部标识。
- Source 与 Inbox 的 PDF 原件、`content.md` 和相对 `images/` 资源均从已注册 Bundle 读取并经过现有 Host 认证、Origin 和路径边界；无 Plan Source 也可访问。Topic 标签来自 Source Library 唯一关系。
- 使用隔离的真实 `workspace-runtime` 和 Codex CLI 0.154.0 启动生产构建，浏览器实际看到 `DeepStack-paper` 的完成 Inbox、`Stage 1 Runtime` Topic、待规划 Source 及原件／正文入口；点击刷新后投影保持。上传弹窗明确显示“此步只把文件放入 Inbox，不会调用 MinerU 或 Codex”，未再次上传或解析论文。
- 5 项只验证旧 Host 上传规划路径的测试随入口一并删除；一项 Source ID 用例改为验证当前打开／准备路径。当前全套失败清单为空。

## 真实 MinerU

- 在被忽略的新 Workspace 中，由共享 Application 对授权 `2604.04750v2.pdf` 发起一次真实 MinerU precision v4 解析；非秘密 batch 为 `5a5e8ef8-71a4-45e4-b4f2-2675f850ec98`。
- 同一 batch 经续接后完成。期间一次 CDN 下载返回 curl exit 18，未重新上传；最终 Source 发布、Topic 关联、Bundle 校验均成功。再次以改名原件加入第二 Topic 时返回 `document_status=reused`，没有调用 Parser。
- 真实运行暴露完整标题被误用为目录名的 Windows 路径问题。实现随后将 Source Short Name 上限收紧为 80 字符、保留完整 Source Title，并恢复已知 `DeepStack` 工作名规则；回归和基于同一真实 Bundle 的新 Workspace 发布得到 `DeepStack-paper`，没有再次远端解析。
- MinerU v4 官方文档只列出提交与查询操作，未给出取消端点。因此取消立即关闭本地 attempt 的提交资格；远端无法停止时明确显示 `still_running`，不伪造已停止。[MinerU API 文档](https://mineru.net/apiManage/docs?openApplyModal=true)

## 真实 Codex Runtime

- 使用仓库固定 `.venv/Lib/site-packages/codex_cli_bin/bin/codex.exe`，版本 0.154.0，登录为 ChatGPT；模型固定 `gpt-6-astra`。系统 PATH 上另一个 0.130.0 因用户配置含不兼容 `service_tier=default` 无法启动，没有被静默采用。
- Runtime 只收到 4,000 字符候选正文片段和一张复制到临时隔离目录的图片；使用 read-only sandbox、ephemeral 会话、忽略用户配置／规则和严格 output schema。真实结果为 `title_matches=true`、`image_observed=true`；模型不接触正式 Workspace 写入口。
- 第二次真实调用在进程启动后由 Adapter 取消，返回 `cancelled=true`、worker 已结束、Codex exit code 1；没有 Source 写入。官方文档说明非交互 `codex exec` 默认只读并支持显式 sandbox；App Server 支持文本和本地图片输入。[Codex 非交互模式](https://developers.openai.com/zh-Hans/docs/non-interactive-mode)；[Codex App Server](https://developers.openai.com/zh-Hans/docs/app-server)

## 内容抽查

- PDF 共 16 页；真实 Bundle 保留字节一致原件、30 个标题、27 张连续且可解析的引用图片。
- 可视抽查第 1、4、7、10、11、12 页：标题与摘要；Figure 4/5 框架和硬件层次；Figure 7 tile 级计算通信重叠；Figure 13/14 DRAM 层数；Figure 15–19 热与 NoC 分析；Table 4 消融均清晰。
- Bundle 顺序与 PDF 一致；Figure 4/7/13/16 的图片和说明相邻，公式 (3) Little's Law、(4) 网络时间、(5) overlap pipeline 保留在相应方法段落。结构和抽查通过不扩大为全文语义零误差声明。

## 剩余边界

- MinerU precision v4 没有文档化远端取消接口；产品只能保证本地提交闸门和诚实远端状态。
- 真实 Parser 与 Runtime 分别通过同一 Application 的候选边界；Codex 检查复用本轮真实 MinerU Bundle，未为验收重复解析同一 PDF。
- 浏览器验收未重复完整远端故障矩阵；重试、去重、迟到写拒绝和关联恢复沿用同一 Application 的确定性／真实服务证据。
