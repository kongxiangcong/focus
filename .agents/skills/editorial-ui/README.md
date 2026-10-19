# editorial-ui · 1.1.0

面向内容型界面、经授权的产品 UI 全面重构，以及自包含交互式 HTML 的 Agent skill。
保留业务契约；普通修改保留现有视觉，明确授权的重构则执行用户选定的新设计规范。
它不是 Claude 皮肤包，也不是 FOCUS 专用组件库。

## 本次升级

- Integrate 增加 `visual_policy: preserve / redesign`，避免把“保留业务”误解成“不能换旧界面”。
- 增加本地参考库审查：版本、工作树、文件摘要、冲突裁决、来源与声明区分；`external/` 默认只读、非运行时依赖。
- 产品选定规范和产品代码拥有视觉/动效参数；技能 JSON 只控制附带的默认 HTML，不强迫覆盖产品参数。
- 全面重构按“小状态板 → 最小基础组件 → 真实核心路径 → 其他页面 → 完整验收”推进；必做项延期不等于变可选。
- 新增只读 `audit_reference.py` 及测试；补充动效中断、阅读定位/流式跟随、全屏浮层和证据边界。

附带的 3 个 HTML、CSS/JS 源码和数值配置与 1.0.0 完全相同，不借修改开发流程悄悄替换模板外观。

## 安装或升级

复制整个 `editorial-ui` 文件夹，不要只复制 SKILL.md。更新已有安装时替换原位置，不要留下两份同名技能。先备份旧目录，备份必须放在技能扫描目录之外。无需 API Key、MCP 或远程安装器。

Codex 本地路径与显式调用依据官方文档核对（2026-10-17）：
- 个人：`~/.agents/skills/editorial-ui/`
- 仓库：`<repo>/.agents/skills/editorial-ui/`
- 在 Codex CLI/IDE 使用 `$editorial-ui`，必要时通过 `/skills` 检查；更新未显示时重启会话。

来源：https://developers.openai.com/codex/skills （重定向 https://learn.chatgpt.com/docs/build-skills）。Codex 的 `agents/openai.yaml` 保留 `allow_implicit_invocation: false`；SKILL frontmatter 同时保留支持该字段的运行时显式调用扩展。本次没有在用户的 Codex/其他 Agent 中安装实测。

已有 Claude Code/Cursor 安装可更新原安装位置；1.0.0 文档中的路径核对日期为 2026-10-16，本次未重新核对这些产品。通用 skill 目录结构见 https://agentskills.io/specification （2026-10-17）。

### Linux / macOS：升级现有 Codex 个人安装

在解压后的 `editorial-ui` 上一级运行。目标不存在时也可安装。若以前用的是仓库安装，将 `dest` 改为那个实际路径，不要另装一份个人副本。

```bash
set -eu
src="$(pwd)/editorial-ui"
dest="$HOME/.agents/skills/editorial-ui"
backup="$HOME/.editorial-ui-backups/editorial-ui-$(date +%Y%m%d-%H%M%S)-$$"
test -f "$src/SKILL.md" || { echo '当前目录没有完整的新技能'; exit 1; }
test "$src" != "$dest" || { echo '请从解压目录运行'; exit 1; }
mkdir -p "$(dirname "$dest")" "$(dirname "$backup")"
if [ -e "$dest" ] || [ -L "$dest" ]; then mv "$dest" "$backup"; fi
if ! cp -R "$src" "$dest"; then
  echo "复制失败；请检查部分目标，并从 $backup 恢复旧目录。"
  exit 1
fi
```

### Windows PowerShell：升级现有 Codex 个人安装

```powershell
$src = (Resolve-Path '.\editorial-ui').Path
$dest = Join-Path $HOME '.agents/skills/editorial-ui'
$backups = Join-Path $HOME '.editorial-ui-backups'
$backup = Join-Path $backups ('editorial-ui-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $PID)
if (!(Test-Path (Join-Path $src 'SKILL.md'))) { throw '缺少完整新技能' }
if ($src -eq $dest) { throw '请从解压目录运行' }
New-Item -ItemType Directory -Path (Split-Path $dest), $backups -Force | Out-Null
if (Test-Path $dest) { Move-Item -LiteralPath $dest -Destination $backup -ErrorAction Stop }
try { Copy-Item -LiteralPath $src -Destination $dest -Recurse -ErrorAction Stop }
catch { throw "复制失败。旧副本如存在则位于 $backup；检查部分目标后恢复。$_" }
```

这两段是给用户本地执行的指引，本次没有替用户执行安装。自定义修改先与新版 diff/合并，勿盲目覆盖。

## 调用示例

### 普通修补：保持现有设计
```text
$editorial-ui
只修复当前阅读页在全屏状态下的资料弹窗。
Integrate / visual_policy=preserve；保留主题、布局和业务行为。
检查真实代码、焦点、中文输入和回归测试，不做整站改版。
```

### 全面重构：采用选定的新规范
```text
$editorial-ui
按项目中的 UI_DESIGN_SPEC.md 和 UI_IMPLEMENTATION_BRIEF.md 改造真实界面。
Integrate / visual_policy=redesign。允许替换旧视觉，保留业务契约。
参考项目已放在 external/example，仅作只读设计与实现参考。
先核对实际目录、版本和差异，参数以产品规范为准。
最小状态板校准后立即完成真实核心页面路径，再迁移其他页面。
不要只交付方案或独立演示；不要自动提交、推送或部署。
```

### 新交互 HTML
```text
$editorial-ui
将所附分析做成可离线打开的单文件 HTML。
支持实际筛选、细节查看和导出；示例数据明确标注。
不依赖 npm、CDN 或后端。实现并验证，不只给设计建议。
```

FOCUS 专属执行文档与设计分析应放在 FOCUS 项目中，不能写成这个通用技能的强制默认值。

## 目录与按需使用

`SKILL.md` 是入口；`references/product-redesign.md` 管重构；`references/reference-adoption.md` 管参考库；其他规范管视觉、动效、交互和验收。
`assets/design-tokens.json` 与 `assets/motion-presets.json` 只维护附带模板的默认数值。现有产品使用自身唯一参数来源。
`assets/starters/reader.html`、`flow-explorer.html`、`report.html` 为独立的原生 HTML 示例；回答与架构数据均为明确标注的模拟，不连接模型。

参考库快照示例（文件列表须对应真实存在路径）：
```bash
python <skill-root>/scripts/audit_reference.py --reference external/example --files README.md LICENSE package.json
```
输出为 JSON；可重定向到项目进度目录。仅记录指定文件和 VCS 元数据，不执行代码、访问网络或修改参考库。普通拷贝目录不会被误标为父仓库的 commit。

## 验证与证据

在技能目录执行：
```bash
python scripts/build_starters.py --check
python scripts/validate_skill.py
python -m unittest discover -s tests -p 'test_*.py'
python scripts/check_offline.py assets/starters/reader.html
```
这些脚本使用 Python 3.10+ 标准库。可选浏览器脚本需要已获准安装的 Playwright/Chromium：
```bash
python scripts/browser_smoke.py --out ./validation-local
```
它默认测试 file://；受管理浏览器禁止该入口时，可用 `--transport inline` 测同一内联内容并将直开标为未测，不修改浏览器安全策略。

本轮真实结果见 `validation/REPORT.md`。1.0.0 旧报告移至 `history/1.0.0/validation/REPORT.md`，不算本轮测试。结构/单元/模板浏览器测试不是 Agent 生成质量评测，也不是 FOCUS 验收。

## 来源

历史上游参考基线为 `Caho1/open-claude-ui@02d021fceaf2a907f9e63a8125621bdda1b85d60`。新版没有审查用户机器里的 external 项目，实际使用时必须就地核验。见 `references/provenance.md`、`THIRD_PARTY_NOTICES.md` 与 `licenses/`。没有打包上游整库、字体文件、专有音频或品牌图标，不声称官方还原或法律认证。
