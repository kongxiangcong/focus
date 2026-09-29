# FOCUS 用户手册

FOCUS 运行在你自己的电脑或服务器上。浏览器是操作入口；PDF 解析、模型调用、知识库和会话数据都由运行 Python Host 的机器负责。

## 1. 部署

需要 Python 3.10+、Node.js 20.19+ 或 22.12+、pnpm。克隆仓库后，在仓库根目录执行：

```bash
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r host/requirements.txt
pnpm install --frozen-lockfile
pnpm reader:build
cp .env.example .env             # Windows PowerShell: Copy-Item .env.example .env
python -m host --workspace ./knowledge-base --network
```

打开 `http://127.0.0.1:8765`。Host 默认只监听本机；浏览器在另一台机器上时，需要自行配置受信任的网络入口，并设置 `FOCUS_HOST_TOKEN` 和 `FOCUS_PUBLIC_ORIGIN`。详细启动参数见 `python -m host --help`。

`.env` 留在仓库根目录，按需填写：

```dotenv
MINERU_API_TOKEN=你的_mineru.net_Token
DEEPSEEK_API_KEY=你的_DeepSeek_API_Key
```

本地 MinerU 4.0.8 Standard V1 可用时不需要 `MINERU_API_TOKEN`。Host 默认先检测本机 `http://127.0.0.1:18765` 的 MinerU；本地确实不可用时，才使用已配置的 mineru.net 精准解析 API。这里的“本机”指 **Host 所在机器**，与访问网页的 Windows 电脑无关。只用 Codex 时不需要 DeepSeek Key；Codex 需要 Host 系统用户已有的 ChatGPT / Codex 登录。`.env` 被 Git 忽略，不要把真实密钥写入 `.env.example` 或提交到仓库。

## 2. 选择后端

打开网页的“设置”，选 Codex 或 DeepSeek，在下拉框选模型，点击该后端的“连接检查”。FOCUS 会按需准备所选后端的依赖，再用所选模型发起一个最小请求，成功后自动保存并启用。检查会产生一次真实模型调用；没有成功时不会切换后端。首次使用 Codex，可在设置页点击“登录 Codex”，打开浏览器授权，等待页面确认登录成功后再执行连接检查；首次使用 DeepSeek，先填写 `.env` 中的 `DEEPSEEK_API_KEY`。连接检查只证明该模型请求成功，不能替代完整阅读链路验收。

## 3. 阅读与记录

1. 在“资料库”上传 PDF 或 SingleFile 保存的 HTML，选择专题，点击“开始解析并生成博客”。PDF 自动按服务器环境选择 MinerU；HTML 在本地解析。
2. 打开一篇来源，在阅读页查看原文、译文和博客；直接提问可围绕当前内容讨论。
3. 点击“继续阅读”才会推进到下一段。普通追问不会移动阅读位置。
4. 需要留下结论时，请在对话中明确要求保存为 Note。刷新或重启 Host 后，可继续使用已有知识库和对话。

`knowledge-base/` 保存来源、正文、博客和阅读记录；Host data 保存会话。备份时两者都要保留，继续原来的 Codex 会话还要保留运行时自己的用户目录。更完整的本地验收步骤见 [网页 Agent 启动与验收](FOCUS_Web_Agent_Quickstart.md)。
