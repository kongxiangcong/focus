# 02: 用临时来源替换文本探针

**What to build:** 让连接检测直接验证所选实际模型能读回 FOCUS 提供的原文。

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] 每次在独立临时来源放入新随机标记，只开放 focus 的 read_range 动作；提示词不含标记。
- [x] Host 同时观察到本次读取成功且最终回复带回正确标记才通过；验证纯文本、错误标记、调用成功却未返回正确标记均失败。
- [x] 普通检测只报告一个通过或失败结果；不激活配置、不访问用户文章，移除旧 FOCUS_OK 探针。

## Comments

测试覆盖纯文本、错误标记和完整临时原文往返，并用真实 Codex 和 DSH 复核。 [验收记录](../acceptance.md)
