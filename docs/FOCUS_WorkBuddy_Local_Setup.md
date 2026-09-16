# 国内 WorkBuddy 本地助理：接入前置配置

用户已选择：网页驱动本机国内 WorkBuddy；目前没有开放平台应用。
本文件是配置准备，不代表已实现或已通过授权。CodeBuddy SDK/CLI 登录不能替代这条路线。

## 应用注册草稿

进入 [WorkBuddy 开放平台](https://open.workbuddy.cn/)，按
[第三方应用指引](https://open.workbuddy.cn/docs/third-party-app)注册应用：

- 名称建议：FOCUS 私人阅读工作台。
- 用途：本人从 FOCUS 网页向本人 PC 的 WorkBuddy 本地助理发送阅读任务并查看回复。
- 权限：`user.localassistant.readable`、`user.localassistant.invokable`。
- 回调规划：`https://<你的FOCUS域名>/reader/workbuddy/callback`。这是待实现的回调，当前 Host 没有该路由；不要把示例域名提交为实际配置。
- 本地开发若需 loopback 回调，先核实平台是否允许 `http://127.0.0.1:8765/reader/workbuddy/callback`；未从当前文档确认可用，不能假定支持。
- 审核/启用后取得 client_id、client_secret；secret 仅配置在服务端私有环境，不要粘贴到聊天或前端。

注册涉及平台账号、应用归属及服务协议，需要用户自行完成；本次未替用户创建或提交应用。

## 实施时的固定边界

使用 `www.workbuddy.cn/openapi/v2/authorize` / `token`，校验随机 state、绑定会话与精确回调地址，
只在后台换取/刷新 token。浏览器只能得到连接状态，不能收到 client_secret 或 refresh_token。
按官方本地助理接口检查在线状态、发送消息并增量读取历史；不读取或导出桌面私有登录 token。

本地助理官方材料尚不能完整确认网页端停止、审批回传、单任务终态与 Focus 自定义工具注入。
尤其中文/英文文档对 permission_response 的说明不一致。拿到应用后须先做隔离试验验证，
不能将“停止轮询”写成“停止后台任务”，也不能将回复到达写成任务完成。
读取 Focus 原文与写入 Notes/Plan/Cursor 仍须走受约束的 Core 工具；不能让远端 Agent 直接改状态文件。

官方依据：[Open API](https://open.workbuddy.cn/docs/openapi)。云端 ACP 的能力不能直接套到本地助理 API。
