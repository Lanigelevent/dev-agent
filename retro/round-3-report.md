# 复盘轮报 round-3

open 14 / closed 2

## 分类统计

- 手工：13
- 误报：2
- 行为回归：1

## 未结坑明细

| ID | 类别 | 坑 | 根因 | 对策 | 来源 |
|---|---|---|---|---|---|
| 5fc9903b1f38 | 误报 | LLM 评审材料（step4 material）未脱敏：prompt 文件里 password= 字面量明文可见，违反硬 | material 直接取自 ctx[diff] 原文，只有 finding 级  | 下一轮把 material 过 redact() 再进 prompt（llm/p | retro\events-round-phase01.json |
| 7ec6fce89ac0 | 误报 | requests 的 pickle 命中是方向伪影（修复新增的代码形态被记为抓住 bug） | run-samples 正向 diff 扫修复后代码 | 方向契约测试（TestRealCorpusChain）永久锁定；失败案例 8b2 | retro\events-round-fixdir.json |
| 07cf8ce1f8cc | 手工 | fix-apply 文档字符串与 SKILL.md 提及其他脚本的旗标拼写，被 doc-drift 参数漂移误判 | 不知道 doc-drift 会把同现脚本名与 --flag 的行当参数断言 | 写文档时散文体不出现 --旗标 拼写，git 旗标改文字描述 | retro\events-round-baseline.json |
| 2ae5d49858cb | 手工 | GitHub 直连被重置（Connection was reset），真实语料克隆改走 Gitee 镜像 | 网络环境对 github.com 的限制 | 真实语料策展统一走 Gitee 镜像 mirrors/<repo>，逐仓验证可用 | retro\events-round-realcorpus.json |
| 6016972afe29 | 手工 | 中途 resume 历史缺陷：产物摘要形状≠内存形状（step2_collect.json 的 files 是计数，内存 | 断点只存展示用产物，从未有中途续跑的真实用例 | resume-state.json 形状保真回灌（v1.15.0 已修）；教训： | retro\events-round-phase01.json |
| 8bad50975bae | 手工 | Windows 下 py 打印 CRLF 行尾，bash 反引号取 ID 带  导致按 ID 查找失败 | py print 输出 
 与 bash 分词冲突 | 脚本提取 ID 后必须 strip()，或改用文件传递 | retro\events-round-org.json |
| 906e6e6d01d9 | 手工 | host 协议每维度各一问（提示词含维度名），首轮测试假设单轮填答错 | 协议设计时未写明征询粒度 | SKILL.md 已写明可能多次 WAIT/续跑；测试改循环填答（上限 8） | retro\events-round-phase01.json |
| 9d93e1705cb6 | 手工 | 调研称 Ruff 有 Python API（ruff.lint），实测 pip 包只有 find_ruff_bin——无 | 二手资料未实测 | 引擎接入前先在 .venv 实测 API 面（已确认走 subprocess+J | retro\events-round-phase01.json |
| a8c51e998c03 | 手工 | 评测窗口 12→36 个月经两人规则变更（提案 retro/批准 director），collect 验证 19→30 | - | 行为级配置变更沿用 _governance 式留痕：提案、批准、验证三件齐全 | retro\events-round-realcorpus.json |
| aceff6563e08 | 手工 | collect-samples --limit 0 语义是第一个样本即 break 而非不限 | 哨兵值 0 与「不限」语义冲突（len>=0 恒真） | 全量采集传显式大数；哨兵值语义在 docstring 里写清 | retro\events-round-realcorpus.json |
| b67f26397fe9 | 手工 | gitee.com/mirrors/jinja2 镜像不存在，克隆失败要求认证 | 并非所有上游仓库都有官方 Gitee 镜像 | 策展阶段逐仓验证；失败仓进入失败案例双轨 | retro\events-round-realcorpus.json |
| d086f638b262 | 手工 | Edit 工具做纯空行微调时误删 def 行尾换行，def 与函数体合并成语法错误 | old_string 含尾换行的小编辑风险 | 无实质变更不提交编辑；插入方法用带上下文的完整块 | retro\events-round-phase01.json |
| d2c22ec68c70 | 手工 | 测试 fixture 的测试文件未提交导致工作树脏，闸门守卫把行为回归测试用例本身拦下 | 五道闸前置条件与测试夹具准备顺序冲突 | 凡进五道闸链路的夹具先提交再送审 | retro\events-round-baseline.json |
| d8c4b419a461 | 手工 | urllib3 的 cred-password 命中因 snippet 脱敏丢失第二个 gt 标识符而无法 ground | 脱敏（产品红线）与判分标识符重合的固有张力 | 接受该折衷并在报告局限声明；不为指标好看而放宽脱敏 | retro\events-round-fixdir.json |

## 改进候选（按 权重×数量 排序）

- **手工：12 个未结坑** — 纳入下一轮改进候选，明确责任与验收口径
- **误报：2 个未结坑** — 为该模式补阴性样例并入经验库，必要时收紧规则形态
