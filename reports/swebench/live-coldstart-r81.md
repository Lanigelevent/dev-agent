# round-81 gate-r80 批次真连跑：briefcase-2075 = f2p_passed + 环境适配收束

## 结论先行

- **briefcase-2075 = f2p_passed**（F2P 13/13、1 编辑 / 582 B 补丁 /
  判分 52.734 s）——gate-r80 新批次第 1 个数据点；**零反馈冷启动口径
  2/7**（pvlib r73 + briefcase 本轮；f2p_passed 部分口径单列，不冒充
  resolved——r68 契约）。
- **基线体检 9 条全跑完**：仅 briefcase 基线健康（17 failed / 2976
  passed，F2P = test_permissions_context 参数化 13 节点，基线全败、
  基线实测回填）；其余 8 条为环境依赖类失败（venv 未装仓依赖）或源
  不可达，**环境适配挂账下轮**（setup_cmds 逐仓适配表是结构性工作）。
- **源拉取 8/9**：full-clone 150s 超时不适配大仓 → **depth-1 单提交
  预填缓存法 7/9 一次通过**（r66 验证取法复验有效；conan 重试 1 次
  就位）；checkov 网络持续不通判 **blocked_source**（降级原因记录，
  D-045 四态保留）。
- flash 空内容流前置探测 3/3 正常（r79 形态为任务相关，对策在位）。

## 执行面（协议 v4 + D-048）

- briefcase 跑次：rounds 24 / 1 编辑 / tests fail（部分修复形态）→
  判分 f2p-only 口径经 live-sample predictions 模式（复用官方判分
  管线 + malformed_node_ids 体检）；worktree 从 depth-1 缓存仓开出
  （git worktree 相对路径坑：worktree add 的相对 dest 被解析到缓存
  仓内——绝对路径规避，入册留观）。
- D-048 附录：9 份 notes 生成（文件指针 + 静态 F2P node，checkov 为
  数据驱动用例形态改用数据目录指针）；briefcase 跑次验证附录含指针
  行的编辑引导有效（第 1 数据点即进入编辑行为）。
- F2P 静态推导修正链（round-81 沉淀）：`+++ b/` 路径需容忍
  `arviz/tests/` 型非 tests/ 前缀；类方法需追踪 `+class` 上下文
  （aiogram 型）；参数化 id 需基线实测回填（静态只能到函数级）。

## 8 条挂账明细（round-82 开局接手）

| 实例 | 状态 | 根因 | 下步 |
|---|---|---|---|
| aiogram-1594 | env 缺依赖 | 缺 pymongo 等（setup_cmds 缺位） | 适配 setup_cmds（pip install -e . + 测试依赖） |
| sh-744 | 1 error | 收集错误（依赖缺） | 同上 |
| arviz-2413 | 1 error | matplotlib 版本不匹配 | 同上 + 依赖 pin |
| cfn-lint-3764 | 1 error | formatters 收集错误 | 同上 |
| beancount-931 | env_failed | pip install 失败（编译/版本） | 依赖 pin 或 py 版本 |
| beets-5457 | 66 errors | 插件依赖缺 | 适配 setup_cmds |
| conan-17102 | 370 errors | functional 测试依赖外部工具 | 测试子集选择或 setup_cmds |
| checkov-6893 | blocked_source | GitHub 连接持续不通（降级记录） | gitee 镜像寻找或换网络环境重试 |

- 基线失败集 ≠ F2P：aiogram/sh/arviz/cfn-lint/beets/conan 的 errors
  为环境类（import/依赖），须先修环境再取真 F2P——不得把环境失败冒
  充任务 F2P（口径纪律）。

## 对照面板（D-045 零反馈冷启动，n=8 实例 / 10 跑次）

零反馈 2/7（pvlib、briefcase）+ 协议 v4 数据点 1/1（placement r79）；
失败形态持续指向修复面规模与环境适配。briefcase 为 v4 + D-048 条款
下首个零反馈 f2p_passed，与 pvlib（v3 前协议）同属「单点小修复面 +
指针明确」形态——分界线假设继续一致。

## 限制

- n=1 本轮新数据点（其余 8 条环境适配挂账），不外推成功率。
- flash key（测试用）跑次 1 次；空内容流未复现（3/3 探测 + 跑次
  正常），模型轴单点。
- f2p_passed 不等于 resolved（P2P 未判，上游截断缺陷维持 f2p-only
  口径，r68 契约）。

## 证据

- 跑次与判分：`reports/_work/live-r81/`（runs/briefcase、judge、
  baseline、notes——gitignored 工作区）
- 判分台账：judge/live-sample-ledger.json（f2p_passed 1）
- 协议：D-045 / D-048 / 协议 v4；gate 语料
  `datasets/swebench/live/gate-r80-batch.jsonl`（briefcase F2P 已
  基线实测回填 13 节点）
