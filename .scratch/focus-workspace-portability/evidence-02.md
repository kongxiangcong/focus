# 02 验收证据（2026-10-06）

状态：resolved。后端完整初始化按票内边界由 03 接入；没有发行包验收。

- Host／进程：`test_workspace_binding`、复制后批次继续测试、正常启动测试共 9 项通过（39.136s，tmp/workspace-portability/ticket02-final.txt）。
- 首次无配置不取得写者、不建库；新建／导入／重启／原库重新定位、相同 ID 副本实例隔离、配置落盘失败保持原库、HTTP 旧请求拒绝和活动任务切换拒绝均通过。
- 完整恢复：含 Source 原始材料、Topic、Blog、Plan、译文、Notes、Cursor、讨论／摘要／时间线的真实持久化合成库，停机完整复制到中文新位置并隐藏原目录；全新机器配置原地导入。逐项比较逻辑资产和资源字节，继续阅读、提问与保存笔记、新增解析及 Blog 批次通过。恢复不会重新解析已发布来源。
- 未完成业务：暂停后的两项批次停机复制到新位置，原目录隐藏；继续剩余步骤、同一请求重复继续幂等通过。远端受理未知保持 status_check_required，恢复后 Parser 零调用。
- 项目移动：复制实际 Host/Core、方法和构建后 UI 到中文／空格项目路径，在其他 cwd 的真实进程打开外部既有工作区，保留身份及 Topic；缺失可选 Runtime 不妨碍页面读取。
- 浏览器：实际 Chrome、390px 窄屏，首次页无默认库、目录选择取消及手动输入、非法导入留草稿、新建中文／空格路径、设置取消、两个页面换库旧页暂停、旧 HTTP 请求拒绝、完整复制导入同一身份新实例、刷新直达、失效路径重新定位原库全部通过。`tests/workspace_binding_browser.py` 返回 0；结果、截图和逐步记录在 tmp/workspace-portability/workspace-binding-{results.json,trace.txt,png}。
- 目录选择取消用 Host 返回取消的受控替身；手动路径、实际文件系统绑定和浏览器流程真实。未宣称自动化点击了原生选择器。
- Node Windows fs.cpSync 出现原生退出码 3221226505；验收改用 Python shutil.copytree 完整复制，不影响产品。浏览器关页产生 WinError10054 连接关闭日志，不是业务验收失败。
- 类型检查和 UI build 通过。README 已更新普通无库启动、项目资源定位、停机整库复制与原地导入说明。

基线失败与第 01 张票记录相同；最终全量测试及双轴审查由 03 完成。尚未运行真实双 Backend，不以本票替身证据声称真实 Runtime 通过。

最终审查与 03 补充：切库请求携带独立 binding generation，延迟旧草稿及其 Backend 配置在创建目标前拒绝；只读损坏预检保证失败导入目录字节不变；原库关闭失败回滚机器绑定与配置。HTTP、实际 Chrome 旧切库 POST、新格式进程重启与 WAL 恢复均复验通过。真实双 Backend 的复制恢复与剩余阅读推进已在 03 完成，独立证据见 [evidence-03.md](evidence-03.md)。
