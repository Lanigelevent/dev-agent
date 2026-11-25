# round-72 判分链修复 ×2 + PENDING 指针结构改造：可信链 3/9→4/9

日期：2026-10-31 ｜ 版本：v1.73.0 ｜ 状态：**haystack/pvlib gold f2p_passed（链修复成功）；reflex 深因=自身 compat 层 bug 如实保留；冷启动 #5 候选就位（pvlib，2 文件/3 hunks/13 行）**

## 结论

1. **判分链修复 ×2（gold 先行验证驱动）**：
   - **haystack-8489**：test_tracing 缺 `ddtrace`（补）→ 次缺
     `opentelemetry.sdk`（补 opentelemetry-sdk/api）→ gold f2p_passed
     （F2P 4/4，26.9 s）。
   - **pvlib-2249**：仓库 pyproject 的 `testpaths` 为字符串、pytest ≥8
     拒绝 → 按仓库时代钉 `pytest~=7.4`（首版 `pytest<8` 的 `<` 被 Windows
     shell 当重定向吞掉——shell 安全写法修正）→ gold f2p_passed
     （F2P 7/7，20.6 s）。
   - 可信判分链 **3/9→4/9**（conan/keras/haystack/pvlib）；pvlib 成为
     下一个冷启动候选（修复面 2 文件/3 hunks/13 行，全语料现役最小）。
2. **PENDING 指针结构改造（stale-id 对策升级）**：code-task 的
   WAIT_HOST_LLM 每跳覆写 `out_dir/llm-tasks/PENDING` 指针文件
   （prompt/response 绝对路径），宿主只需读一个稳定文件、不再凭记忆
   复用 id（本会话六次实踩的对策闭环）；输出 note 增显式警告；
   既有 WAIT_HOST 契约内嵌指针断言（契约 530 不变）。
3. **reflex 深因定性**：pydantic 钉 2.7.4 后 `pydantic_v1_patch` 仍崩
   （RuntimeError: generator didn't stop after throw()）——reflex 自身
   compat 层在本机栈（Windows × py3.12.13）的 bug，非依赖版本问题；
   blocked_env 如实保留，判分链侧不再追。

## 1. 判分链修复明细（累计）

| 实例 | 根因 | 修复 | gold 复验 |
| --- | --- | --- | --- |
| keras-20389 | conftest 缺 tensorflow | + tensorflow-cpu（r71） | f2p_passed（F2P 1/1） |
| haystack-8489 | 缺 ddtrace → 缺 opentelemetry.sdk | + ddtrace + opentelemetry-sdk/api（r72） | f2p_passed（F2P 4/4，26.9 s） |
| pvlib-2249 | pyproject testpaths 字符串 × pytest≥8 | + pytest~=7.4（r72，shell 安全修正） | f2p_passed（F2P 7/7，20.6 s） |
| reflex-4087 | reflex 自身 compat 层 bug | 不在判分链侧追 | blocked_env |
| instructlab-2526 | 包要求 Python <3.12 | 不硬凑 | blocked_python |

任务级适配记录在各自 gate-r68-*.jsonl 的 adaptation_note。

## 2. 对 D-045 路线的影响

- 冷启动候选面：pvlib（13 行）与 haystack（45 行）就位——round-73 首选
  **pvlib**（全语料现役最小修复面，且 F2P 7 条全为 test_patch 新增型的
  gold 先行验证已通过、链可信）。
- gold 先行验证三轮兑现价值（r70 拦坏链 / r71 修后取信 / r72 连修两条），
  「扩样前 gold 必跑」前置检查成立且已代码化于流程。
- 零反馈 vs 带反馈对照（r71 立）等待 pvlib 数据点扩样。

## 3. 证据与复跑

```
# gold 复验
.venv/Scripts/python.exe skills/eval-harness/scripts/live-sample.py \
  --tasks datasets/swebench/live/gate-r68-pvlib-python.jsonl --mode gold --f2p-only \
  --out datasets/swebench/live-runs-r72 --source-root datasets/swe-repos --no-network --force
# （haystack 同型，gate-r68-haystack.jsonl）
```

判分台账 `datasets/swebench/live-runs-r72/live-sample-ledger.json`；
任务文件 `datasets/swebench/live/gate-r68-{pvlib-python,haystack}.jsonl`
（adaptation_note 全记录）。

## 4. 边界（不宣称的部分）

- gold f2p_passed 只证「判分链可信 + gold 有效」，不折算 agent 能力。
- pvlib/haystack 的 P2P 大头含上游截断 id，完整 resolved 不可得（f2p-only
  部分口径）。
- PENDING 指针只解「宿主写错 id」，不解决宿主探索策略（首轮全函数覆盖）
  ——后者留给下一个冷启动跑实证。
