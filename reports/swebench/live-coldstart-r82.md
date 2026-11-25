# round-82 环境适配表 + depth-1 产品化：cfn-lint = f2p_passed、conan = unresolved

## 结论先行

- **cfn-lint-3764 = f2p_passed**（F2P 2/2、3 编辑 / 2 865 B 补丁、判分
  83.797 s）——gate-r80 批次第 2 数据点；**零反馈口径累计 4/11**（旧
  批次 2/7 + 新批次 2/4 判：briefcase、cfn-lint 过，conan 未过；部分
  口径单列不冒充 resolved，r68 契约）。
- **conan-17102 = unresolved**（F2P 1 节点未过、4 编辑 / 2 220 B、判分
  29.828 s）——真实失败数据点（修复面 = build_order 求解器行为，未收敛）。
- **depth-1 单提交救援产品化**（`live-sample.py` `_depth1_rescue`）：
  full clone / fetch 双失败后自动救援；契约 +2（本地 bare 仓 file://
  正反两例，离线）；契约 538→540。
- **环境适配 9 条最终态**：健康基线 3（briefcase r81 + cfn-lint/conan
  本轮）；**env_blocked 4**（sh: fcntl Unix-only；arviz: 旧 matplotlib
  无 py3.12 轮；beancount: C 扩展无轮；aiogram: 2.x TestClient 下标
  语法 py3.12 运行时 TypeError）；blocked_data 1（beets：test_patch
  修改型且基线 0 失败信号，无 F2P 可判）；blocked_source 1（checkov：
  GitHub 连接持续不通，降级原因已记录）。

## 执行面

- 适配方法（round-82 沉淀）：**窄化 test_cmds 到 test-patch 目标文件**
  （f2p-only 口径下绕开全仓收集的环境噪声）+ **setup_cmds 逐仓配方**
  （基线日志缺什么装什么：cfn-lint +defusedxml、beets +requests/mock、
  conan +mock/PyJWT/parameterized/webtest/bottle、aiogram +pymongo/
  pytest-aiohttp/redis）。conan 经 2 轮迭代取绿。
- **flash 空内容流为间歇性、任务相关**：首轮 cfn-lint/conan 双双被
  空白响应废掉（17 s/99 s，0 编辑），重试即正常（337 s/3 编辑、
  261 s/4 编辑）。与 r79 literal-strings 形态一致；对策 = 重试即过
  （空内容按可重试失败已内建）。**跑次纪律**：0 编辑 fast-done 先查
  task-meta history 的空白响应占比，占比高则重试一次再下结论。
- **PYTHONPATH 前置修正**（编码循环测试反馈保真）：基线 venv 的
  editable 安装指向基线 worktree；编码 worktree 跑内测须把
  `repo;repo/src` 前置到 PYTHONPATH，否则循环内测试测的是旧代码。
  judge 侧不受影响（live-sample 自建 venv 重装）。
- aiogram 排查链（如实）：pymongo → redis → 最终 TypeError（py3.12
  运行时），非依赖可修。

## 结果表（gate-r80 批次累计）

| 实例 | 状态 | 数据 |
|---|---|---|
| briefcase-2075 | **f2p_passed** | r81；F2P 13/13、1 编辑/582 B |
| cfn-lint-3764 | **f2p_passed** | 本轮；F2P 2/2、3 编辑/2 865 B |
| conan-17102 | unresolved | 本轮；F2P 1 节点未过 |
| aiogram-1594 | env_blocked | py3.12 typing 运行时不兼容 |
| sh-744 | env_blocked | fcntl Unix-only |
| arviz-2413 | env_blocked | 旧 matplotlib 无 py3.12 轮 |
| beancount-931 | env_blocked | C 扩展无轮 |
| beets-5457 | blocked_data | 基线无失败信号 |
| checkov-6893 | blocked_source | 网络持续不通 |

## 限制

- n=2 本轮新数据点；f2p_passed ≠ resolved（P2P 未判，f2p-only 口径）。
- flash（测试用 key）跑次 4 次（2 废 + 2 成）；空内容流间歇性使跑次
  效率折半——正经扩面前建议换 deepseek-chat 档端点。
- conan unresolved 未做归因深挖（修复面为求解器行为，预算内收束）。

## 证据

- 跑次与判分：`reports/_work/live-r82/`（runs、judge、baseline、
  notes、适配脚本——gitignored 工作区）
- 契约 +2：`tests/test_live_sample.py::TestDepth1Rescue`
- gate 语料：`datasets/swebench/live/gate-r80-batch.jsonl`（cfn-lint/
  conan F2P 基线实测回填；adaptation_note 全量记录 blocked 依据）
