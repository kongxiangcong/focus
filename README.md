# FOCUS

FOCUS 是一个在本机运行的论文阅读网页：上传 PDF 或 SingleFile HTML，按专题整理来源，生成阅读内容和博客，在同一页面提问、继续阅读并保存笔记。浏览器是日常使用入口；解析、模型调用和文件存储都在运行 FOCUS 后端的机器上完成。

## 本地部署

准备 Python 3.10+、Node.js 20.19+ 或 22.12+、pnpm。从仓库根目录执行：

```bash
git clone https://github.com/kongxiangcong/focus.git
cd focus
python -m venv .venv
source .venv/bin/activate       # Windows PowerShell 用 .\.venv\Scripts\Activate.ps1
python -m pip install -r host/requirements.txt
pnpm install --frozen-lockfile
pnpm reader:build
```

在仓库根目录按需新建 **`.env`**：

```dotenv
MINERU_API_TOKEN=
DEEPSEEK_API_KEY=
```

- **PDF 解析**：后端默认先检查它所在机器的本地 MinerU（`http://127.0.0.1:18765`，4.2.3 Standard Tasks V1）。本地服务可用时，`MINERU_API_TOKEN` 留空；没有本地 MinerU 时，填入 mineru.net 的 Token，使用远端精准解析 API。浏览器所在电脑的 MinerU 不参与选择。
  在后端机器的独立 Python 3.11–3.14 环境运行 `python -m pip install "mineru==4.2.3"`，再用 `mineru-api --host 127.0.0.1 --port 18765 --tier standard` 启动服务。首次解析需准备 Standard 模型。升级前先完成旧服务中尚在运行的任务；已提交的任务绑定原服务和协议。
- **模型**使用运行 Host 的电脑上已经安装的 CLI。Codex 复用本机 ChatGPT 登录，可在网页设置页发起或取消授权。DeepSeek 使用 `dsh --profile acp`。已有 DeepSeek 凭据文件路径和模型偏好会保留，也可在设置中指定包含 `DEEPSEEK_API_KEY` 的文件。`.env` 保存在本机，已被 Git 忽略。

启动网页后端：

```bash
python -m host --network
```

浏览器打开 <http://127.0.0.1:8765>。首次进入选择运行 Host 这台电脑上的父目录，新建可改名的 `knowledge-base`；已有新格式工作区可原地导入。路径手动输入与本机目录选择器均可使用。没有保存位置时不会自动建库；正常重启直接打开已选工作区，位置失效时可重新定位原库。设置页可在任务结束后更换工作区。Host 默认只允许本机访问。

首次可直接进入知识库，在需要 AI 时从设置选择 Backend。内置预置包括 Codex、DeepSeek、Antigravity CLI 和 Cursor CLI。扫描只读取配置并查找本机可执行文件。设置支持重新扫描、填写已安装程序的路径、加载模型清单和手动输入模型。连接检查会让实际选中的模型通过 FOCUS 工具读取一段临时原文，模型清单加载与这项验证分别运行。首次发送时，如配置尚未通过验证，FOCUS 先检测，通过后自动继续原请求。

“保存并应用”会复用匹配的检测回执，或先检测再切换。前台任务运行时暂缓切换。Backend 和模型偏好在同一个 Host 的工作区之间共用。Windows 默认设置位置为 `%LOCALAPPDATA%/FOCUS/settings.json`，可用 `FOCUS_SETTINGS_FILE` 指定独立配置。自定义 Backend 的 JSON Manifest 放在实际设置文件同级的 `backends/` 目录，也可指定其他目录。

```bash
python -m host --backend codex --model gpt-6-astra
python -m host --backend codex --backend-bin /path/to/codex
python -m host --backends-dir /path/to/backends --check-runtime
```

`--backend`、`--backend-bin`、`--model` 和 `--backends-dir` 优先于 `FOCUS_BACKEND`、`FOCUS_BACKEND_BIN`、`FOCUS_MODEL` 和 `FOCUS_BACKENDS_DIR`。命令行和环境变量只影响本次 Host 进程，跨工作区有效。设置页的“保存并应用”是持久化入口。启动指定的 Backend 或路径无效时仍可使用知识库，AI 操作会指出需要修正的配置。`--check-runtime` 只报告本机路径，可用 `--backend` 指定要检查的条目。

来源、专题、Blog、阅读内容、笔记、进度、讨论和业务断点均保存在这个完整工作区。备份时退出所有持有该库的 FOCUS 进程，等待落盘，再复制整个目录；恢复目录到新位置后使用“导入工作区”。不要运行中单独复制数据库主文件。机器配置和 Runtime 登录独立保存，不需要另找 Host 历史来恢复讨论。旧格式目录会被拒绝，本轮不提供迁移。

项目与工作区可以放在不同位置。方法、UI、解析资源和 `.env` 按项目实际位置定位，终端当前目录不作为数据根；移动项目后需在新位置准备基础依赖，虚拟环境不保证直接搬动。沿用以上项目部署方式，不提供独立 Windows 发行包。

## 外观与阅读设置

在“设置 → 外观与阅读”中，可调整主题（跟随系统／浅色／深色）、低动态、界面密度、字号和正文字体。字号会显示当前数值，字体预览可用于确认阅读效果。

修改即时预览；点击“保存外观”后，刷新页面仍会保留，点击“还原外观”则恢复上次保存的值。这些偏好保存在当前浏览器中，不随工作区备份或跨设备同步，也不会更改后端配置；后端的“保存并应用”是独立操作。阅读页点击“宽幅”展开横向滑杆，实时调整段落宽度；中点“标准”为 1040px，可点击恢复。宽度自动保存在当前浏览器，空间不足时自动适配。

## 最小使用例子

1. 在“知识库”点击“上传”，选一篇 `paper.pdf`，创建专题“端侧 NPU”，点击“开始解析并生成博客”。
2. 打开这篇来源，在阅读页提问“这篇论文的核心机制是什么？”；问题不会推进阅读位置。
3. 点击“继续”进入下一段；需要保留结论时，在对话里说“把刚才的结论保存为一条笔记”。

讨论可以读取当前绑定论文或文章的原文。所选 Backend 支持联网搜索时，也可提问“结合论文原文，搜索官方代码，解释这个调度策略如何实现。”阅读进度和笔记由 FOCUS 管理。

开发或排查解析流程时使用 [Skills 与 Python CLI 调试说明](docs/FOCUS_Debug_CLI.md)；日常阅读无需这些命令。

## 文章结构与导读

知识库的列表和卡片都提供“文章结构”，与“带读博客”并列。点击可独立预览
“文章标题 → 中文文章骨架 → 文章导读”；关闭后保留筛选和滚动位置。
首次正式阅读使用同一份内容，点击“进入正文”后沿用原有阅读流程。
已经开始阅读的文章不会重置，可从阅读位置菜单打开“文章结构总览”。

未准备的文章可直接在预览中点击“准备文章结构”，失败后可重试。新文章复用
现有阅读准备任务，可能需要等待全文准备；两处同时请求不会启动重复任务。
旧文章按需补齐导读，不批量覆盖已有段落、译文、笔记或进度。
原文或计划变化时旧导读不会继续作为当前版本展示；旧版原文计划需先按既有流程重新准备并启用。

## 项目结构

源码目录、生成物与本地数据的边界，以及文档入口见 [项目目录结构](docs/project-structure.md)。
