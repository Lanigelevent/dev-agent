# round-60 评审闭环（4.4）样例集实跑

判据：差异率 = (external_only + self_only) / union；差异率 > 阈值或存在高严重度发现 → NEED_HUMAN（转人工）。

本次 8 例：PASS 4 / NEED_HUMAN 4，与预期一致 8/8。

结论口径：
- 干净补丁（round-59 真实修复补丁 ×2 + 本次纯净补丁）全部 PASS，他评无新增发现（差异率 0）；
- 植入缺陷补丁全部 NEED_HUMAN（ruff F401/E711、ast-grep console.log/var/空 catch/宽松相等）；
- 语法错误一例两臂**一致命中**（差异率 0）仍被高严重度门阻断——差异率不是放行的唯一条件；
- threshold-probe 证明判定由差异率数字驱动（同一缺陷补丁抬阈值即放行），阈值是显式参数而非常量。

局限（不夸大）：
- OCR 只跑 `delegate preview` 取文件覆盖（本仓库无 LLM 端点，`ocr review/scan` 未跑，不得当作 OCR 的完整评审）；
- Go 补丁无规则覆盖（ruff/ast-grep 对 .go 跳过），该例的 PASS 只等于「自评无发现」；
- 自评臂是作者侧机械核验（补丁结构/语法树/测试），不是第二个人；他评命中而自评无对应发现时差异率必然为 1.0，默认阈值 0.5 因此偏保守（fail-closed）。

端到端接管（code-task --review）见 `run-gate-bench.py` 与 `gate-bench.json`。

| 样例 | 预期 | 判定 | 差异率 | matched/union | 自评/他评条数 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| clean-ts | PASS | PASS | 0.0 | 0/0 | 0/0 | round-59 真实修复补丁；ocr 只作文件覆盖 |
| clean-go | PASS | PASS | 0.0 | 0/0 | 0/0 | Go 无规则覆盖（ruff/astgrep 均跳过）——覆盖率缺口如实记录 |
| clean-py | PASS | PASS | 0.0 | 0/0 | 0/0 | 本次纯净补丁（新增 mean） |
| seeded-py | NEED_HUMAN | NEED_HUMAN | 1.0 | 0/2 | 0/2 | 植入未用导入 + == None；ruff F401/E711 命中 |
| seeded-ts | NEED_HUMAN | NEED_HUMAN | 1.0 | 0/6 | 0/6 | 植入 console.log/var/空 catch/宽松相等；ast-grep 命中 |
| syntax-py | NEED_HUMAN | NEED_HUMAN | 0.0 | 1/1 | 1/1 | 两臂一致命中语法错误——差异率低但高严重度仍阻断 |
| threshold-probe | PASS | PASS | 1.0 | 0/2 | 0/2 | 同缺陷补丁抬阈值到 1.01 → 放行；证明判定由差异率数字驱动 |
| cmd-reviewer | NEED_HUMAN | NEED_HUMAN | 1.0 | 0/3 | 0/3 | 第三方命令评审器接入并计入他评（自评无对应发现） |

OCR 可执行：<repo>\reports\_work\tooling\ocr\node_modules\.bin\ocr.cmd

每个样例的完整 review.json 在 cases/<id>/ 下，可复算。
