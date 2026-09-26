# FOCUS 设置页 Codex 登录调研

日期：2026-09-26。范围：官方文档、本地固定 SDK 类型／源码和 CLI 版本／帮助。未读取认证文件或环境变量值，未发起 OAuth、安装依赖、调用模型或做浏览器验收。

## 结论与接口

用户要求的 Codex 登录可通过现有 App Server 路线接入，不需要改为 OpenAI API Key，也不需要仅为登录重写整个 Backend。官方 Python `openai-codex` SDK 控制本地 App Server，发布包携带固定 CLI Runtime。[Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)

官方账号接口支持如下流程：`account/read` 查询状态；`account/login/start` 以 `type: chatgpt` 返回 `loginId` 与 `authUrl`；客户端打开浏览器，App Server 接收本地回调；通过 `account/login/completed` 与 `account/updated` 获知结果。另有登录取消、退出和设备码流程。应让 Runtime 管理 OAuth，而非让 FOCUS 浏览器页面处理令牌。[App Server authentication](https://learn.chatgpt.com/docs/app-server#auth-endpoints)

Codex 可将凭据保存到系统凭据库或 CODEX_HOME 下的认证文件。[Authentication](https://learn.chatgpt.com/docs/auth#credential-storage) 用户在第三轮 Q14 明确选择直接共用个人 Codex 登录，否决此前独立登录目录的建议。后续需验证固定 Runtime 使用同一认证存储且不继承无关模型／工具配置；不能复制凭据到知识库或另建第二份登录状态。

## 本地版本证据

- `host/requirements.txt` 固定 `openai-codex==0.154.0`；本地 `.venv` 包元数据及配套可执行文件 `--version` 均核实为 `0.154.0`。`login --help` 存在设备码等登录选项。
- `.venv/Lib/site-packages/openai_codex/client.py:441–476` 提供登录、取消、账号查询和退出方法。
- SDK `_login.py:29–45` 使用 `type: chatgpt` 并取得 `loginId/authUrl`，`:117–136` 提供等待与取消；`api.py:118–124` 暴露 `login_chatgpt` 与 `login_chatgpt_device_code`。
- SDK `generated/v2_all.py:2276–2288` 定义浏览器授权 URL，`:6497–6506` 定义完成通知。

因此本次核查的版本已有所需接口，不必预先升级才能设计该流程。接口存在不是授权登录已通过的证据；发布时验证实际使用的 Runtime。第四轮 Q21 已决定 FOCUS 不绑定 Runtime 版本、不设版本门槛；此处 `0.154.0` 只标识历史核查基线，不是产品限制。

## FOCUS 当前差距

- `host/backends/codex.py:37–42` 在打开业务会话时检测 `OPENAI_API_KEY` 并主动 API Key 登录，违背本轮仅使用 Codex 登录的要求。需取消隐式认证切换，并确保所有 Codex 任务使用同一认证政策。
- `host/proxy.py:59–65` 复制进程环境，`host/runtime.py:26–28` 用该环境启动。需验证实际使用的是用户选定的个人 Codex 认证存储；不能仅由某个全局 CLI 已登录推断 FOCUS Runtime 一定已登录。独立认证目录不是目标。
- `host/backends/__init__.py:49–65` 当前预检查验证可执行文件版本，没有完整账号预检查；设置页还缺少登录状态、发起、取消与结果接口。

## 建议产品流程（待收敛）

1. 首次启用只安装两套依赖，不启动登录。用户在设置页选择 Codex 后，Host 通过所选 Runtime／认证目录查询账号。
2. 未登录时显示“登录 Codex”；用户点击后在系统浏览器授权。Host 保持登录进程，页面显示等待、取消或重试入口；打开浏览器不算登录成功。
3. 收到成功通知后重新查询账号，确认是 ChatGPT 登录；显示最小账号状态。认证成功、账号额度可用与任务验收分别判断，不以登录成功承诺所有调用必然成功。
4. 登录过期时给出重新登录入口；不要求用户粘贴令牌，不自动切换 API Key 或 DeepSeek。设备码作为固定版本可验证的备用登录入口，不影响浏览器主路径。
5. 保存 Backend／模型后提示用户刷新页面，Reload 就是刷新；刷新前允许旧配置启动任务，常驻提示依据保存值与生效值的差异显示。运行中刷新不取消任务、不应用配置，任务完成后再刷新；同一 Host 的多个页面共用一份生效配置。

后续验收：干净环境登录、取消／失败、应用重启复用、失效重新登录、错误认证模式拒绝、环境 Key 不覆盖、所有 AI 路径认证一致，以及浏览器授权到真实模型任务的完整流程。本次均未声称完成。
