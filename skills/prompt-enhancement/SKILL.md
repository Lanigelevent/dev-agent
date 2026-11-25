---
name: prompt-enhancement
description: 从用户原话解析评审对象、范围、深度档与 A/B/C 意图分级，C 级强制追问。也用于口语说法：用户这句话到底想审什么
---

# prompt-enhancement — 意图解析与澄清

## 目的与边界

把用户的自然语言请求机械解析为评审对象、范围、深度档与意图分级，
供派发、定档与材料构造消费。只做可机械判定的部分；
语义层面的「用户到底想要什么」由 A/B/C 分级兜底，C 级必须追问。

边界约定：

- 解析判据全部是显式关键词/模式，不做脑补；判据本身写进依据（rationale）。
- 对象无法确定或请求自相矛盾 → C 级，退出码 3，禁止擅自开审。
- 输出 questions 最多 1 条，问最关键的那件事。

## 何时用 / 何时不用

用：主流程步骤 1，一切评审的开头。
不用：纯脚本化调用（上游已给出 sha/范围）时可跳过，但要在运行信息里注明跳过原因。

## 脚本与用法

### intent-parse.py

```bash
python skills/prompt-enhancement/scripts/intent-parse.py --request "review PR #12, 快速看下"
python skills/prompt-enhancement/scripts/intent-parse.py --request "评审最近的改动" --repo /path/repo
```

- 输入：`--request`（必填，用户原话）、`--repo`（可选，B 级默认对象用）。
- 输出：`intent_level`（A/B/C）、`object`（提交/范围/PR/整个仓库/未知）、
  `object_ref`、`scope`、`depth`、`rationale[]`、`questions[]`。

## 判级规则

A级（对象明确，可开审）：

- 命中 PR 编号（`PR #12`、`#12`）。
- 命中提交标识（7–40 位十六进制 sha、`HEAD`、`HEAD~n`）。
- 命中分支引用（`分支 xxx` / `branch xxx`）。
- 命中范围（`A..B`）且无整个仓库表述。
- 命中「整个仓库/全部代码」。

B级（对象可默认，需在运行信息注明）：

- 请求无对象表述，但给了 `--repo` → 默认评审整个仓库。

C级（退出码 3，必须追问）：

- 对象无法确定（无对象表述且无 --repo）。
- 请求自相矛盾（同时命中快速与深入档关键词）。

## 深度档判据

| 档位 | 关键词 |
| --- | --- |
| quick | 快速、大概、粗略、大致、quick |
| deep | 仔细、全面、深入、详细、thorough、deep |
| standard | 未命中以上关键词 |

quick 与 deep 同时命中 → 自相矛盾，C 级退出 3。

## 范围提取

- 请求中出现的源码路径（`*.py` 等后缀形态）进 scope 列表。
- 无路径 → scope = 全部改动。
- scope 只描述「用户点名的文件」，实际评审范围仍以取数结果为准。

## 对象优先级

同一请求命中多个对象时，按 PR > 分支 > 范围 > 提交 > 整个仓库 取最后命中的强信号，
rationale 里逐条列出全部命中证据，供人工复核判级是否合理。

## 与主流程的接入点

| 主流程 | 用法 |
| --- | --- |
| 步骤 1 | intent-parse 输出写入运行信息；C 级先追问再继续 |
| 步骤 4 | depth 传给 dispatch/材料深度；scope 收窄取数范围 |
| 步骤 10 | intent_level 与 questions 落入报告口径段 |

## 消费注意

1. B 级不是免检：默认对象要在报告口径里显式写出，用户可事后纠正。
2. rationale 是判级依据，不许删；人工改判必须保留原判与理由。
3. 本脚本不做仓库访问；--repo 只判存在性（是否传入），不做任何 git 调用。
4. sha 正则可能把长十六进制单词误判为提交；rationale 会列出原文，人工可纠正。

## 退出码汇总

| 退出码 | 含义 |
| --- | --- |
| 0 | 可开审（A/B 级） |
| 3 | 需追问（C 级） |
| 2 | 参数错误（缺 --request） |

## 检查清单

1. A/B/C 三级判据与 BASELINE.md 一致。
2. C 级必须带 questions，且最多 1 条。
3. 深度档关键词冲突必须判 C，不得静默取一方。
4. rationale 保留全部命中证据。
5. scope 里的路径必须是请求原文出现过的。
6. 本脚本零 git 调用、零文件写入。
7. assumptions 每条必须有 basis 与 risk_if_wrong；confirmations 由其生成，
   不得出现「没有依据的待确认项」。

## 输出字段说明

| 字段 | 说明 |
| --- | --- |
| intent_level | A=对象明确；B=默认对象；C=需追问 |
| object | 提交/范围/PR/整个仓库/未知 |
| object_ref | sha/分支名/PR 号；无则 null |
| scope | 请求点名的文件列表或「全部改动」 |
| depth | quick/standard/deep；C 级矛盾时为 null |
| rationale | 全部命中证据，人工复核判级用 |
| questions | C 级追问，最多 1 条 |
| ambiguity | 多解读清单：有信号但被裁决掉的（dimension/readings/chosen/rule） |
| assumptions | 采用的假设（assumption/basis/risk_if_wrong），至多 4 条 |
| confirmations | 非阻塞待确认项，由假设生成，至多 3 条 |

## 三键分工：ambiguity / assumptions / confirmations（2026-10-26 新增）

模糊意图不猜着执行的机制化：三种信息分三条通道，不许混装。

- **ambiguity** = 「有信号但被裁决掉的」：同一维度多个对象信号命中、快深矛盾、
  scope 多文件。chosen 写明按哪条规则裁决（对象按优先级），落选信号保留
  readings 供人工复核。矛盾（depth）时 chosen=null 且阻塞。
- **assumptions** = 「我猜的」：B 级默认对象、深度档缺省 standard、scope 缺省
  全部改动。每条必须带 basis（依据）与 risk_if_wrong（错了的代价）。
- **confirmations** = 非阻塞待确认项：由 assumptions 机械生成（假设+依据+代价
  拼成一句话），用户可逐条确认或纠正；不回答不阻塞，但汇总时原样带回。
- 分工纪律：阻塞追问走 questions（≤1 + 退出码 3），非阻塞走 confirmations；
  调用方拿到 confirmations 必须在报告口径段列出，不得静默吞掉。

## C 级追问话术

- 对象缺失：请提供评审对象（sha/分支/PR 号/仓库路径）。
- 矛盾：请求同时要求快速与深入，请确认深度档。
- 追问后重跑本脚本；questions 不进报告正文，只进运行信息。

## 上游集成注意

- 调用方拿到退出码 3 必须终止流程，不得跳过追问。
- intent_level=B 时报告口径段必须写明「默认对象，可事后纠正」。
- 深度档 quick 不等于省略核验，只降低材料窗口与路数。
- scope 中的文件若不在取数结果里，按「用户点名但无变更」记录。
- 本脚本输出不落盘，编排层负责写入运行信息。
