# DSH 专用 attempt Session 采用终止、释放与归档

阶段 2D 在固定 DSH `0.1.7-rc.2` / `477b4f4` 上，为每个 AI attempt 创建独立的原生 Session。attempt 到达成功、失败、取消或中断终态后，Host 必须先确认执行已终止并释放 live handle，再通过 DSH 公开能力归档该 Session。归档后的 DSH 日志仍保存在 DSH 自有持久层中；FOCUS 不宣称日志已永久删除，也不直接操作 DSH 私有存储。业务结果与归档结果分别报告：归档失败不回滚已提交资产，但必须显示“归档未完成”，保留最小关联并在下次启动重试。旧 attempt 一旦失去提交资格，归档是否成功都不能恢复提交资格。

## Considered Options

- 继续要求永久删除：被否决。固定基准的公共 `SessionPersistence` 没有删除能力，实际持久化探针也证明 close／dispose 后日志仍存在；这会让阶段 2D 永久停在框架能力之外。
- 直接删除 JSONL 或修改 DSH 内核：被否决。两者依赖私有实现并扩大了 FOCUS 集成边界，无法作为受支持的 Host 能力。
- 只停止或释放 handle，不归档：被否决。它不能给用户稳定、可查询的终态，也没有可重试的清理回执。

## Consequences

- 阶段 2D 的清理出口改为“执行终止、资源释放、Session 归档”三项分别可核验；归档失败可见且可重试。
- FOCUS 仅保存版本、业务 attempt、Session 关联、工具权限、校验／提交及停止／释放／归档回执等最小验收信息；DSH 自己保留的 Session 日志不复制进 FOCUS，但也不描述为已删除。
- 打开知识库不创建 Session；重试仍创建新 attempt 和新 Session；归档 Session 只作为历史记录，不是业务状态权威。
- 若未来固定 DSH 基准提供受支持的永久删除 API，可另行决策是否升级清理策略；本 ADR 不预先承诺迁移或补删历史 Session。
