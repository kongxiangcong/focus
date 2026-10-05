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

在仓库根目录新建 **`.env`**，按需填写这两个值，空着的可以保留：

```dotenv
MINERU_API_TOKEN=
DEEPSEEK_API_KEY=
```

- **PDF 解析**：后端默认先检查它所在机器的本地 MinerU（`http://127.0.0.1:18765`，4.0.8 Standard V1）。本地服务可用时，`MINERU_API_TOKEN` 留空；没有本地 MinerU 时，填入 mineru.net 的 Token，使用远端精准解析 API。浏览器所在电脑的 MinerU 不参与选择。
- **模型**：使用 DeepSeek 时填写 `DEEPSEEK_API_KEY`；使用 Codex 时在网页设置页点击“登录 Codex”完成授权，不需要 DeepSeek Key。`.env` 只保存在本机，已被 Git 忽略，不要提交密钥。

启动网页后端：

```bash
python -m host --network
```

浏览器打开 <http://127.0.0.1:8765>。首次进入选择运行 Host 这台电脑上的父目录，新建可改名的 `knowledge-base`；已有新格式工作区可原地导入。路径手动输入与本机目录选择器均可使用。没有保存位置时不会自动建库；正常重启直接打开已选工作区，位置失效时可重新定位原库。设置页可在任务结束后更换工作区。Host 默认只允许本机访问。

首次默认 Codex 和“使用默认模型”，可以改选 DeepSeek。连接检查和模型选择均可跳过，直接进入不会安装依赖、登录或调用模型。显式检查或首次使用 AI 时才准备所选 Backend 的缺失依赖，优先复用已有 SDK 配套 Runtime；明确指定的失效路径不会自动替换。连接检查先用 Host 发布规则的默认模型执行无业务工具的最小推理，通过后读取真实模型目录。清单加载失败可单独重试；更换模型不会自动推理，检查成功只验证本次模型请求。

两个 Backend 各自记住默认／手选模型偏好，跨工作区共用。设置页的“保存并应用”在空闲时一次保存并启用，不要求另行刷新，也不强制检查或推理；有活动任务时服务端拒绝切换。API 密钥等配置可在项目目录的 `.env` 文件中填写；Codex 使用已有登录，未登录时主动点击“登录 Codex”。工作区路径和 Backend／模型选项由应用另存到机器用户设置文件，不放在 `.env` 或工作区备份中。Windows 默认设置位置为 `%LOCALAPPDATA%/FOCUS/settings.json`，可用 `FOCUS_SETTINGS_FILE` 指定独立机器配置。

来源、专题、Blog、阅读内容、笔记、进度、讨论和业务断点均保存在这个完整工作区。备份时退出所有持有该库的 FOCUS 进程，等待落盘，再复制整个目录；恢复目录到新位置后使用“导入工作区”。不要运行中单独复制数据库主文件。机器配置和 Runtime 登录独立保存，不需要另找 Host 历史来恢复讨论。旧格式目录会被拒绝，本轮不提供迁移。

项目与工作区可以放在不同位置。方法、UI、解析资源和 `.env` 按项目实际位置定位，终端当前目录不作为数据根；移动项目后需在新位置准备基础依赖，虚拟环境不保证直接搬动。沿用以上项目部署方式，不提供独立 Windows 发行包。

## 最小使用例子

1. 在“知识库”点击“上传”，选一篇 `paper.pdf`，创建专题“端侧 NPU”，点击“开始解析并生成博客”。
2. 打开这篇来源，在阅读页提问“这篇论文的核心机制是什么？”；问题不会推进阅读位置。
3. 点击“继续阅读”进入下一段；需要保留结论时，在对话里说“把刚才的结论保存为一条笔记”。

开发或排查解析流程时使用 [Skills 与 Python CLI 调试说明](docs/FOCUS_Debug_CLI.md)；日常阅读无需这些命令。
