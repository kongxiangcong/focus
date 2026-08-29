# FOCUS Phase 2 DSH Integration Contract

> 状态：Design boundary
> 前置：Phase 1 Source Library、Topic Reading 与 Topic Synthesis 已实现
> 非目标：迁移旧原型数据、兼容旧 schema、复制 Workspace 权威

## 1. 保持不变的产品语义

DSH adapter 必须投影现有深模块接口，而不是建立第二套领域状态：

- `sources/` 是唯一 Source Library；每份 Bundle、Plan、Record 和 Notes 只保存一次。
- `topic.yaml.sources` 是唯一 membership 权威并保持顺序。
- `state.json` 只保存 current Source、可选 current Topic 与 per-Source Plan/Chunk Cursor。
- Continue Reading 是唯一 Cursor move，并可在完成当前 Source 后进入 Topic 的下一 Source。
- Topic Synthesis 是显式派生产物，每条 claim 必须有 Source ID 与 Source Anchor。
- 宿主 Session 保存原始对话；FOCUS 不创建聊天 archive 或第二会话模型。

## 2. Adapter 与权限

DSH 可将五个公开 Skills 映射为工具，但不得暴露内部 MinerU task lifecycle、Bundle staging、Short Name/Source ID allocation 或 focus-map draft transport。Parser 调用中用户选择 URL 或文件即授权该次 MinerU 获取/上传，不再进行二次确认。

MinerU Token 只存在于部署 Secret。签名 URL 只经进程 stdin 传输。错误保持 typed：credential、network、publisher access、MinerU task、timeout 与 Bundle validation 不合并为成功，也不触发替代抓取。

## 3. 私人数据与部署

以下都属于私人数据：原始 PDF/HTML、Parser Bundle、Blog Output、Reading Plans、translation、Notes、state.json、Topic manifests 与 Synthesis。部署应将一个 Workspace 挂载为单一受控目录，并限制 adapter 只访问该目录。

Phase 2 可以增加部署级身份、Secret 注入、备份和单写者执行保证，但不能把这些机制写回 Phase 1 schema。任何多写者协议、远程同步或共享权限模型都需要独立 ADR。

## 4. 不做旧数据迁移

本次切换明确不迁移旧 Workspace，也不读取旧 `papers/`、Topic 双写、临时 draft、旧 Cursor 或会话产物。DSH 从当前 Source Library schema 创建新 Workspace；不存在 wrapper、alias、fallback reader、双读双写或 conversion job。

## 5. Acceptance

DSH integration 完成前必须分别验证：

1. Source 可零 Topic 注册、后续加入多个 Topic，资产无复制；
2. Parser 调用无二次授权，失败直接且不绕过访问控制；
3. Title/Short Name/Source ID/Task ID 分离，重复 identity 复用；
4. focus-map stdin transport 不产生用户可见 draft 或 receipt；
5. Topic Reading 跨 Source 恢复只依赖 current_topic_id 与 per-Source Cursor；
6. Topic 搜索有界，Synthesis claims 均可回到 Source Anchor；
7. Secrets、真实来源和私人 Workspace 资产不进入 Git、日志或模型可见错误体。
