# round-94 D-045 扩样真连跑：宿主会话模型轴（n=3 冻结，2 判 + 1 blocked）

## 结论先行

- **批次**：gate-r94 = seaborn-2848 / flask-4045 / requests-1963（三新仓，
  与全部历史评测零重叠——实例级+仓级双排除，选法确定性入 frozen_note）。
- **结果（零反馈单发口径，partial 不折算 resolved）**：
  - **mwaskom__seaborn-2848 = f2p_passed**（F2P 1/1；补丁 +13/−1，单 hunk；
    修法=越界 hue 值映射为全透明 RGBA、保行对齐——facecolors 按原始行
    掩码索引的官方测试语义）。官方口径累计：**零反馈 3/7**（r73 pvlib、
    本轮 2 例；部分口径单列）。
  - **pallets__flask-4045 = f2p_passed**（F2P 2/2；补丁 2 hunk：Blueprint
    __init__ 名含点抛 ValueError + add_url_rule 的 assert 改 ValueError
    ——era 代码用 assert 使 AssertionError 不满足 pytest.raises(ValueError)）。
  - **psf__requests-1963 = env_blocked**（2011 年代 vendored 布局 py2 隐式
    相对导入，py3.12 无法构建；r81/r82 先例 blocked 不补位）。
- **模型轴（诚实登记）**：宿主会话模型（CRA_LLM_PROVIDER=host，总监
  2026-11-07 派工「由你作为后端模型的替代」），host 文件进出协议逐跳
  响应；**不是 deepseek-chat 档单发口径**，n=2 可判不外推；带会话级
  上下文（我作为宿主可读全仓），比 API 端点上下文面更宽——模型轴
  对比时须按「host 会话模型」单独记账。
- **环境适配表（round-94 增补）**：seaborn→mpl==3.8.4/numpy==1.26.4/
  pandas==2.1.4 era pin；flask→werkzeug==2.0.3 等 era pin + pytest==7.4.4
  （era conftest 依赖 _pytest.monkeypatch.notset）+ 判分/loop test-cmd
  加 -p no:warnings（era setup.cfg filterwarnings=error 对 py3.12 弃用
  告警致命）；requests→env_blocked。

## 过程要点（可复算）

1. 选批→冻结→derive（test_cmds 收窄）→gitee 3/3 取源（无降级）→
   prepare（gate-run）→基线体检（seaborn/flask baseline_ok；requests
   env_failed→判 blocked）→逐实例 host 协议编码循环→predictions
   JSONL→live-sample f2p-only 判分。
2. seaborn 循环 3 跳收敛（读测试→读实现→编辑），但环境面三次返工：
   ①loop 的 pytest 在主 .venv 无 era pin→收集失败判红；②v1 修法
   shape mismatch（_hue_map 返回 RGB 3 列）；③v2 用 to_rgba_array
   归一后过；④worktree 相对路径手滑嵌套进 repo（坑入册留观）。
3. flask 循环暴露三层环境纠缠：era conftest 依赖 pytest 旧内部 API
   （钉 7.4.4）、era setup.cfg filterwarnings=error 对 py3.12 致命
   （-p no:warnings）、editable 安装指向（loop 的测试必须指向被编辑
   的 worktree）。三者均入适配表，judge 环境自洽复算通过。
4. derive 产品缺口留观：requests-1963 静态 F2P=0（类上下文解析未覆盖
   其 test_patch 形态），derive 覆写官方 F2P 的行为在 r94 用「官方
   F2P 回填」绕过——derive 不应覆写官方列表（产品修正候选）。

## 口径声明

- f2p_passed 是部分口径：F2P 全过、P2P 未全跑（上游截断缺陷，live-sample
  malformed_node_ids 体检拦截）——**不计 resolved**，与 r81/r82 同口径。
- 模型轴=宿主会话模型（host 协议）；与 r79-82 的 flash/deepseek 端点
  轴不同源，跨轴比较须注明。
- 台账：worktree 相对路径坑（嵌套 worktree）当轮入册留观；其余环境
  问题为 r81/r82 已知形态的复现，对策已固化入适配表。

## 证据

- 批次：datasets/swebench/live/gate-r94-batch.jsonl（+ raw/notes）
- 运行：datasets/swebench/live-runs-r94/（宿主协议 llm-tasks 全留痕）
- 判分：reports/_work/r94/live-sample-ledger.json（baseline+predictions）
- 补丁：live-runs-r94/<iid>/single/out/edits.patch
