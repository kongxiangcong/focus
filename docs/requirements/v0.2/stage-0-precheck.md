# 阶段 0 预检查记录

日期：2026-09-21。本轮预检查结果已记录；需求 grill 已完成，以下未测项目仍保留，不能作为阶段 0 全部通过声明。

## 本地恢复与隔离

已创建本地 annotated tag `v0.1-pre-v0.2`，解析至 `1de307f51c9bd674b8c7efc053e57e5e5b777276`，未推送。它仅保存旧代码，不含当前未提交变更或私人资产。

已创建 `.scratch/focus-v02-stage0/{workspace,host-data,evidence}/`，`git check-ignore` 确认 Workspace 和 Host 数据均被忽略。恢复时使用独立旧版代码目录与旧 schema 数据副本，不把旧程序指向试验目录；数据备份和恢复演练尚未执行。

## 参考配置

- Codex 二进制：`.venv/Lib/site-packages/codex_cli_bin/bin/codex.exe`；实际 `--version` 返回 `codex-cli 0.154.0`，`login status` 返回 `Logged in using ChatGPT`，退出码均为 0。
- 本地配置模型为 `gpt-6-astra`、reasoning 为 `medium`；这是配置值，不是模型实际成功响应的证明。真实调用、图像能力、网络、取消和恢复尚未验证。
- Host 的 `--model` 默认读取 `FOCUS_MODEL`；示例中的 `FOCUS_CODEX_MODEL` 未被该入口消费。两者本次均未设置。
- 当前 Runtime 有 workspace-write 和 shell/patch 能力；现有检查不足以证明 v0.2 的受限工具及 Core 唯一提交边界。需在新链路收敛并验收。
- MinerU 从仓库根忽略的 `.env` 找到凭据，未输出凭据。样例 `2604.04750v2.pdf` 为 18,465,727 bytes，PDF 文件头检查通过。用户已授权该样例外发，真实解析已完成，进程退出码 0，注册为 `DeepStack-paper`。

复现命令（从仓库根执行，保持该凭据发现位置）：

```powershell
.venv/Scripts/python.exe -B -X utf8 .agents/skills/paper-parser/scripts/mineru_precision.py parse 2604.04750v2.pdf --workspace .scratch/focus-v02-stage0/workspace --timeout 40 --poll-interval 5
```

`--timeout 40` 仅约束解析等待，不是整个命令的时限；现有上传和下载各允许最长 600 秒。本次非秘密 batch ID 为 `2aff5a7d-1792-4ab1-b8cc-65db3b57187a`，最终完成；以下 resume 仅记录恢复方式，本次不再执行，成功安装后任务 staging 已清理：

```powershell
.venv/Scripts/python.exe -B -X utf8 .agents/skills/paper-parser/scripts/mineru_precision.py resume 2aff5a7d-1792-4ab1-b8cc-65db3b57187a --workspace .scratch/focus-v02-stage0/workspace --timeout 40 --poll-interval 5
```

## 真实样例结果

Parser 返回 `ok=true/status=done/source_id=DeepStack-paper`。Bundle 的 `validation.json` 为 `ok=true`，原件一致、正文非空、元数据可解析、图片引用可定位、图片命名连续均通过，计 30 个标题、27 张图片。额外直接逐字节比较原 PDF 与 Bundle 内 `source.pdf` 一致。语义阅读顺序、核心图表和公式仍待原文抽查，结构校验不代表内容质量完全通过。

样例 Source 仅有 `source.yaml` 与 `parser-bundle/`，无 reading/Plan；Cursor 的 Plan/Chunk 均为空，证明现有 Parser 注册可不创建 Plan，尚不证明新版 Inbox／Application 已实现。

使用现有 SourceLibrary.attach 将同一 Source 加入两个隔离样例 Topic，并重复添加第二个 Topic：最终仍为 1 个 Source，每个 Topic 恰有 1 个相同 Source 引用；Bundle 文件清单和逐文件摘要前后相同，无 Plan 目录。此检查无远端调用。隔离证据为 `.scratch/focus-v02-stage0/evidence/topic-reuse.json`，只证明现有本地关系复用行为，不代表新版 Host 失败恢复或事务验收。

## 旧资产保护范围

只读检查目录和元数据结构，未读取正文或备注内容：`workspace/` 有 1 个 Source、1 个 Topic、4 个 uploads 条目、0 个 parser-tasks；Source 保存 HTML 原件、Bundle、Plan 和 Records。当前 Plan/Chunk 引用为空，但仍有一套历史 Plan 目录与 40 个 record JSON，不能沿当前游标推断可删除资产。

Source 元数据含 identity、short_name、source_id、source_kind、source_url、title；Topic 含 description、sources、title、topic_id。未发现显式 schema/version 字段。`.focus-runtime/workspace/` 另有 agent、parser、SQLite 与 WAL/SHM、settings 等运行资产。

迁移前停机，整体备份原 workspace、实际 Host 数据与运行目录，在独立位置检查文件清单、内容完整性及旧版打开能力。不能仅复制 SQLite 主文件而忽略活动 WAL；本次尚未执行备份，也未宣称数据恢复已验证。
