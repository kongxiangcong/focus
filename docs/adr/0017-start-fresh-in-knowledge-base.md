---
status: accepted
---

# Start fresh in knowledge-base instead of migrating old data

2026-09-26 阶段 5 grill Q17、Q19 确认 FOCUS 从空知识库重新开始，新的数据根目录命名为 `knowledge-base/`，不再使用 `workspace/`。旧 Source、Topic、Bundle、Blog、Notes、Plan、译文和阅读进度全部不迁移；需要的文章由用户重新上传，以取消旧布局映射和未知备注意图处理的复杂度。

此决定替代总计划 P3 和阶段 5 的旧数据迁移、dry-run、旧资产完整性比对与迁移回退交付，也替代 ADR 0008／0009 对本次新发布沿用旧目录数据的要求。旧目录暂不参与新版运行；不自动导入、回退读取或双写，实际旧数据的移动与删除不属于这次需求整理。初始化、配置默认值和启动说明应统一使用 `knowledge-base/`；已存在的新知识库在重启时保留数据，不被自动清空。

Core／Application 单一资产权威、单写者约束和正常失败恢复不变。阶段 6 继续验证兼容新 schema 宿主之间对同一知识库的本机停机接管。这是已确认目标，不是路径实现或发布验收声明。
