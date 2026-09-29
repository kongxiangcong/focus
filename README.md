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
python -m host --workspace ./knowledge-base --network
```

浏览器打开 <http://127.0.0.1:8765>。在“设置”中选择 Codex 或 DeepSeek、选择模型并点击“连接检查”；它会准备缺失的后端依赖，并发送一次最小模型请求，成功后自动应用。Host 默认只允许本机访问。知识库保存在 `knowledge-base/`，会话保存在单独的 Host data 目录；重装或搬迁时两者都要备份。

## 最小使用例子

1. 在“知识库”点击“上传”，选一篇 `paper.pdf`，创建专题“端侧 NPU”，点击“开始解析并生成博客”。
2. 打开这篇来源，在阅读页提问“这篇论文的核心机制是什么？”；问题不会推进阅读位置。
3. 点击“继续阅读”进入下一段；需要保留结论时，在对话里说“把刚才的结论保存为一条笔记”。

开发或排查解析流程时使用 [Skills 与 Python CLI 调试说明](docs/FOCUS_Debug_CLI.md)；日常阅读无需这些命令。
