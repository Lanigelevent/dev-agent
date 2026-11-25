# round-65 评审 precision 护栏：语料 pin 化（D-047）

日期：2026-10-29 ｜ 版本：v1.66.0 ｜ 状态：PASS（真语料）+ 反向三例判红 + 契约测试 6/6

## 结论（决定）

1. **语料仍不入库、CI 不跑**：ReviewBench 语料 `datasets/reviewbench`（含 219 个
   golden、diffs、corpus 全量 10MB 级）继续留在本地/受控目录；发布闸与 CI 都不
   强制跑本门禁——CI 机器没有语料，强制跑只能二选一：伪造 PASS 或常驻 SKIP，
   两者都比「明确不挂」更糟。
2. **基线钉死来源**：`skills/eval-harness/precision-baseline.json` 升到
   `precision-baseline/2`，新增 `corpus` 块：
   - `revision` = `36cc8a8dbce3375c80f58f957a2a2be34681cf49`（本地语料 git HEAD，
     2026-10-26T16:49:16+10:00 的上游提交）；
   - `files` = 本门禁实际读取的 **26 个输入**逐文件 sha256：样本清单
     `samples-py.json` + `corpus/manifest.json` + 12 个选定 `diffs/*.diff` +
     12 个 `golden/*.json`。
3. **先验 pin 再对账**：`precision-gate.py run` 与 `check --corpus` 在评测前校验
   revision 与全部文件 sha256；任一项不符即 **code=2**，不进入判分、不出 PASS。
   不带 `--corpus` 的 `check` 保持旧行为（只对账 judge↔基线），供 CI 形状校验。

## 证据

### 真语料 PASS（pin 26/26）

命令：

```
.venv/Scripts/python.exe skills/eval-harness/scripts/precision-gate.py run \
  --corpus datasets/reviewbench --out reports/_work/precision-r65
```

产物 `run.json`：`ok=true / status=PASS / failed=[]`，
`corpus_pin = {status: PASS, revision: 36cc8a8…, actual_revision: 36cc8a8…,
files_expected: 26, files_verified: 26}`，指标 precision 0.6667 / recall 0.3636 /
valid 11 + weak 1，与 round-62 基线一致；`judge.json` 同目录落盘可复算。

### 反向三例（同一真语料，均 rc=2，不进判分）

| 反向样例 | 扰动 | 结果 |
| --- | --- | --- |
| `reverse-tamper-sha.json` | 基线里 `samples-py.json` 的 sha256 改成全 0 | rc=2「sha256 不匹配: samples-py.json（期望 000…，实得 a163…」 |
| `reverse-wrong-rev.json` | 基线 revision 改成 `1111…` | rc=2「revision 不匹配: 期望 1111… 实得 36cc8a8…」 |
| `reverse-missing-file.json` | 基线钉一个不存在的 `diffs/nonexistent.diff` | rc=2「语料缺文件: diffs/nonexistent.diff」 |

### 契约测试（6/6 绿）

`tests/test_scripts.py::TestPrecisionGate`：原 4 例 + 新增
`test_check_with_corpus_verifies_pin`（合成 git 语料 pin 通过）、
`test_pin_mismatch_is_code2`（改字节 / 换 revision / run 前置拦截三反向），
`test_shipped_baseline_shape` 升到 schema `/2` 并断言 26 个 pin 与 upstream。

## 语料新鲜度说明（如实记录）

- 本地语料是 **浅克隆**，HEAD 停在 `36cc8a8…`（2026-10-26）。
- 2026-10-29 实测上游 HEAD 已前进到 `228f2a8d662c9c1c12d25757e23c52c9a6170d5a`。
- 本轮**不追新**：pin 的意义就是让「0.6667 这个数字」与产生它的那份语料一一对应。
  换语料（`git pull` / 重新生成 `samples-py.json`）必须重跑评测并把新 pin 写回
  基线，否则 run/check --corpus 直接 code=2——这是有意设计，不是缺陷。

## 复跑命令

```
.venv/Scripts/python.exe skills/eval-harness/scripts/precision-gate.py check \
  --judge reports/precision-gate-round65/judge.json --corpus datasets/reviewbench
.venv/Scripts/python.exe -m unittest discover -s tests -p test_scripts.py -k PrecisionGate
```
