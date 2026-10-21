# 验证环境与可复现边界

- 基线：PR #24 / feat/article-structure-guide / 9f183cd。没有真实 Knowledge Base。
- `pnpm install --frozen-lockfile`；Python `.venv` 使用 `python -m venv --system-site-packages .venv`。
- Playwright 位于 `/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright`。
- 标准 Playwright Chromium 下载包损坏；在 `/tmp/focus-browser-runtime` 通过 npm 安装 @sparticuz/chromium 153.0.0，解压包内 chromium.br 至 `/tmp/focus-chromium`。未改变项目依赖。
- Chromium 153.0.8010.0；使用 `--no-sandbox --no-zygote`，只运行隔离合成 Host。
- 为避免 Linux 没有 CJK 系统字体造成界面方框，将仓库已有 neo-zhisong-screen.ttf 复制到 /tmp/focus-fonts，并用 FONTCONFIG_FILE=/tmp/focus-fonts/fonts.conf 指定系统回退字体；没有改产品字体。
- `run_fixture.py` 使用现有 confirmed_ux_browser.py 的合成数据副本和真实 Host。仅在测试进程里省略 test_focus_read 对已删除 CLI 的导入，默认通过 Host 显式进入正文；FOCUS_BROWSER_LEGACY_INTRO=1 为旧脚本准备确定性的合成 Article Overview。
- `run_legacy_tests.py` 只用于诊断旧 fixture，**不是**规范 unittest 命令的通过证据；基线及本次版本都失败。
- 所有浏览器测试必须把 Host 和 Node 子进程放在同一执行命令的网络环境。模板：

```bash
FONTCONFIG_FILE=/tmp/focus-fonts/fonts.conf \
FOCUS_BROWSER_FIGURES=1 FOCUS_BROWSER_PORT=18778 \
FOCUS_PLAYWRIGHT_MODULE=/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright \
FOCUS_CHROMIUM_EXECUTABLE=/tmp/focus-chromium \
FOCUS_BROWSER_SCRIPT=tests/reading_width_browser.mjs \
FOCUS_BROWSER_OUTPUT=.scratch/reader-usability-audit/evidence/03 \
.venv/bin/python .scratch/reader-usability-audit/validation/run_fixture.py
```

真实数据验证尚未执行。需要实际 Knowledge Base 后按用户指定 cp -a 到 /tmp，只用新隔离 Host 的访问口令；合成数据通过不替代该门禁。
