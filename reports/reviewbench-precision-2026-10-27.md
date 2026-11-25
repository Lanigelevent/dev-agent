# ReviewBench 首份精度报告（2026-10-27，round-36）

语料：ReviewBench 12 例 Python PR（MIT，署名保留；golden 标注 tp×introduced-by-pr），
样本级双指标口径与 forward-bench judge 一致：recall=hits/valid_samples、
precision=grounded/claimed；gt<2 标识符的 weak 样本剔除分母（本轮 weak=1）。
命中判定：finding 文本提到 >=2 个 gt 标识符（>=6 字符、剔关键词、剔注释行）。

| 评审器 | recall | precision | claimed | grounded | valid | weak | findings 总数 |
|---|---|---|---|---|---|---|---|
| deterministic（38 硬规则） | 0.3636 | 0.6667 | 6 | 4 | 11 | 1 | 56 |
| host（宿主 LLM，本会话模型） | 0.8182 | 0.7500 | 12 | 9 | 11 | 1 | 39 |

## 逐样本对照（hit=样本级命中）

| 样本 | det claimed | det hit | host claimed | host hit |
|---|---|---|---|---|
| AA-Factory_aafactory-prototype_17-a1978cb7 | False | False | True | True |
| DisciplinedSoftware_Codebase-Conversion_1-4b | True | True | True | True |
| Hermione-Granger-1176_artifacts_24-5d880a71 | True | True | True | True |
| gagneurlab_PROTRIDER_10-b462b109 | False | False | True | True |
| github_copilot-sdk_1049-4f18d31b | True | True | True | True |
| gtronset_tablo-legacy-m3u_30-051c9cf3 | False | False | True | True |
| jenreh_appkit_48-0c634d30 | True | False | True | True |
| kutanti_litmusai_67-48e73983 | True | False | True | True |
| melroyanthony_healthstream-rag_34-a1d2b3e0 | False | None | True | None |
| pacnpal_callis_3-27a4c218 | True | True | True | False |
| resplab_leap_48-fced0644 | False | False | True | False |
| shartma2_TTP_v2_33-e249f90f | False | False | True | True |

## 如实声明的局限

- n=12 属小样本，数字不作能力上限宣称；golden 标注本身来自上游 LLM 评审（ tp/fp 人工复核口径），存在同源偏差风险。
- host 材料按脱敏后 8000 字符截断：两个大 diff 样本（Codebase-Conversion 173KB、artifacts 1MB）只可见前段，recall 受材料截断面限制，不是模型能力上限。
- host=本会话模型临时替代（宿主文件协议，无 API key），无法保证与线上模型分布一致；样本级命中判定对『提到正确标识符但语义错误』的发现会误计为命中（precision 偏乐观）。
- deterministic 的 0.6667 precision 好于 61 样本真实语料的 0.5，口径不同（样本级 vs 样本级+语料密度），不可直接跨语料比较。

## 复现命令

```
python skills/eval-harness/scripts/reviewbench-eval.py prepare --corpus datasets/reviewbench --out reports/_work/reviewbench-eval
python skills/eval-harness/scripts/reviewbench-eval.py run --corpus datasets/reviewbench --out reports/_work/reviewbench-eval
python skills/eval-harness/scripts/reviewbench-eval.py judge --findings reports/_work/reviewbench-eval/findings.json --prepared reports/_work/reviewbench-eval/manifest.json
CRA_LLM_PROVIDER=host python skills/eval-harness/scripts/reviewbench-eval.py run --corpus datasets/reviewbench --out reports/_work/reviewbench-eval-host --reviewer host
python skills/eval-harness/scripts/reviewbench-eval.py judge --findings reports/_work/reviewbench-eval-host/findings.json --prepared reports/_work/reviewbench-eval/manifest.json
```