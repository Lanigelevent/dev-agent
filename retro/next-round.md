# 下一轮开局检查单

> round-240 收官（2026-11-28）：**双仓社区规范化与 README 加强**（v2.105.0 不增版本，测试 **894 不变**、脚本 **93 不变**、工具 **16 不变**）。
> README 四处陈旧引用修正 + 贡献节社区指针；社区五件套落地（CONTRIBUTING/SECURITY/CODE_OF_CONDUCT/PR 模板/issue 模板）；许可决策维持不变（开源授权留总监裁定）。
> light 单跑 267.05 秒。台账 273 / open 6 / closed 243 / archived 24。
> 下一轮（round-241）见第 204 条。
>
> round-239 收官（2026-11-28）：**公开仓同步收尾与存量红面登记**（v2.105.0 不增版本，测试 **894 不变**、脚本 **93 不变**、工具 **16 不变**）。
> 同步完成（内容至 r238、通道 A×3+B×1、smoke 208/208 双证绿）；三修落地（CVE setuptools 日鲜/mcp-scan pwsh bash/interop 规范哈希）；nightly 全量面存量红（环境资产缺失型，早于同步）登记修复候选待 r240 裁定。
> light 单跑 273.76 秒。台账 273 / open 6 / closed 243 / archived 24。
> 下一轮（round-240）见第 203 条。
>
> round-238 收官（2026-11-28）：**公开仓同步 hotfix——自扫描规范哈希**（v2.105.0，测试 **893→894**、脚本 **93 不变**、工具 **16 不变**）。
> 公开仓 CI 六矩阵全红根因=策略哈希对 CRLF 工作树字节（r234 写盘未钉 newline），公开 LF 检出假漂移拒服务；修复=规范形哈希（解码→CRLF→LF），回归测试锁定双形同哈希+篡改必命中。
> 内部双跑后重走导出（含 generic 用户路径脱敏 pass）→ 推送 GitHub → CI 复验。
> full 双跑 248.44/232.99 秒。台账 272 / open 5 / closed 243 / archived 24。
> 下一轮（round-239）见第 202 条。
>
> round-237 收官（2026-11-28）：**三项代裁落笔——阶段 5 收口**（v2.104.0 不增版本，测试 **893 不变**、脚本 **93 不变**、工具 **16 不变**）。
> D-054=方案 C 终局（四依赖条件激活）；依赖刷新第十九跑=不提前（锚点约 r244）；批次四=backlog 维持。裁定实录见 D-054 第 2 条与 reports/dep-refresh-19-proposal-r236.md。本轮零代码。
> light 单跑 317.62 秒（891 passed + 2 skip）。台账 271 / open 4 / closed 243 / archived 24。
> 下一轮（round-238）见第 201 条。
>
> round-236 收官（2026-11-28）：**依赖刷新第十九跑提案——不提前**（v2.104.0 不增版本，测试 **893 不变**、脚本 **93 不变**、工具 **16 不变**）。
> uv 只读探测 11 直接依赖零新增直接漂移（hypothesis 传递升级按先例拒绝）；建议不提前，下一锚点约 r244；提案待总监裁定。本轮零代码。
> light 单跑 232.27 秒（891 passed + 2 skip）。台账 271 / open 4 / closed 243 / archived 24。
> 下一轮（round-237）见第 200 条。
>
> round-235 收官（2026-11-28）：**阶段 5 批次二后半——测试选择器 + 记忆归档臂**（v2.104.0，测试 **884→893**、脚本 **92→93**、工具 **16 不变**）。
> M6 test-select（直接证据+后缀链，空集回退全量；fix-apply auto 档接线，argv 作用域勘误由闸五测试群抓回）+ M8 supersede 归档臂（保留原文，live 过滤进比对与检索）；9 条新契约全绿。
> Q10 参数漂移两连抓（文档措辞纪律）；选择器碰撞由双向契约抓住改后缀链（correction 入账，open 4）。
> full 双跑 230.51/227.83 秒。台账 271 / open 4 / closed 243 / archived 24。
> 下一轮（round-236）见第 199 条。
>
> round-234 收官（2026-11-28）：**阶段 5 批次二前半——PII 出站闸 + 端点降级链**（v2.103.0，测试 **873→884**、脚本 **91→92**、工具 **16 不变**）。
> M7 pii-scan（校验位+熵兜底三层，selftest 反向样例入 CI；selftest 实证抓住 luhn 累加行丢失）+ M5 多端点降级链（SSRF 逐端点复验、降级必记、全灭如实 degraded）；11 条新契约全绿。
> 死代码两红（unused_import + --root 死参数）拆除，Q10 参数漂移门禁抓到；传输损坏 2 处被 selftest/compile 拦于提交前（correction 入账，open 3）。
> full 双跑 244.89/250.94 秒。台账 270 / open 3 / closed 243 / archived 24。
> 下一轮（round-235）见第 198 条。
>
> round-233 收官（2026-11-28）：**阶段 5 批次一 P0 落地**（v2.102.0，测试 **849→873**、脚本 **90→91**、工具 **16 不变**）。
> M1 mcp-selfscan（pin/check/启动比对/CI）+ M4 tools-policy（auto×14/gated×2/fail-closed）+ M2 熔断与统一裁剪 + M3 complete_json 回填重试（D-053 语义锁定）；24 条新契约全绿；CI self-check 增自扫描步。
> 传输损坏对策升级：数据分件装配路径零损坏（1 条 correction 入账）；r232 顺序坑结案（验收=本轮真值行先齐再跑）。
> full 双跑 248.20/239.50 秒（首跑轮 3 红于真值行未齐、次跑 1 红于进程内 argparse 污染；rc 测试改子进程面 + 新测试改 unittest 兼容后双绿，F5 真值 873 对齐）。台账 269 / open 2 / closed 243 / archived 24。
> 下一轮（round-234）见第 197 条。
>
> round-232 收官（2026-11-28）：**开源对标强化计划入册**（v2.101.0 不增版本，测试 **849 不变**、脚本 **90 不变**、工具 **16 不变**）。
> 开源调研（991 项索引 A/B/I 三方向快照）→ 审查报告 W1-W10 → ROADMAP §3.1（10 行对标矩阵）+ §4 G16-G23 + §6 阶段 5（5.1-5.10）+ D-054 提案入册；本轮零代码。
> 编辑链 5 处单字/乱串错误 + 收官首跑红于 PROGRESS 台账行未刷新（预置漂移起跑）双坑如实入册（open 2，对策=python+断言+回读；先真值行后套件）。
> light 单跑 264.06 秒（线内）。台账 268 / open 2 / closed 242 / archived 24。
> 下一轮（round-233）见第 196 条。
>
> round-231 收官（2026-11-26）：**依赖刷新第十八跑裁定——不提前**（v2.101.0 不增版本，测试 **849 不变**、脚本 **90 不变**、工具 **16 不变**）。
> 用户接受提案：11 依赖无直接漂移，维持约 r236 锚点；本轮零代码。
> light 单跑 265.96 秒（线内）。台账 266 / open 0 / closed 242 / archived 24。
> 下一轮（round-232）见第 195 条。
>
> round-230 收官（2026-11-26）：**依赖刷新第十八跑提前提案写案**（v2.101.0 不增版本，测试 **849 不变**、脚本 **90 不变**、工具 **16 不变**）。
> 只读探测 11 依赖无直接漂移，建议不提前、维持锚点约 r236；提案待总监裁定。
> light 单跑 268.94 秒（线内）。台账 266 / open 0 / closed 242 / archived 24。
> 下一轮（round-231）见第 194 条。
>
> round-229 收官（2026-11-26）：**项目体积与缓存终盘**（v2.101.0 不增版本，测试 **849 不变**、脚本 **90 不变**、工具 **16 不变**）。
> 7.07GB 总量，三轮清理释放约 122.4GB；剩余内容全有引用/审计价值，停止清理。
> light 单跑 259.00 秒（线内）。台账 266 / open 0 / closed 242 / archived 24。
> 下一轮（round-230）见第 193 条。
>
> round-228 收官（2026-11-26）：**对外口径与门禁面季度复核**（v2.101.0 不增版本，测试 **849 不变**、脚本 **90 不变**、工具 **16 不变**）。
> gate/日志 sha256/CI 十步全对齐；README/PROGRESS 补回宿主臂 unavailable 口径，数字未改。
> light 单跑 246.89 秒（线内）。台账 266 / open 0 / closed 242 / archived 24。
> 下一轮（round-229）见第 192 条。
>
> round-227 收官（2026-11-26）：**全仓口径与计数季度对账**（v2.101.0 不增版本，测试 **849 不变**、脚本 **90 不变**、工具 **16 不变**）。
> 版本/计数/台账六处一致；修正 PROGRESS 848→849 与 MCP docstring 14→16 两处前向漂移；tag 缺口 v2.98/99 无闸证据属正确行为。
> light 单跑 290.07 秒（线内）。台账 266 / open 0 / closed 242 / archived 24。
> 下一轮（round-228）见第 191 条。
>
> round-226 收官（2026-11-26）：**缓存清理 1.92GB + 依赖刷新第十七跑**（v2.101.0，测试 **849 不变**、脚本 **90 不变**、工具 **16 不变**）。
> 用户裁定两项合并执行：剩余历史缓存清空、清华镜像零降级（拒 pyyaml/packaging 传递升级）、三矩阵零漂移。
> 双跑 259.69 / 250.52 秒（< 540s、< 600s）。台账 266 / open 0 / closed 242 / archived 24。
> 下一轮（round-227）见第 190 条。
>
> round-225 收官（2026-11-26）：**评测口径季度对账**（v2.100.0 不增版本，测试 **849 不变**、脚本 **90 不变**、工具 **16 不变**）。
> 0.42% 复算成立（0.0042 = 3/713、clean 零噪声 97.4%），对外数字与 D-053 因果表述无勘误。
> light 单跑 279.36 秒（线内）。台账 266 / open 0 / closed 242 / archived 24。
> 下一轮（round-226）见第 189 条。
>
> round-224 收官（2026-11-26）：**剩余 datasets 二次盘点**（v2.100.0 不增版本，测试 **849 不变**、脚本 **90 不变**、工具 **16 不变**）。
> 8.99GB 总量，保留镜像/仓库/Pro-work/语料；约 2GB 可清候选待裁定，未删。
> light 单跑 266.08 秒（线内，pid 竞态未再现）。台账 266 / open 0 / closed 242 / archived 24。
> 下一轮（round-225）见第 188 条。
>
> round-223 收官（2026-11-26）：**缓存清理 120.5GB + pid 竞态加固**（v2.100.0，测试 **848→849**、脚本 **90 不变**、工具 **16 不变**）。
> 用户三裁定全落地：删历史评测缓存 / 有界等待 +1 契约（28/28）/ 收官后推送合并 main + v2.100.0 tag。
> 双跑 384.80 / 360.07 秒（< 540s、< 600s）。台账 266 / open 0 / closed 242 / archived 24。
> 下一轮（round-224）见第 187 条。
>
> round-222 收官（2026-11-26）：**冗余备份与无用文件清理**（v2.99.0 不增版本，测试 **848 不变**、脚本 **90 不变**、工具 **16 不变**）。
> 删除约 4.6GB gitignored 临时/缓存；datasets 129GB 保留并给出可清理清单待裁定。
> light 重跑 285.38 秒（首跑 1 例 pid 竞态失败留档）。台账 266 / open 0 / closed 242 / archived 24。
> 下一轮（round-223）见第 186 条。
>
> round-221 收官（2026-11-25）：**维护轮——五检全绿 + 观察项扫描**（v2.99.0 不增版本，测试 **848 不变**、脚本 **90 不变**、工具 **16 不变**；零代码 light，单次 xdist 550.02s）。MCP async 27/27，作业目录 3 cancelled/4 done；CI/CII/key 轮换仍待操作员。台账不变（266 / open 0 / closed 242 / archived 24）。下一轮（round-222）见第 185 条。
>
> round-220 收官（2026-11-25）：**依赖刷新第十六跑——tree-sitter 0.27.0 + coverage 7.17.5**（v2.99.0，测试 **848 不变**、脚本 **90 不变**、工具 **16 不变**；xdist full 双跑 470.29/463.80s + 发布闸六项）。11 个直接依赖三面一致，三矩阵零漂移；拒绝 pyyaml/packaging 非跟踪传递升级。台账不变（266 / open 0 / closed 242 / archived 24）。下一轮（round-221）见第 184 条。
>
> round-219 收官（2026-11-24）：**维护轮——脚本 UTF-8 自防御判据 + 污点测试临时副本隔离**（v2.98.0，测试 **830→848**、脚本 **90 不变**、工具 **16 不变**；full 双跑 557.198/586.742s + 发布闸六项）。S10 真仓 110/110，13 个入口补自防御；坏污点配置只在临时副本注入。台账不变（266 / open 0 / closed 242 / archived 24）。下一轮（round-220）见第 183 条。
>
> round-218 收官（2026-11-27）：**阶段三收官轮——AB-14 沙箱评估 + RouteLLM 读设计**（v2.97.0 不增版本，测试 **830 不变**、脚本 **90 不变**、工具 **16 不变**；零代码 light）。AB-14 评估完成暂不实施（威胁面已覆盖+平台错位，实施条件备档）；RouteLLM 读设计不采纳（零成本+放缓纪律）。**阶段三七项全终局（三落地+三评估+一审计）；吸收列表 27 项+RouteLLM 零悬置，r193 吸收计划三阶段全清**。台账不变（266 / open 0 / closed 242 / archived 24）。下一轮（round-219）见第 182 条。
>
> round-217 收官（2026-11-27）：**阶段三⑤ AB-06 提示优化循环——prompt-optimizer.py 第 90 号脚本**（v2.97.0，测试 **825→830**、脚本 **89→90**、工具 **16 不变**；full 双跑 365.55/350.82s + 发布闸）。三段循环（plan 变体矩阵 21 项→evaluate 协议 blocked 诚实口径→adopt 采纳闸不许降+指纹固化）；DSPy 思想复用读设计不装库 + dead-code 未用导入拦截实证（移除后全绿）。台账不变（266 / open 0 / closed 242 / archived 24）。下一轮（round-218）见第 181 条。
>
> round-216 收官（2026-11-27）：**阶段三④ AB-20 记忆三级管线——memory-pipeline.py 第 89 号脚本**（v2.96.0，测试 **820→825**、脚本 **88→89**、工具 **16 不变**；full 双跑 430.86/447.47s + 发布闸）。三级分工（抽取→合并决策→检索）+ 双臂诚实口径（llm 臂无 key blocked 不写 store）+ namespace 分级（mem0 同型）+ prompt 子命令（doc-drift 死代码拦截实证：未接线函数被机械抓出后补接线）。台账不变（266 / open 0 / closed 242 / archived 24）。下一轮（round-217）见第 180 条。
>
> round-215 收官（2026-11-27）：**阶段三③ AB-16 rail 校验注册表对照审计**（v2.95.0 不增版本，测试 **820 不变**、脚本 **88 不变**、工具 **16 不变**；零代码 light）。on_fail 动作面已标准化（rc 三态 + 结论三态 + 台账去向）；FIX/重试生成有意排除（治理哲学更强：防双记+补丁变动即作废+两人规则）。终局=已对齐零缺口，不吸收。台账不变（266 / open 0 / closed 242 / archived 24）。下一轮（round-216）见第 179 条。
>
> round-214 收官（2026-11-27）：**阶段三② AB-22 rules 注入面——repo-rules-inject.py 第 88 号脚本**（v2.95.0，测试 **816→820**、脚本 **87→88**、工具 **16 不变**；full 双跑 386.73/367.38s + 发布闸）。惯例名发现 6 类 + 有界摘录 + 脱敏复用；配方化第一面审计=已对齐（--style 外部 spec 已存在）。**两坑入册即结**（3fbe8bfb4bc5：裸子进程 GBK 翻红→reconfigure 自防御纪律；kill 测试进程树留真仓夹具损坏态→kill 后 git status 复核纪律）。台账（266 / open 0 / closed 242 / archived 24）。下一轮（round-215）见第 178 条。
>
> round-213 收官（2026-11-27）：**阶段三① AB-10 elicitation 可行性评估**（v2.94.0 不增版本，测试 **816 不变**、脚本 **87 不变**、工具 **16 不变**；零代码 light；总监 2026-11-27 全量批准阶段三）。规范取证走 npmmirror SDK 1.24.0（官方站超时降级记录）；三面判定：批准书载体不采纳（瞬态 vs 批准书持久化=结构性冲突，两人规则不可降级）、防呆面有条件采纳暂缓、URL 批准页不采纳。终局=评估完成暂不实现（验收口径=提案本身）。台账不变（264 / open 0 / closed 240 / archived 24）。下一轮（round-214）见第 176 条。
>
> round-212 收官（2026-11-27）：**阶段二补漏轮——AB-18/05/19 三项终局**（v2.94.0 不增版本，测试 **816 不变**、脚本 **87 不变**、工具 **16 不变**；full 双跑）。AB-18 真实验（新量具 symbol-window-bench.py，n=11 同源语料）：成本比 0.279 + 覆盖率 0.5455（5/11 模块级兜底如实登记）——现役组合取窗比两极端都稳，Serena 不引入；AB-05/19 概念已对齐/有意排除。**吸收列表 27 项对账收口：22 终局 + 6 阶段三待裁决，零漏排**。台账不变（264 / open 0 / closed 240 / archived 24）。下一轮（round-213）见第 175 条。
>
> round-211 收官（2026-11-21）：**维护轮——五检全绿**（v2.94.0 不增版本，测试 **816 不变**、脚本 **87 不变**、工具 **16 不变**）。r210 提交态首个验证轮：freshness/drift/structure/dead-code 四检全绿 + secret-scan 零命中。观察项：①MCP async 家族无新 flaky（第 5 例仍 r204 run2）；②CI nightly mcp-scan 枚举复核待首次 CI 实跑（操作员）；③下一依赖锚点 r220。台账不变（264 / open 0 / closed 240 / archived 24）。下一轮（round-212）见第 174 条。
>
> round-210 收官（2026-11-21）：**依赖刷新第十五跑——ast-grep-py 补丁升级 + venv/lock 双面漂移修复**（v2.94.0，测试 **816 不变**、脚本 **87 不变**、工具 **16 不变**）。逐包探测 11 项仅 ast-grep-py 0.51.2→0.51.3 可升（补 r173 欠账）；新坑入册即结（31f6c8f13828：r173 台账宣称失实升级未落 lock 面 + venv 112 孤儿包清零 + 裸 sync 剥 dev extra + 探针假阴性纪律）；三矩阵零漂移（ruff 973/482/250、astgrep 29/2、libcst ok）；requirements-lock 重导出（--extra dev）；skip 集 2→3（pynguin 孤儿被 sync 移除，LGPL 隔离层测试诚实跳过——pip 模块被剥离同属预期，uv pip 替代）。台账（264 / open 0 / closed 240 / archived 24）。下一轮（round-211）见第 173 条。
>
> round-209 收官（2026-11-21）：**维护轮——五检全绿 + 观察期扫描**（v2.93.0 不增版本，测试 **816 不变**、脚本 **87 不变**、工具 **16 不变**）。freshness/drift/structure/dead-code 四检全绿 + secret-scan 零命中。观察项扫描：①MCP async 家族无新 flaky（第 5 例仍 r204 run2）——家族留观持续；②CI nightly mcp-scan 动态枚举仍待首次 CI 实跑复核（操作员）；③依赖刷新第十五跑锚点 **r210（下一轮即到，专属轮）**。台账不变（263 / open 0 / closed 239 / archived 24）。下一轮（round-210）见第 172 条。
>
> round-208 收官（2026-11-21）：**维护轮——四检全绿 + 观察期扫描**（v2.93.0 不增版本，测试 **816 不变**、脚本 **87 不变**、工具 **16 不变**）。freshness/drift/structure/dead-code 四检全绿 + secret-scan 零命中。观察项扫描：①MCP async 家族 flaky 第 5 例（r204 run2 test_purge_guards）重试绿——家族留观持续；②CI nightly mcp-scan 动态枚举待首次 CI 实跑复核；③下一依赖锚点 r210（2 轮后）。台账不变（263 / open 0 / closed 239 / archived 24）。下一轮（round-209）见第 171 条。
>
> round-207 收官（2026-11-21）：**AB-04 Harbor 三件套概念映射——已对齐零缺口，改名 ROI 不值**（v2.93.0 不增版本，测试 **816 不变**、脚本 **87 不变**、工具 **16 不变**；路线图阶段二⑥）。评测链所有脚本已按 prepare→run→judge 三动词结构组织——与 Harbor 的 task/solver/validator 三件套同型对齐（reports/ab04-harbor-mapping-r207.md）；命名差异仅是术语选择，文件改名 ROI 不值打破引用面。矩阵并行留观察（评测量未达规模）。与 AB-07/12/13/15/17/21 七审计同类——已对齐零缺口；三件套概念映射终局。台账不变（263 / open 0 / closed 239 / archived 24）。下一轮（round-208）见第 170 条。
>
> round-206 收官（2026-11-21）：**AB-21 SKILL.md 渐进披露规范对齐审计——已对齐零缺口**（v2.93.0 不增版本，测试 **816 不变**、脚本 **87 不变**、工具 **16 不变**；路线图阶段二⑤）。13 个 SKILL.md 全量对照 anthropics/skills 规范（reports/ab21-skillmd-audit-r206.md）：6/7 要素已对齐 + 口语触发管控为超出设计 + 2 项有意排除。与 AB-07/12/13/15/17 五审计同类结论——已对齐零缺口；SKILL.md 对齐从路线图移除（终局）。台账不变（263 / open 0 / closed 239 / archived 24）。下一轮（round-207）见第 169 条。
>
> round-205 收官（2026-11-21）：**AB-13 Hooks 拦截器对照审计——已对齐零缺口**（v2.93.0 不增版本，测试 **816 不变**、脚本 **87 不变**、工具 **16 不变**；路线图阶段二④）。五道闸 vs Claude Code Hooks 逐面映射（reports/ab13-hooks-audit-r205.md）：能力覆盖 4/5，唯一差距（改写返回）**有意排除**——审核分立硬约束 + sha256 不可变 + REJECTED→重出路径已存在；Claude Code 5 模式四项已有对应。与 AB-07/12/15 三审计同类结论：已对齐零缺口。台账不变（263 / open 0 / closed 239 / archived 24）。下一轮（round-206）见第 168 条。
>
> round-204 收官（2026-11-21）：**影子 init 延迟修复——首个 fix 轮 + 缺省 on 恢复**（v2.93.0，测试 **816 不变**、脚本 **87 不变**、工具 **16 不变**；路线图阶段二③完形）。r203 根因链闭合的实施落地：shadow init 从循环前置延迟到首个 fix 轮（wt 已由 worktree add 物理创建后）+ core.bare=false/core.worktree 钉住（r202 防护保留）；缺省 --shadow-checkpoints 恢复 on。台账 bare 判定双坑全结（263 / open 0 / closed 239 / archived 24）。双跑 **300.49 / 256.73 秒**（`logs/suite-r204-run1/2.log`，xdist，814 passed + 2 skip；run2 首跑红于 MCP async 家族第 5 例 flaky（test_purge_guards，重试全绿——家族留观持续）。下一轮（round-205）见第 167 条。
>
> round-203 收官（2026-11-21）：**影子 bare 判定上游补研——根因链闭合**（v2.92.0 不增版本，测试 **816 不变**、脚本 **87 不变**、工具 **16 不变**）。诊断矩阵四形态独立复现全通过（仓库外不可复现）→ 手动场景实弹定位根因：shadow init 在 wt 物理创建前运行 + GIT_DIR env 无 GIT_WORK_TREE → bare 模式 init → 后续 add 被 bare 拒绝（防护 config 被 env 优先级压住）。**定案**：影子 init 延迟到首个 fix 轮（wt 物理存在后）+ core.bare=false 钉住 → r204 实施；本轮缺省 off 维持。原始 bare 坑结案，调查条接续追踪。台账（263 / open 0 / closed 239 / archived 24；bare 判定双坑全结）。双跑 **300.49 / 256.73 秒**（`logs/suite-r204-run1/2.log`，xdist，814 passed + 2 skip；run2 首跑红于 MCP async 家族第 5 例 flaky（test_purge_guards，重试全绿——家族留观持续）。下一轮（round-205）见第 167 条。
>
> round-202 收官（2026-11-21）：**AB-11 影子 git 检查点——编码循环持久多检查点**（v2.92.0，测试 **812→816**、脚本 **87 不变**、工具 **16 不变**；路线图阶段二③）。落地 agent/shadow_git.py（snapshot/rollback/checkpoints，独立 shadow 目录与用户 .git 解耦）+ code-task 接线（--shadow-checkpoints/--rollback-to）；**与既有单批回滚分层互补**（先审计后实现）；**设计修正**=影子目录放 worktree 兄弟目录（解耦契约实证）。**缺省 off**：code-task 子进程上下文 bare 判定机制未决（'must be run in a work tree'，环境变量 None、仓库外不可复现——防护 config 已钉、机制裁决列上游补研，open 台账 261 号段）；验收=影子单测四条全绿 + 构造破坏回滚还原实证。台账（261 / open 1 / closed 236 / archived 24）。双跑 **305.65 / 323.11 秒**（`logs/suite-r202-run1/2.log`，xdist，814 passed + 2 skip；run2 首跑红于 MCP async 家族第 4 例 flaky（test_cancel_running_job，重试全绿——家族观察期重启留观）。下一轮（round-203）见第 165 条。
>
> round-201 收官（2026-11-21）：**AB-02 质量指标 pytest 化——指标网格进标准套件**（v2.91.0，测试 **808→812**、脚本 **87 不变**、工具 **16 不变**；路线图阶段二②）。DeepEval 复用评估：41 包依赖面+live LLM 需求→导入不可行，方案复用定型（pytest 式指标断言，同 AB-03 先例）；落地三指标格（①precision 地板 round65 固定产物→precision-gate check 含提示面指纹 ②trace 评测集分数 Tracer fixture→trace-export→阈值断言——AB-01 评测集套件内消费者，r199 勘误闭环 ③评审质量门 D-053 正反双验）——标准套件/nightly CI 出现指标单测格并与 precision 护栏并行出数；产物缺失 SKIP 不假红。台账不变（260 / open 0 / closed 236 / archived 24）。下一轮（round-202）见第 164 条。
>
> round-200 收官（2026-11-21）：**依赖刷新第十四跑——三补丁升级 + 矩阵重分类同步**（v2.90.0，测试 **808 不变**、脚本 **87 不变**、工具 **16 不变**；路线锚点轮）。14 项探测 11 项 no changes + 三真升级（ruff 0.17.6 / coverage 7.17.4 / hypothesis 6.170.17 均补丁级）；矩阵重测 drift：ruff 规则重分类 973/481/251→**973/482/250**（fixable +1/safe −1）——契约无计数钉实证+license PASS+双跑全绿后接受并三面同步（engines 矩阵+AGENTS+文档）。锁定向刷新（--upgrade-package ×3）+ requirements 重导出（**--extra dev** 惯例确认——uv export 缺省不含 optional-dependencies）；附带修正 uv.lock 项目版本 2.62.0 停滞（零升级轮未刷锁积累）。拒 numpy 2.5.5 传递提议。台账不变（260 / open 0 / closed 236 / archived 24）。双跑全绿 **364.08 / 343.25 秒**（`logs/suite-r200-run1/2.log`，xdist，806 passed + 2 skip）。下一依赖锚点约 r210。下一轮（round-201）见第 163 条。
>
> round-199 收官（2026-11-21）：**AB-01 trace 评分回挂 + 评测集导出器**（v2.89.0，测试 **804→808**、脚本 **86→87**、工具 **16 不变**；路线图阶段二①，第 87 号脚本）。落地：trace.py score() 记录（Langfuse score 模型本地形态）+ trace-export.py 导出器（schema trace-eval-set/1，逐会话聚合+score 明细+--require-score 质检）；**勘误（诚实口径）**：吸收列表 AB-01 验收原写「被 run-samples.py 消费」——schema 核查 trace 会话与评审缺陷样本不同构，消费者勘误为 judge 重跑路径（AB-02 集成）。复用优先：Langfuse SDK 不引（scheme 复用同字段语义）。首跑揭两处漂移即修（F5 README 叙述位计数 + doc-drift Q10 docstring 示例含未实现参数——新脚本入仓前三检纪律再实证）。台账（260 / open 0 / closed 236 / archived 24；自报收官链漏 events 三犯坑入册即结，31e4a4d04ca5）。双跑全绿 **313.38 / 290.50 秒**（`logs/suite-r199-run1/2.log`，xdist，806 passed + 2 skip）。下一轮（round-200）见第 162 条。
>
> round-198 收官（2026-11-21）：**AB-03 提示变更回归门——阶段一七项全清**（v2.88.0，测试 **801→804**、脚本 **86 不变**、工具 **16 不变**；路线图阶段一⑥收官）。**promptfoo 复用评估**：其 YAML 矩阵需 live provider（REVIEW_LLM unset + CI 无端点）不可行——采用其「声明式变更即红」概念，确定性形态落地（JSON 声明，治理壳 stdlib）；live 矩阵随 AB-02 judge 集成再评估。**落地**：precision-gate 第五项检查 prompt_regression（声明面 sha256 指纹 vs 基线，PROMPT_DRIFT 判红指路）+ record-baseline 子命令 + prompt-watch.json（judge 语义臂/编码循环两提示载体）；契约 +3（record→PASS→改→必抓反向验证）；真仓实弹五检查全 PASS（judge=round65 产物）。台账不变（259 / open 0 / closed 235 / archived 24）。双跑全绿 **376.73 / 285.03 秒**（`logs/suite-r198-run1/2.log`，xdist，802 passed + 2 skip）。**阶段一（AB-07/08/09/12/15/17/03）七项全清，下一轮进阶段二**。下一轮（round-199）见第 161 条。
>
> round-197 收官（2026-11-21）：**AB-12 对照审计 + AB-17 中心度复评实验**（v2.87.0，测试 **801 不变**、脚本 **86 不变**、工具 **16 不变**；路线图阶段一④⑤）。AB-12 已对齐零缺口（phases.py 门禁+契约双在位，Cline/CC 同型）；**AB-17 决定性负结果**：量具新增三中心度变体（refs4+cent4=7/11、cent8_backfill=0/11、cent8_pure=0/11）——refs 9/11 守擂，PPR 图重要性与任务相关性正交，aider REPOMAP 方案不迁移成立，**D-031 维持且强化**（终局证据，不再重议）。**cancel 竞速第三例（新根因类）**：run1 实弹 job_state failed≠cancelled——worker 终态写与 cancel 竞速，超时/终局两路径写前加复查守卫即修（家族 27/27+cancel 连续两过；三例三因对策链完整 r184 负载轮询/r190 共享锁/r197 终态竞速）；run1 另揭 README 台账计数漏同步（F6a 拦截）即修。台账（259 / open 0 / closed 235 / archived 24）。双跑全绿 **284.74 / 266.74 秒**（`logs/suite-r197-run1/2.log`，xdist，799 passed + 2 skip；最快一对）。下一轮（round-198）见第 160 条。
>
> round-196 收官（2026-11-21）：**AB-08 mcp-scan 进 nightly + AB-09 工具描述规范**（v2.86.0，测试 **801 不变**、脚本 **86 不变**、工具 **16 不变**；路线图阶段一②③）。**复用优先**：直接复用 Invariant mcp-scan v2.3.0（npx+npmmirror 实测可用）——本地实测静态检查正常、动态枚举 Windows 全形态失败（如实记录）→ 动态枚举以 CI ubuntu nightly 为准（首个 CI 报告落 baseline，第 157 条跟进）；nightly 新增 mcp-scan 步（扫描器钉 2.3.0，critical/high 判红）。**潜伏缺陷连带修复**：接线前 PyYAML 校验发现 self-check.yml 预存多行标量缺陷（windows full-suite 步内嵌裸换行）——pushes 恢复后 nightly 将整体起不来、无人观察；修复为块标量，两 workflow 合法化，接线校验纪律固化（台账 +1 即结 265773e7f126）。AB-09：docs/06-operations §MCP 工具描述规范四条。台账（258 / open 0 / closed 234 / archived 24）。双跑全绿 **377.26 / 372.00 秒**（`logs/suite-r196-run1/2.log`，xdist，799 passed + 2 skip）。下一轮（round-197）见第 158 条。
>
> round-195 收官（2026-11-21）：**AB-07 ACI 工具面审计 + AB-15 对照审计**（v2.85.0，测试 **801 不变**、脚本 **86 不变**、工具 **16 不变**；路线图阶段一①⑦）。16 工具×三准则逐条对照（reports/aci-audit-r195.md）：3 处描述面修订（scan 失败语义/coding 条件必填说明/director prose 补 scorecard）；AB-15 对照零差异（edit_formats 唯一命中与 opencode 同型、终端闸同型）。诚实口径：描述改动不改行为——precision 数字预期不变，ACI 收益量化留待 LLM 臂复测点。上游补研受阻（SWE-agent 文档直连+CDN 均重置）——以资料三准则为准，实例细节留网络窗口。台账不变（257 / open 0 / closed 233 / archived 24）。下一轮（round-196）见第 157 条。
>
> round-194 收官（2026-11-21）：**详细能力吸收列表 + 升级优化路线制定**（v2.84.0 不增版本，测试 **801 不变**、脚本 **86 不变**、工具 **16 不变**）。机制深拆两轮（评测基础设施 8 对象 + 治理与上下文 12 对象）+ 移动端归档确认后产出两份交付：`reports/absorb-list-r194.md`（AB-01..27 逐项机制级吸收列表，5 处上游补研缺口如实标注）+ `reports/upgrade-roadmap-r194.md`（三阶段 21 项+横切纪律 7 条；阶段一 r194-r200 七项 S 档=ACI 审计/mcp-scan/描述规范/Plan 收窄/中心度复评/回归门/Edit 审计；阶段二评测闭环四层贯通；阶段三条件轮）。第 155 条重构为引用路线图。台账不变（257 / open 0 / closed 233 / archived 24）。下一轮（round-195）见第 156 条。
>
> round-193 收官（2026-11-21）：**开源生态吸收地图研究轮**（v2.84.0 不增版本，测试 **801 不变**、脚本 **86 不变**、工具 **16 不变**）。四路并行只读研读 450+ 项目资料逐条对照（reports/absorb-map-opensource-r193.md）：战略确认引擎组合（Ruff/LibCST/ast-grep）在评审 agent 中零公开同类=差异化空白、AutoGPT 反例反向印证五道闸、MCP Registry 需跟进、Aider 放缓警示固化借鉴纪律；候选借鉴 Top10 进第 155 条（评测闭环三差距 trace 评分回挂/质量指标 pytest 化/prompt 回归门 + MCP 三道自检 ACI/mcp-scan/工具描述规范 + 影子 git + repo_map 中心度复评 + Serena 对照 + SKILL.md 对齐 + elicitation 远期）。台账不变（257 / open 0 / closed 233 / archived 24）。下一轮（round-194）见第 155 条。
>
> round-192 收官（2026-11-21）：**MCP async 家族观察期收口**（v2.84.0 不增版本，测试 **801 不变**、脚本 **86 不变**、工具 **16 不变**）。收口证据：r190 读写硬化（uuid4 唯一 tmp + _read_json_retry）后连续三轮全量零复现——r190 双跑 308.17/326.38s + r191 双跑 286.05/408.55s + 本轮 light 406.76s（家族全成员含取消摘要/账本子资源/并发契约）。家族失稳史闭环：r184 1 例（留观收口）→ r190 1 例（产品真根因即修）→ 连续三轮零复现。light 单跑全绿 **406.76 秒**（`logs/suite-r192-run1.log`，799 passed + 2 skip）。台账不变（257 / open 0 / closed 233 / archived 24）。下一轮（round-193）见第 154 条。
>
> round-191 收官（2026-11-20）：**发布闸证据面重跑陷阱硬化**（v2.84.0，测试 **799→801**、脚本 **86 不变**、工具 **16 不变**）。r190 三连拦截的结构性教训落地：check_git_state 对闸自身 --out 证据路径自豁免（空白切路径段 + R 重命名尾段 + resolve 规范比对 + **porcelain 目录折叠形态前缀匹配**），out_evidence_excluded 计数入 evidence；**重跑陷阱活体实证**（连续两次过闸不提交证据面：修复前 ok:False → 修复后 ok:True、excluded=1、dirty=0）；+2 契约（out 脏→PASS / out+他脏→仍 FAIL 反向验证，8/8 绿）；两轮实弹伪像（strip 后固定列切片、目录折叠）均由契约与活体验证即时抓住。台账（257 / open 0 / closed 233 / archived 24）。双跑全绿 **286.05 / 408.55 秒**（`logs/suite-r191-run1/2.log`，xdist，799 passed + 2 skip）。下一轮（round-192）见第 153 条。
>
> round-190 收官（2026-11-20）：**依赖刷新第十三跑 + MCP status 并发写读防冲突**（v2.83.0，测试 **798→799**、脚本 **86 不变**、工具 **16 不变**）。零升级 14/14（13/14 no changes；拒 numpy 2.5.5 传递提议，r182/r173 先例）；三矩阵零漂移（973/481/251 + 29/2/2 + libcst 全等）。run2 实弹 PermissionError on status.json.tmp——MCP async 家族第二例，定位到产品真根因（固定 tmp 名跨线程碰撞 + 读写双侧无共享锁容错）：_status_write 改 uuid4 唯一 tmp + 双异常有界重试、_read_json_retry 读侧容错、+1 并发契约（生产节奏建模 5-15ms）。二轮即修：空 catch 改 contextlib.suppress（lang-empty-catch 自扫命中新代码）；发布闸 tag-reuse 预检拦截闸前误打 tag + 证据面勘误（fc9d48c 误标七项全绿→勘误提交留痕）。README L20 版本 token 两轮停滞勘误（v2.81.0→v2.83.0）。台账（256 / open 0 / closed 232 / archived 24）。双跑全绿 **308.17 / 326.38 秒**（`logs/suite-r190-run1/2.log`，xdist，797 passed + 2 skip）。下一轮（round-191）见第 152 条。
>
> round-189 收官（2026-11-20）：**弹窗修复真作业实证冒烟**（v2.82.0 不增版本，测试 **798 不变**、脚本 **86 不变**、工具 **16 不变**）。temp 双提交仓 + 真 runner.py 全链：queued→running→done、PROGRESS 10 步全过、runner 终态 DONE（`reports/_work/smoke-r189.json`）——r188 CREATE_NO_WINDOW spawn 树端到端实证通过；夹具勘误（首版单提交仓 HEAD~1 不可解析属冒烟夹具问题非链路缺陷）；作业级账本仅 cancel/purge 写入为设计行为（干净 done 无账本属预期）。light 单跑全绿 **303.92 秒**（`logs/suite-r189-run1.log`，796 passed + 2 skip）。台账不变（255 / open 0 / closed 231 / archived 24）。下一轮（round-190）见第 151 条。
>
> round-188 收官（2026-11-20）：**MCP 异步作业 spawn 静默化——黑色弹窗根因修复**（v2.82.0，测试 **797→798**、脚本 **86 不变**、工具 **16 不变**）。用户报告黑色弹窗频现：_submit_tool 用 DETACHED_PROCESS 起 worker（无控制台），worker 裸 Popen 起 runner——Windows 为无控制台父的控制台子程序分配【可见】控制台，作业链每个子孙闪黑窗（r185 压测 5×25 假作业对上弹窗量）；worker 与 runner 两处 spawn 改 CREATE_NO_WINDOW（隐藏控制台可继承，根除分配可见窗），taskkill /T /F 取消语义与组标记不变；+1 契约（Popen 捕获三断言：NO_WINDOW 在位/DETACHED 禁用/组标记保留；POSIX 保持 start_new_session）。首跑揭 F5 漏更（README L217 叙述位 797——sync-counts 又漏叙述位，同 r186 款）即修并入工作提交。台账（255 / open 0 / closed 231 / archived 24）。双跑全绿 **308.44 / 322.06 秒**（`logs/suite-r188-run1/2.log`，xdist，796 passed + 2 skip）。下一轮（round-189）见第 150 条。
>
> round-187 收官（2026-11-20）：**heredoc 转义坑入册即结 + 契约 797 首周观察**（v2.81.0 不增版本，测试 **797 不变**、脚本 **86 不变**、工具 **16 不变**）。heredoc 三层转义嵌套损毁源码坑入册即结（对策=程序化写源码一律 Edit/Write 工具 + 写后即时收集验证；r186 两处均被收集期 SyntaxError 拦截未进提交历史）；light 单跑全绿 **446.23 秒**（`logs/suite-r187-run1.log`，795 passed + 2 skip——幂等守卫与夹具修复后连续第二轮全绿）。台账（254 / open 0 / closed 230 / archived 24）。下一轮（round-188）见第 149 条。
>
> round-186 收官（2026-11-20）：**close 门账本追加幂等守卫**（v2.81.0，测试 **794→797**、脚本 **86 不变**、工具 **16 不变**）。机制确证：r154 历史双记=close 重跑同轮双记（r185 close 首跑 FAIL 后重过闸未双记属侥幸非守卫）；守卫落地——_ledger_has_round_summary 容坏行扫描 + _append_ledger_record 前置守卫（读失败保守放行，best-effort 不变），+3 契约（同轮双记拦截/异轮不受阻反向验证/坏行容错）；AGENTS 表行注记。开局 F6b 拦截 README 计数漏更（r185 结案后未同步——红线 7 引用面遗漏，开局前修正提交）。台账（253 / open 0 / closed 229 / archived 24）。双跑全绿 **412.61 / 381.24 秒**（`logs/suite-r186-run1/2.log`，xdist，795 passed + 2 skip）。下一轮（round-187）见第 148 条。
>
> round-185 收官（2026-11-20）：**MCP flaky 留观复核结案 + 事件账本对账复核**（v2.80.0 不增版本，测试 **794 不变**、脚本 **86 不变**、工具 **16 不变**）。留观证据链：隔离 3/3 过（r184）+ 模块 -n 2 压测 5 轮 5/5 过 + 全量 light 复跑零复现（**441.78 秒**，792+2skip）——r184 单次失败为负载型偶发，按坑对策条款（零复现结案）结案；台账 open 清零（252 / open 0 / closed 228 / archived 24）。账本对账（第 145 条③顺延）：哈希链 verify 完好、round-summary 153..184 全覆盖 32/32、轮报全齐；r154 历史双记 1 条（11 秒间隔双 append）如实记录、不追改历史。light 单跑全绿（`logs/suite-r185-run1.log`，xdist）。下一轮（round-186）见第 147 条。
>
> round-184 收官（2026-11-19）：**评测口径季度对账成立 + 测试夹具过期类修复**（v2.80.0，测试 **794 不变**、脚本 **86 不变**、工具 **16 不变**）。对账四项成立（0.42% 复算 3/713 + clean 零噪声 97.4%、README/PROGRESS 引用面无漂移、D-053 因果表述完好、778→794 的 +16 契约全属 MCP 异步面——评测语义零变更）；light 单跑揭 3 失败即修：compact-memory 两测夹具钉死日期（2026-10-20）恰越 --max-age-days 30 老化边界——**类修复** 8 处改 _fresh_iso 相对时间戳（含 aged_deletion 5 天后将要越界的潜伏雷）；MCP ledger flaky 留观 open（隔离 3/3 过，负载下 1 次失稳）。台账（252 / open 1 / closed 227 / archived 24）。双跑全绿 **465.75 / 394.17 秒**（`logs/suite-r184-run1/2.log`，xdist，792 passed + 2 skip）。下一轮（round-185）见第 146 条。
>
> round-183 收官（2026-11-18）：**CI nightly 全量口径复核**（v2.79.0 不增版本，测试 **794 不变**、脚本 **86 不变**、工具 **16 不变**）。
> 600s 护栏双侧生效（CI ubuntu/windows + release-gate），nightly 门禁面逐项在册，零漂移无需改动。
> light 单跑 276.53 秒（线内）。台账 250 / open 0 / closed 226 / archived 24。
> 下一轮（round-184）见第 145 条。
>
> round-182 收官（2026-11-18）：**依赖刷新第十二跑**（v2.79.0，测试 **794 不变**、脚本 **86 不变**、工具 **16 不变**）。
> 清华镜像一次命中零降级；14/14 探测零升级；拒 numpy 传递升级；三矩阵零漂移。
> 双跑 262.56 / 275.79 秒。台账 250 / open 0 / closed 226 / archived 24。
> 下一轮（round-183）见第 144 条。
>
> round-181 收官（2026-11-18）：**MCP 异步作业全链收官复核**（v2.78.0 不增版本，测试 **794 不变**、脚本 **86 不变**、工具 **16 不变**）。
> tools/handlers 16 对齐、5 份冒烟证据在仓、5 处文档计数一致；对外口径不变。
> light 单跑 260.53 秒（线内）。台账 250 / open 0 / closed 226 / archived 24。
> 下一轮（round-182）见第 143 条。
>
> round-180 收官（2026-11-18）：**阶段 C 落地——purge 三重闸**（v2.78.0，测试 **791→794**、脚本 **86 不变**、工具 **15→16**）。
> code_review_purge（confirm + 单 id + 终态 + 中央账本摘要）；真作业 done→purge→resource 不可读。
> D-055 扩面 B+C 与 r178 资源 A+B 全部完成；对外口径不变。双跑 280.11 / 266.81 秒。
> 台账 250 / open 0 / closed 226 / archived 24。下一轮（round-181）见第 142 条。
>
> round-179 收官（2026-11-18）：**jobs 资源 A+B 落地**（v2.77.0，测试 **786→791**、脚本 **86 不变**、工具 **15 不变**）。
> resources/read 增 cancel 摘要 + ledger_verify envelope；新增 review://jobs/<id>/ledger 子资源；真作业冒烟全通。
> 阶段 C（purge）已批准，下轮实现。双跑 258.51 / 272.06 秒。
> 台账 250 / open 0 / closed 226 / archived 24。下一轮（round-180）见第 141 条。
>
> round-178 收官（2026-11-18）：**jobs 资源扩面提案写案**（v2.76.0 不增版本，测试 **786 不变**、脚本 **86 不变**、工具 **15 不变**）。
> reports/proposal-jobs-resource-r178.md：A 扩展 resources/read（+3 契约，建议先批）/ B 账本子资源 / C 另案；待裁决。
> 阶段 C（purge）仍未批；依赖锚点未到。light 单跑 243.31 秒（线内）。
> 台账 250 / open 0 / closed 226 / archived 24。下一轮（round-179）见第 140 条。
>
> round-177 收官（2026-11-18）：**MCP 异步回归 + `runs/jobs/` 审计**（v2.76.0，测试 **783→786**、脚本 **86 不变**、工具 **15 不变**）。
> +3 契约（Unix 信号 mock / ProcessLookupError / worker_pid 回退，17/17 全绿）；6 作业目录 0.2MB 无清理迫切性。
> 阶段 C（purge）未批准不实现；依赖锚点未到。双跑 217.41 / 213.52 秒。
> 台账 250 / open 0 / closed 226 / archived 24。下一轮（round-178）见第 139 条。
>
> round-176 收官（2026-11-18）：**D-055 扩面阶段 B 落地**（v2.75.0，测试 **778→783**、脚本 **86 不变**、工具 **14→15**）。
> cancel（进程树终止 + 账本摘要）+ 配置白名单透传；真作业取消 killed_pids 非空、后续 submit done step=10。
> D-052 粒度勘误（双跑中位 >540s）；阶段 C（purge）仍未批准。双跑 227.97 / 227.24 秒。
> 台账 250 / open 0 / closed 226 / archived 24。下一轮（round-177）见第 138 条。
>
> round-175 收官（2026-11-18）：**评测口径复核**（v2.74.0 不增版本，测试 **778 不变**、脚本 **86 不变**、工具 **14 不变**）。
> 0.42% 复算成立（3/713 + clean 零噪声 97.4%），对外口径与 D-053 因果表述无勘误；D-052 判定粒度歧义登记。
> light 单跑 299.40 秒（线内）。台账 250 / open 0 / closed 226 / archived 24。
> 下一轮（round-176）见第 137 条。
>
> round-174 收官（2026-11-18）：**MCP 异步作业扩面提案（v2.74.0 不增版本，测试 **778 不变**、脚本 **86 不变**、工具 **14 不变**）**。
> 提案 reports/proposal-mcp-async-ext-r174.md：三缺口 + 候选 A/B/C（建议分阶段 B→C，+8 契约），待总监裁决；本轮零代码。
> light 单跑 243.69 秒（线内）。台账 250 / open 0 / closed 226 / archived 24。
> 下一轮（round-175）见第 136 条。
>
> round-173 收官（2026-11-18）：**依赖刷新第十一跑**（v2.74.0，测试 **778 不变**、脚本 **86 不变**、工具 **14 不变**）。
> 清华镜像一次命中零降级；升 ast-grep-py 0.51.3、拒 numpy 传递升级；三引擎矩阵零漂移。
> 双跑 527.80 / 514.48 秒（< 540s 触发线、< 600s 护栏，各 2 skip）；按 D-035 gate 绿后打并推 v2.74.0 tag。
> 台账 250 / open 0 / closed 226 / archived 24。下一轮（round-174）见第 135 条。
>
> round-172 收官（2026-11-18）：**D-055 step 进度帧修复 + 真作业复冒烟**（v2.73.0，测试 **775→778**、脚本 **86 不变**、工具 **14 不变**）。
> runner stderr PROGRESS 帧 + worker 终局补扫；running step=6 → 断连重连 → done step=10；+3 契约全绿。
> 双跑 446.64 / 416.67 秒（< 450s，各 2 skip）；按 D-035 gate 绿后打并推 v2.73.0 tag。
> 台账 250 / open 0 / closed 226 / archived 24。下一轮（round-173）见第 134 条。
>
> round-171 收官（2026-11-18）：**D-055 真作业冒烟 + tag 断档全量追认**（v2.72.0 不增版本；测试 **775 不变**、脚本 **86 不变**、工具 **14 不变**）。
> 真作业断连重连 status/resource 全通；step 帧未解析与 findings=[] 如实记录；v2.38–v2.72 共 35 tag 预检后追认推送。
> light 单跑 427.80 秒（< 450s）。台账 250 / open 0 / closed 226 / archived 24。
> 下一轮（round-172）见第 133 条。
>
> round-170 收官（2026-11-18）：**D-055 批准实现（v2.72.0，测试 **769→775**、脚本 **86 不变**、工具 **12→14**）**。
> submit/status 双工具 + review://jobs/<id> 资源；独立子进程 + uuid4 路径守卫；假作业 6 契约全绿。
> 双跑 374.39 / 366.28 秒（< 600s，各 2 skip）。按裁定本轮不打 tag、不推送（gate 证据生成后一并推 main）。
> 台账 250 / open 0 / closed 226 / archived 24。下一轮（round-171）见第 132 条。
>
> round-169 收官（2026-11-17）：**受阻轮补录操作规程入仓**（v2.71.0，测试 **769 不变**、脚本 **86 不变**）。DEVELOPMENT §10 增补补录三步规程（重跑重写日志防 stale 误记 / 换位过闸 / 尾随 commit；r141 与 r166/167 两批先例固化）；key 轮换检查 secret-scan 零命中。**补录完成（2026-11-18）：双跑全绿 482.44 / 524.33 秒**（`logs/suite-r169-run1/2.log`，xdist，767 passed + 2 skipped，总 769 ✓；第二 skip 为 docker 条件门——Docker 未运行 docker info 实测坐实，常驻 skip 为 DEEPSWE_RUN 门，非套件回归）；2.71.0 发布闸七项全绿；受阻期按 D-052 不绕闸（run1 92% 被护栏击杀 + 重试被宿主异常终止）。台账不变（250 / open 0 / closed 226 / archived 24）。下一轮（round-170）见第 131 条。
>
> round-168 收官（2026-11-17）：**补录收尾 + 口径纪律维护**（v2.70.0，测试 **769 不变**、脚本 **86 不变**）。r166/r167 双轮 close 完成（台账 166/167 closed；r166 双跑 538.03/576.84s 全绿、r167 light 单跑 573.40s 全绿）；2.69.0 发布闸证据补齐（七项全绿）——版本证据面恢复连续；PROGRESS §1 快照同步（坑台账 246→250、最近已提交锚点、契约测试行补录时长）；台账入册 stale 日志轮询误记坑并即结（7f6a9642b12f，对策=闸面以闸内新鲜读取为准）。台账（250 / open 0 / closed 226 / archived 24）。双跑全绿 **541.53 / 520.45 秒**（`logs/suite-r168-run1/2.log`，xdist，skip 1/1；双双回落 540s 线内）。下一轮（round-169）见第 130 条。
>
> round-167 收官（2026-11-15）：**依赖刷新第十跑——零升级**（v2.69.0，测试 **769 不变**、脚本 **86 不变**）。12 项清华镜像逐项对照 12/12 已最新；三矩阵落盘对比全一致；零代码变更轮。**补录完成（r168 开局补录，2026-11-15）：light 单跑全绿 573.40 秒**（`logs/suite-r167-run1.log`；另补 run2 583.12 秒供 2.69.0 发布闸证据，`logs/suite-r167-run2.log`）。台账不变（249 / open 0 / closed 225 / archived 24）。下一轮（round-168）见第 129 条。
>
> round-166 收官（2026-11-15）：**变异抽检复跑 + 盲区处方补齐**（v2.68.0，测试 **767→769**、脚本 **86 不变**）。round-gate.py kill_rate 1.0（10/10 全杀）；doc-freshness.py 首跑 0.1（9 盲区=truth_values F8 块零直接断言）→ 按处方 +2 行为断言（canary 优先级/113 特判/逐行计数）→ 复跑 1.0。台账不变（249 / open 0 / closed 225 / archived 24）。**补录完成（r168 开局补录，2026-11-15）：双跑全绿 538.03 / 576.84 秒**（`logs/suite-r166-run1/2.log`，xdist，skip 1/1；两连红后第三次重试全绿，勘误 d4e5ec5）。下一轮（round-167）见第 128 条。
>
> round-165 收官（2026-11-15）：**CI 门禁接线对账**（v2.67.0，测试 **767 不变**、脚本 **86 不变**）。表标「CI 门禁」8 脚本核对执行面：doc-structure 缺接线（接线前实跑抓到真漂移——PROGRESS L24 || 空列 + 真值陈旧 b3c744c/v2.54.0，修复后 20/20 PASS 接线 CI）；mutation-sampler 登记修正为按需抽检；e2e-check 体检 rc=0。台账不变（249 / open 0 / closed 225 / archived 24）。下一轮（round-166）见第 127 条。
>
> round-164 收官（2026-11-15）：**SRE 预算结算机械化**（v2.66.0，测试 **765→767**、脚本 **86 不变**）。round-gate close 增第八项检查 scorecard_budget：WARN（≤2×阈值）关注不阻断、EXCEEDED（>2×阈值）判红（17 open 坑反向验证实弹被拦）；真仓 PASS；AGENTS 两处表行同步口径。约定「每轮结算」至此机械化。台账不变（249 / open 0 / closed 225 / archived 24）。下一轮（round-165）见第 126 条。
>
> round-163 收官（2026-11-15）：**维护轮——scorecard 恢复 + coverage 复测**（v2.65.0，测试 **765 不变**、脚本 **86 不变**）。org-scorecard 实跑恢复每轮约定（全项 PASS + 两项 N/A 如实）；coverage 76.16% vs 基线 76.09%（容差内 +0.07pp）、check rc=0，覆盖面新文件 latency-bench.py（80.77%）按 r122 先例信息登记。结构候选：scorecard 并入 close 门（125 条②）。台账不变（249 / open 0 / closed 225 / archived 24）。下一轮（round-164）见第 125 条。
>
> round-162 收官（2026-11-14）：**观察收口轮**（v2.64.0，测试 **765 不变**、脚本 **86 不变**）。540s 触发线裁决跑 465.85/475.57s 双双回落线内——越线序列（r160 两跑+r161 run2）为间歇型未成三连，观察解除、阈值不动；双新检查（F10/suite_count_claim）首周四轮零误报收口。台账不变（249 / open 0 / closed 225 / archived 24）。下一轮（round-163）见第 124 条。
>
> round-161 收官（2026-11-14）：**依赖刷新第九跑**（v2.63.0，测试 **765 不变**、脚本 **86 不变**）。12 项清华镜像逐项探测：11 项已最新，唯一可升 ast-grep-py 0.51.1→0.51.2（补丁级）；三引擎矩阵重测零漂移（升级保留）；uv.lock/requirements-lock 重导出；license-check rc=0；astgrep 18 契约全绿。双跑 459.80/573.02s 全绿（run2 仍越 540s 触发线，间歇负载持续观察）。台账不变（249 / open 0 / closed 225 / archived 24）。下一轮（round-162）见第 123 条。
>
> round-160 收官（2026-11-14）：**台账清账轮——开册以来首次清零**（v2.62.0，测试 **765 不变**、脚本 **86 不变**）。五坑逐项取证结案（release-gate 契约 r152 补齐 / uv.lock override r149 落地 / 前置校验口径 r138 纠正 / D-052 护栏+r157-159 三轮六跑全绿 / libcst 管道直比纪律固化）→ 249 / open 0 / closed 225 / archived 24（开册以来首次清零）。suite_count_claim 首用 PASS（765==[765,765]）。下一轮（round-161）见第 122 条。
>
> round-159 收官（2026-11-14）：**收官行计数机械对账**（v2.61.0，测试 **761→765**、脚本 **86 不变**）。round-gate close 增 suite_count_claim：收官行「测试 A→B/A 不变」终值逐跑对照双跑实测，不一致 FAIL（r154 误计复刻被拦，+4 契约）；无声明行不编造失败。F10 判据清单下游复核（DEVELOPMENT F1-F9→F1-F10）。r154 误计坑 2122392940fc 结案（open 6→5）。台账（249 / open 5 / closed 220 / archived 24）。下一轮（round-160）见第 121 条。
>
> round-158 收官（2026-11-14）：**行数基线机械对账**（v2.60.0，测试 **758→761**、脚本 **86 不变**）。doc-freshness 增 F10：BASELINE 钉的「- <skill>: N」逐条对照 SKILL.md 实际行数（含 missing 档）；复刻 r157 实景反向验证 +3 契约；BASELINE 基线块注明机械拦截。r157 坑 c2ff61af5e52 结案（open 7→6）。台账（249 / open 6 / closed 219 / archived 24）。下一轮（round-159）见第 120 条。
>
> round-157 收官（2026-11-14）：**护栏下游对账**（v2.59.0，测试 **757→758**、脚本 **86 不变**）。MCP code_review_retro round 描述更新（真仓必填）+ 新增 MCP 真仓拒绝契约（护栏单点在脚本，MCP 透传 isError 面）；全仓引用面扫余均为叙述文本。r156 遗留坑入册（SKILL.md 行数未同步 BASELINE 基线，+1）。提交未推送，nightly CI 观察条件不满足如实记录。台账（249 / open 7 / closed 218 / archived 24）。下一轮（round-158）见第 119 条。
>
> round-156 收官（2026-11-14）：**retro-report 防重跑护栏**（v2.58.0，测试 **754→757**、脚本 **86 不变**）。真仓（有 next-round.md）缺省自动编号一律拒绝 rc=2，必须显式 --round N 或 --confirm-next；复刻 r154 实景反向验证 + 真仓两态实弹；AGENTS/SKILL 口径同步（红线 7）。SLO 门禁首跑观察全 PASS（p95 0.094-0.116s，margin 0.88-1.88s）。坑 a5ba44db35ee 结案（open 7→6）。台账（248 / open 6 / closed 218 / archived 24）。下一轮（round-157）见第 118 条。
>
> round-155 收官（2026-11-14）：**scan SLO 门禁化**（v2.57.0，测试 **748→754**、脚本 **86 不变**）。latency-bench check 动词对 latency-slo.json 逐档断言 p95 上限（S/M/L 1.0/1.0/2.0s，~10x 余量），nightly run+check 全链接线；红线 6 反向验证实弹抓住超限样例。pip-audit 首周观察：锁面零 CVE，本地 venv 工具链 soupsieve CVE 已升级清零。r154 计数误计勘误（真值 745→748）；retro-report 过早产物坑入册。台账 +2（248 / open 7 / closed 217 / archived 24）。下一轮（round-156）见第 117 条。
>
> round-154 收官（2026-11-14）：**性能基准 + 账本自动化**（v2.56.0，测试 **751→754**、脚本 **85→86**）。latency-bench 三档 p50/p95（0.117-0.122s 恒定——SLO 数据源首建）；close 全过自动追加哈希链记录（F4 机械自动）；AGENTS MCP 表 4→12 对账（LLM 工具面漂移）；MCP 异步作业设计稿待裁决。台账不变（246 / open 5 / closed 217 / archived 24）。下一轮（round-155）见第 115 条。
>
> round-153 收官（2026-11-14）：**event-ledger 哈希链接入 + 覆盖重测**（v2.55.0，测试 **751 不变**、脚本 **85 不变**）。F4 结构改造落地（轮收官哈希链约定：AGENTS 第 4 步 + ops 文档；r141..153 摘要 3 条 verify 完好）；F6 覆盖重测 76.09% 持平、check 门 rc=0。ollama 复探仍 DOWN。台账不变（246 / open 5 / closed 217 / archived 24）。下一轮（round-154）见第 114 条。
>
> round-152 收官（2026-11-14）：**二轮审查即修 F1/F3/F5**（v2.54.0，测试 **749→751**、脚本 **85 不变**）。release-gate 解析器 +6 契约（红线 6 债清偿）+ smoke 208 + 运维表 +5；F2 Gitea CI 死配置与 F4 event-ledger 断链登记候选。测试债坑 1 条入册收口（246 / open 5 / closed 217 / archived 24）。下一轮（round-153）见第 114 条。
>
> round-151 收官（2026-11-14）：**astgrep 适配器 WinError 206 修复**（v2.53.0，测试 **749 不变**、脚本 **85 不变**）。payload 文件传输替代 argv；103 文件 SAST 全量 0 错误。台账不变（245 / open 4 / closed 217 / archived 24）。r141..151 十一轮收官批次到此全部完成（ROADMAP §5.103 批次节关闭，逐轮条目 §5.98-§5.113 已落）。下一轮（round-152）见第 113 条。
>
> round-150 收官（2026-11-14）：**CII Best Practices 预填自查**（v2.52.0，测试 **749 不变**、脚本 **85 不变**）。13 判据证据映射完成；操作员照单注册（唯一 gap=内网 https）。台账不变（245 / open 4 / closed 217 / archived 24）。下一轮（round-151）见第 112 条。
>
> round-149 收官（2026-11-14）：**锁对齐 pytest 9.2.0——override 实验成功**（v2.51.0，测试 **749 不变**、脚本 **85 不变**）。锁与 venv 分歧关闭；ruff 矩阵 973/481/251 三处同步。台账不变（245 / open 4 / closed 217 / archived 24）。下一轮（round-150）见第 111 条。
>
> round-148 收官（2026-11-14）：**CVE 扫描闭环**（v2.50.0，测试 **749 不变**、脚本 **85 不变**）。pip-audit 7→0（black/setuptools 升级）+ nightly 固化；Scorecard Vulnerability-Scan 缺口关闭。台账不变（245 / open 4 / closed 217 / archived 24）。下一轮（round-149）见第 110 条。
>
> round-147 收官（2026-11-14）：**权威手册对齐 + 真值清理**（v2.49.0，测试 **749 不变**、脚本 **85 不变**）。light 收官用法入权威源；83→85 两处清理。台账不变（245 / open 4 / closed 217 / archived 24）。下一轮（round-148）见第 109 条。
>
> round-146 收官（2026-11-14）：**OpenSSF Scorecard 对标整改**（v2.48.0，测试 **749 不变**、脚本 **85 不变**）。4 处 Actions SHA 钉定 + permissions 收敛 + SBOM + SAST 自查零命中。台账不变（245 / open 4 / closed 217 / archived 24）。下一轮（round-147）见第 108 条。
>
> round-145 收官（2026-11-14）：**provider host 流契约 +5**（v2.47.0，测试 **744→749**、脚本 **85 不变**）。host 协议零覆盖缺口关闭；POSIX 跨平台断言（Linux CI 可跑）。台账不变（245 / open 4 / closed 217 / archived 24）。下一轮（round-146）见第 107 条。
>
> round-144 收官（2026-11-14）：**自研变异采样器 mutation-sampler.py**（v2.46.0，测试 **739→744**、脚本 **84→85**）。mutmut Windows 不可用 → stdlib AST 方案（硬约束 1 契合）；RQG 实弹 kill_rate 0.8。台账 245 / open 4 / closed 217 / archived 24。下一轮（round-145）见第 102 条。
>
> round-143 收官（2026-11-14）：**PROGRESS 沿革瘦身**（v2.45.0，测试 **739 不变**、脚本 **85 不变**）。契约测试格 3267→313 字符；r102/103 时长勘误补录。台账不变（245 / open 4 / closed 217 / archived 24）。下一轮（round-144）见第 101 条。
>
> round-142 收官（2026-11-14）：**round-gate --round-type light 轻量收官**（v2.44.0，测试 **739 不变**、脚本 **85 不变**）。双跑 xdist **516.7 / 498.2 秒**全绿（skip 1/1）。台账不变（245 / open 4 / closed 217 / archived 24）。下一轮（round-143）见第 100 条。
>
> round-141 收官（2026-11-13）：**归因修正 + eval-config 口径事实源 + D-052 判红事件收口**（v2.43.0，测试 **726→739**、脚本 **84→85**）。双跑切 xdist（D-051 批 A 预授权，release-gate 补 pytest 双格式解析）：**443.2 / 456.8 秒全绿**——顺序双跑 693.7/603.7 双超 600s（套件本体增长），xdist 为既定提速路径。判红四连坑收口入册（245 / open 4 / closed 217 / archived 24）。下一轮（round-142）见第 99 条。
>
> round-140 收官（2026-11-12）：**第三方 judge 探测 blocked**（v2.42.0，测试 **723 不变**、脚本 **84 不变**）。三步探测全挡（11434 拒连 / ollama 未装 / Docker 路径无镜像背书放弃）；无第三方数字产出、不冒充；judge 通路代码侧就绪（provider loopback 白名单），复评预案固化第 101 条。台账不变（244 / open 3 / closed 217 / archived 24）。下一轮（round-141）见第 102 条。
>
> round-139 收官（2026-11-12）：**供应链锁定 + CI 面**（v2.41.0，测试 **723 不变**、脚本 **84 不变**）。uv.lock（107 包）+ requirements-lock.txt（全 sha256）入仓；CI 改 --require-hashes 锁安装（hash 演练全过）；依赖漂移（typescript/go 缺项）清零；dependabot 双生态 weekly；windows nightly 600s 包装补齐（D-052 精修）。锁回退 pytest 8.4.2 如实记录（venv 实跑 9.2.0，双版本均全绿；约束方未定位，r140+ 候选 override）。锁回退坑 1 条入册（244 / open 3 / closed 217 / archived 24）。下一轮（round-140）见第 101 条。
>
> round-138 收官（2026-11-12）：**评审质量门禁落地**（v2.40.0，测试 **713→723**、脚本 **83→84**）。review-quality-gate.py 四项检查 + judge 前置硬校验 rc=1（D-053 对策）；r114 真批过门禁、judge 真数据回归 F1 逐位一致；反向验证两条全绿。D-052 判红首秀：run2 首跑 678.4s（负载慢跑）触 600s 护栏判红，空载补跑 503.6s 过——护栏抓红能力实证。台账 243 / open 2 / closed 217 / archived 24。下一轮（round-139）见第 100 条。
>
> round-137 收官（2026-11-12）：**归因修正轮 + 九轮升级路线登记**（v2.39.0，测试 **713 不变**、脚本 **83 不变**）。D-053 落地：r132 归因「host 文件协议不胜任此语料」修正为「执行会话未实质评审」——README/PROGRESS 四处对外口径行改因果表述，对外数字不变；全仓「不胜任」清零。路线登记 next-round 98-106（r138 门禁 / r139 供应链+CI / r140 第三方 judge / r141 口径事实源 / r142 分级收官 / r143 沿革瘦身 / r144 变异测试 / r145 host 跨平台）。开局前先行修正 r136 遗留台账漂移（README 两处 241→242）。台账不变（242 / open 1 / closed 217 / archived 24）。下一轮（round-138）见第 99 条。
>
> round-136 收官（2026-11-11）：**依赖刷新第七跑——零升级**（v2.38.0，测试 **713 不变**、脚本 **83 不变**）。14 tracker 项镜像 dry-run（--refresh 真网络复验）全 no changes；三引擎矩阵零漂移（管道直比瞬时伪影教训：对比一律以落盘产物为准）。管道直比伪影 1 坑入册（242 / open 1 / closed 217 / archived 24）。下一轮（round-137）见第 97 条。
>
> round-135 收官（2026-11-10）：**D-052 B+C 落地（v2.37.0，测试 **713 不变**、脚本 **83 不变**）**。
> release-gate REDLINE_SEC=600 升格为判红挂死护栏（fixture 601.313s → FAIL，入仓 fixtures-r135）；
> CI nightly ubuntu `timeout 600`、windows timeout-minutes: 45 兜底；升级触发线 450→540s（D-052 批注生效）。
> 双跑 404.787 / 383.681 秒（< 600s 且 < 450s）。台账 241 / open 0 / closed 217 / archived 24。
> 下一轮（round-136）见第 96 条。
>
> round-134 收官（2026-11-10）：**D-041 触线复盘 writeup——D-052 提案（v2.36.0，测试 **713 不变**、脚本 **83 不变**）**。
> 双窗口窝口（r111–117、r126–131）零处置；600s 护栏未落地（r115/r117 >600s 仍绿）；
> D-052 候选 A/B/C（建议 B+C）——**总监裁决前不改任何阈值与代码**。
> 双跑 409.999 / 363.581 秒（< 450s，各 1 skip）。台账 241 / open 0 / closed 217 / archived 24。
> 下一轮（round-135）见第 95 条。
>
> round-133 收官（2026-11-10）：**全局口径一致性收尾（v2.35.0，测试 **713 不变**、脚本 **83 不变**）**。
> 前向口径 6 处 + 占位填充 5 处 + 勘误 4 处修正；不动代码、不动口径系数、历史口径不重写（带标记勘误）。
> 双跑 426.089 / 409.668 秒（< 450s）。台账 241 / open 0 / closed 217 / archived 24。
> 下一轮（round-134）见第 94 条。
>
> round-132 收官（2026-11-10）：**SWRBench host arm n=1000 真· 全量跑——recall=0 host-unavailable（v2.34.0，测试 **713 不变**、脚本 **83 不变**）**。
> 1000/1000 prompts → findings=0 → mechanical judge：PR fn=500 / point fn=713；recall=0.0；clean 500/500 零误报。
> README 评测能力表定调：硬规则臂 0.42% 为唯一对外口径；宿主臂 unavailable（**host-file-protocol 不胜任此语料**）。
> **勘误（round-137，D-053）**：「host-file-protocol 不胜任此语料」归因修正——全空响应=执行会话未实质评审（非协议缺陷），协议链路可用性由 r114 批证明（PR F1 0.5789，reports/reviewbench/swrenbench-r114.md）；对外数字不变。
> 双跑全绿 416.966 / 394.449 秒。台账 241 / open 0 / closed 217 / archived 24。下一轮（round-133）见第 93 条。
>
> round-131 收官（2026-11-10）：**SWRBench review arm stride-20 × 50**（v2.32.0，测试 **713 不变**、脚本 **83 不变**）。
> 50 新样本 host 判卷全 []；fn=25/point fn=31；clean 25/25 零误报。不外推能力。
> 累计 n=80/1000；继续续跑累计 1000；双跑全绿 510.521 / 460.856 秒。台账 241 / open 0 / closed 217 / archived 24。
> 下一轮（round-132）见第 92 条。
>
> round-130 收官（2026-11-10）：**SWRBench review arm stride-50 批（n=20/1000，契约 713 不变）**。
> 宿主判卷 10 clean + 10 有 gt PR 全判 []；full F1=null，零发现=docs 型样本偏差（不外推能力）。
> 下一步：stride 50 × 继续 17 批续跑；关键发现 F1 累计后决定是否继续。
> 双跑全绿 519.747 / 471.923 秒。台账 241 / open 0 / closed 217 / archived 24。下一轮（round-131）见第 91 条。
>
> round-129 收官（2026-11-10）：**SWRBench review arm smoke**（v2.31.0，测试 **713 不变**、脚本 **83 不变**）。
> 10 个 PR 端到端 smoke：host 协议 → 10 prompts → 宿主判卷 10/10 = [] → mechanical judge（PR fn=5 / point fn=7 / clean 5 完好）。
> 不外推 SWRBench 指标；全量 n=1000 已于 round-132 跑毕（PR fn=500 / point fn=713 / recall=0.0，host-unavailable）；对外唯一口径见 README。
> 双跑全绿 474.846 / 475.514 秒。台账 241 / open 0 / closed 217 / archived 24。下一轮（round-130）见第 90 条。
>
> round-128 收官（2026-11-10）：**依赖刷新第六跑**（v2.30.0，测试 **713 不变**、脚本 **83 不变**）。tree-sitter 0.26.0→0.26.1 补丁；pytest 9.2.0 维持（拒绝 8.4.2 降级）；清华镜像一次命中、零降级；三矩阵 JSON 全等价（ruff 970/480/250 identical）；台账 open 0（round-127 尾巴 f2cbdd9 全部 8 条结案）。double suite 450.510 / 455.260 秒。台账 241 / open 0 / closed 217 / archived 24。下一轮（round-129）见第 89 条。
>
> round-127 收官（2026-11-10）：**README 按参考仓标准重构**（v2.29.0，测试 **713 不变**、脚本 **83 不变**）。参考 `C:/Users/<user>/Desktop/自动化报告生成系统/README.md`，重构为 hero 一句话 + 能力边界 + 按角色选读 + 架构调用链 + ADR + 配置单一事实源 + 门禁边界（四项未验证）+ 已知限制（n=20 不外推）。只留常青真值；逐版流水指向 PROGRESS/BASELINE-HISTORY。doc-structure/doc-drift/freshness 全绿。double suite 557.111 / 473.188 秒。台账不变（241 / open 8 / closed 209）。下一轮（round-128）见第 88 条。
>
> round-126 收官（2026-11-09）：**workspace.py 覆盖率收敛**（v2.28.0，测试 **699→713**（+14）、脚本 **83 不变**）。test_agent.py::TestWorkspaceFakeBackends +14（fake 子进程、零真 docker/ssh）：远程（prepare 快乐/失败、read/write 失败、exists、_git 默认 worktree）+ 容器（运行短路、run -d→exec→detect、run 失败、exec 闭包 rm -f 再抛）。workspace.py 64.54→**71.47**%。double suite 450.334 / 475.650 秒。台账不变（241 / open 8 / closed 209）。下一轮（round-127）见第 87 条。
>
> round-125 收官（2026-11-09）：**precision-report.py 覆盖率收敛**（v2.26.0，测试 **694→699**（+5）、脚本 **83 不变**）。tests/test_scripts_precision_report.py：_load_real（defect_class 覆盖矩阵按真实 schema 核验，sample_id==fix_commit）/ _aggregate_real（跨仓合并 recall=grounded/valid、precision=grounded/claimed、分母零→None）。precision-report.py 36.07→**51.14%**，overall **78.46%**。开局闸流程偏差如实入账（先改码开闸 → stash/pop 后最终树 measure/双跑全绿、close 6/6 全绿）。double suite 414.151 / 409.522 秒。台账不变（241 / open 8 / closed 209）。下一轮（round-126）见第 86 条。
>
> round-124 收官（2026-11-09）：**review_gate.py 覆盖率收敛**（v2.25.0，测试 **690→694**（+4）、脚本 **83 不变**）。补 4 条错误路径契约：_review_gate 缺 edits.patch / 干净检出 apply 失败（清理 worktree）/ 非 git 仓库 / _parse_review_cmds 缺 `=`。review_gate.py 63.64→**93.94%**，overall **78.17%**；check PASS。double suite 375.056 / 369.369 秒。台账不变（241 / open 8 / closed 209）。下一轮（round-125）见第 85 条。
>
> round-123 收官（2026-11-09）：**report-adapter.py 覆盖率收敛**（v2.24.0，测试 **690 不变**、脚本 **83 不变**）。test_report_adapter.py（12 条契约）纳入固定五项子集：report-adapter.py 66.67→**89.39%**，overall 77.81→**78.08%**；按 r120/r122 先例重切基线（旧基线留档 reports/coverage-round123/）；check 复测 PASS（new_files=0）。先开轮再改码纪律已执行（git stash 后 open 全绿再 pop）。双跑全绿 354.590 / 354.818 秒。台账不变（241 / open 8 / closed 209）。下一轮（round-124）见第 84 条。
>
> round-122 收官（2026-11-09）：**覆盖率漂移收敛 + 台账入册**（v2.23.0，测试 **689→690**（+1）、脚本 **83 不变**）。runner.py 固定子集覆盖 85.22→**86.72%**（r105 接线块补测）；doc-freshness.py 已于 r120 入账；measure 77.81%（基线 77.85%，容差内）；new_files=1：report-adapter.py 首次可见（信息登记）。套件日志字节事故入坑台账（口径纪律，open，本轮自报）。首跑红仅 F5 口径提示（690 vs 文档 689）已校准。double suite 383.126 / 376.355 秒（两跑均线内）。台账 **241 / open 8 / closed 209**。下一轮（round-123）见第 83 条。
>
> round-121 收官（2026-11-09）：**权威源文档体系统一维护轮**（v2.22.0，测试 **688→689**（+1）、脚本 **83 不变**）。BASELINE.md / GLOSSARY.md 补「不是权威」第八元字段；doc-structure META_FIELDS 扩为八字段并全仓 PASS（19 文件）；test_doc_structure +1 反向红例；DECISIONS.md 头部决策索引目录表（D-001..D-051，D-049 双条区分）。冻结层 HISTORY 审计后不动。首跑双红在 freshness F5，688→689 校准后全绿（413.339 / 412.213 秒）。台账不变（240 / open 7 / closed 209）。下一轮（round-122）见第 82 条。
>
> round-120 收官（2026-11-09）：**覆盖率常态出数 + 基线重切**（v2.21.0，测试 **688 不变**、脚本 **83 不变**）。三子集 measure→check 判 file 级 REGRESSION（provider.py 94.25→83.11，r118 SSRF 加固子集未触达）；DEFAULT_TESTS 扩为四项（+test_provider_ssrf.py，增量 0.6s），重测 overall **77.85%**、provider **95.27%**；按 r89 先例重切入仓基线（旧基线留档 reports/coverage-round120/），check 复测 PASS；runner.py 85.22%（r105 接线未覆盖）/ doc-freshness.py 83.23% 如实入账。double suite 453.019 / 406.188 秒。台账不变（240 / open 7 / closed 209）。下一轮（round-121）见第 81 条。
>
> round-119 收官（2026-11-09）：**依赖刷新第五跑——7 项小升 + pytest 降级拒绝 + 引擎矩阵零漂移**（v2.20.0，测试 **688 不变**、脚本 **83 不变**）。清华镜像逐项核对 18 跟踪项：click/pandas/tzdata/python-dateutil 4.0.0 等 7 项升级；pytest 9.2.0→8.4.2 降级被拒（pynguin 0.48.0 元数据 pytest<9 触发的解析器提案；单独 dry-run 无变更；r110 裁决维持）；--refresh 复验 ruff/pytest/hypothesis 零变化；三矩阵 JSON 全等价。接手后双跑日志一度损毁（PowerShell UTF-16 落盘 + GBK→utf-16 误判重写），按 r117 口径 cmd /c 全套重跑，同绿 436.193 / 395.945 秒。台账不变（240 / open 7 / closed 209）。下一轮（round-120）见第 80 条。
>
> round-118 收官（2026-11-09）：**安全加固批次 + OTel GenAI 双写**（v2.19.0，测试 **653→688**（+35）、脚本 **83 不变**）。SSRF 302 逐跳复验 + DNS 逐 IP 复核 + 响应体 4MB 封顶；Action 表达式一律 env 中转（base_ref/--repo 补漏）+ github-poster 内网/保留段默认拒绝；MCP 协议版本 2024-11-05→2025-06-18 + 12 工具 annotations；trace gen_ai.* 四键双写 + span_name 映射（B1-06）；B1-02 env 哨兵 + _pid_alive 显式 mbcs；provider SSRF 补契约 +20、workflow 注入防线 +3、trace 契约 +7。上一交接点乐观计数（663）经 F5 拦截校准（665→补测 688）。双跑全绿 438.011 / 422.181 秒。台账不变（240 / open 7 / closed 209）。下一轮（round-119）见第 79 条。
>
> round-117 收官（2026-11-08）：**依赖刷新第四跑——零升级**（v2.18.0，测试 **653 不变**、脚本 **83 不变**）。11 跟踪项镜像 dry-run（含 --refresh 绕缓存复验）全 no changes；引擎矩阵口径（970/480/250 + 2/2/2 + 29 条）零漂移。台账不变（240 / open 7 / closed 209）。下一轮（round-118）见第 78 条。
>
> round-116 收官（2026-11-08）：**判卷归一化 + 依赖盘点先行**（v2.17.0，测试 **652→653**、脚本 **83 不变**）。_dedupe_gt 同片段归一化为组（r115 坑对策闭环），重判 19 PR：组口径 F1 0.6122，member_ref recall 0.5312 与机械一致；REVIEW_LLM_* 全 unset 第三方 judge 不可行（如实探测）。台账不变（240 / open 7 / closed 209）。下一轮（round-117）见第 77 条。
>
> round-115 收官（2026-11-08）：**LLM-judge 语义命中臂**（v2.16.0，测试 **648→652**、脚本 **83 不变**）。judge --match semantic（自评 rubric，19 PR 判卷零 unparsed）；对齐分母后机械 0.6296 ≈ 语义 0.6154——本批行号偏移折损 ≈ 0，r114 机械偏低猜想被否定。判卷不一致噪声 1 处入册（+1 坑，240 / open 7 / closed 209）。下一轮（round-116）见第 76 条。
>
> round-114 收官（2026-11-08）：**P0 延伸 SWRBench 宿主评审臂**（v2.15.0，测试 **642→648**、脚本 **83 不变**）。review/judge 子命令（host 文件协议跑批 + 双级 F1）；首批 stride-10 n=100：PR 级 F1 0.5789 / point 级 0.3656（对标登记值 59.4%/36.2% 量级吻合，n=100 不外推）。1 宿主响应 JSON 损坏如实计 unparsed；无结案（239 / open 6 / closed 209）。下一轮（round-115）见第 75 条。
>
> round-113 收官（2026-11-08）：**P0-3 GitHub 集成闭环**（v2.14.0，测试 **638→642**、脚本 **82→83**）。github-poster.py（评论包 → 行内评论，token 环境变量、422 如实、dry-run）+ review.yml Action 模板（不自建 App）。P0 三项至此全落地：sb-cli 通路 / 中立基准 / GitHub 闭环。无结案（237 / open 4 / closed 209）。下一轮（round-114）见第 74 条。
>

> round-112 收官（2026-11-07）：**P0-2 SWRBench 中立语料接入**（v2.13.0，测试 **633→638**、脚本 **81→82**）。swrenbench-import.py 全量接入 1000 例零坏行；确定性评审器中立首跑 point_recall 0.42% / clean 零噪声 97.4%（中性基线）；LLM 评审臂（对标行业 F1）留待下轮。无结案（237 / open 4 / closed 209）。下一轮（round-113）见第 73 条。
>

> round-111 收官（2026-11-07）：**P0-1 sb-cli 导出通路**（v2.12.0，测试 **630→633**、脚本 **81 不变**）。live-sample --export-sbcli：f2p_passed/resolved → 官方 predictions JSONL（字段对齐，missing 如实，states 副档）；v108 三例真冒烟 3/3 导出，predictions 就绪待官方远端评测（submit 为操作员动作，token 走环境变量）。无结案（237 / open 4 / closed 209）。下一轮（round-112）见第 72 条。
>

> round-110 收官（2026-11-07）：**依赖刷新第三跑——pytest 9 重议落地**（v2.11.0，测试 **630 不变**、脚本 **81 不变**）。pytest 8.4.2→9.2.0（镜像 dry-run 实测），630 契约全绿；其余九项已最新；引擎矩阵口径不变（970/480/250 + 29/2/2 + 2）。无结案（237 / open 4 / closed 209）。下一轮（round-111）见第 71 条（P0-1 sb-cli 通路）。
>

> round-109 收官（2026-11-07）：**维护轮——CI nightly 切 xdist + r110 盘点先行**（v2.10.0，测试 **630 不变**、脚本 **81 不变**）。D-051 批 A 四轮顺延后落地：pytest -n 2 双验证 301.23s / 268.94s 全绿（提速约 43%），nightly 命令切换，PR smoke 口径不变；本地闸证据链保持顺序双跑。r110 依赖盘点先行（12 项已装真值 + 探测降级记录）。无结案（237 / open 4 / closed 209）。下一轮（round-110）见第 70 条。
>

> round-108 收官（2026-11-07）：**verified django 续批——3/3 f2p_passed**（v2.9.0，测试 **630 不变**、脚本 **81 不变**）。django-11095/11099/11119 全 f2p_passed（纯自研 host 轴零 blocked，F2P 5/5 标签）——时代表红利连续第二批；venv-base 免 -e 复用流程固化。verified 累计 f2p_passed **9 例**（部分口径单列）。无结案（237 / open 4 / closed 209）。下一轮（round-109）见第 69 条。
>

> round-107 收官（2026-11-07）：**verified 350 候选批首跑——3/3 f2p_passed**（v2.8.0，测试 **628→630**、脚本 **81 不变**）。django-10554/11066/11087 全 f2p_passed（纯自研 host 轴零 blocked）——r106 选批工具直接兑现（r103 同源 0/3 → 3/3）；runtests 判分器补 docstring 折行格式（11087 实踩）；era venv 改每实例隔离。verified 累计 f2p_passed 6 例（部分口径单列）。无结案（237 / open 4 / closed 209）。下一轮（round-108）见第 68 条。
>

> round-106 收官（2026-11-07）：**F2P 质量预检 + 10880 选批**（v2.7.0，测试 **621→628**、脚本 **80→81**）。f2p-quality.py 纯静态四检查扫官方全池 500 例：ok 373 / blocked 127（prose 107 + 文件孤儿 22）；10880 候选 350 例。10973 类 prose 标签闸前静态拦截（r103 实跑坑前移）；C2 疑点如实标需 prepare 确认。无结案（237 / open 4 / closed 209）。下一轮（round-107）见第 67 条。
>

> round-105 收官（2026-11-07）：**report-adapter 深化——runner/MCP 接线**（v2.6.0，测试 **616→621**、脚本 **80 不变**）。runner --report-style 透传（双闸通过后生成 report-<style>.md 变体，适配失败 fail-soft 降级不阻断交付）；MCP code_review_run 增可选 report_style（向后兼容不破约）；adapter spec 枚举加载期校验（rc2）。无结案（237 / open 4 / closed 209）。下一轮（round-106）见第 66 条。
>

> round-104 收官（2026-11-07）：**报告输出适配器——三维度风格 spec**（v2.5.0，测试 **609→616**、脚本 **79→80**）。report-adapter.py 读 findings JSON + 风格 spec（detail_level/audience/industry，叠加 max_findings/min_severity），按受众渲染（management 摘要 / auditor 取证链 / engineering 全文），severity 过滤 + 截断，行业术语映射 finance/healthcare/gaming；与 runner step10 解耦，任何 findings 形状输入可用。无结案（237 / open 4 / closed 209）。下一轮（round-105）见第 65 条。
>

> round-103 收官（2026-11-07）：**verified django 系续批——
> 3/3 blocked_data**（v2.4.0，测试 **609 不变**、脚本 **79 不变**）。
> gate-v103（django 10914/10973/10999）全 blocked_data——F2P 注释质
> 量不一（模块不一致/描述文本/base_commit 不匹配）；era 适配表完全
> 复用红利实证（零新增适配，收集全通）。建议后续按 10880 模式选批
> 或 F2P 数据质量预检。无结案（237 / open 4 / closed 209）。下一轮（round-104）见第 64 条。
>

> round-102 收官（2026-11-07）：**verified 续——django-10880
> f2p_passed + runtests 判分口径落地**（v2.3.0，测试 **609 不变**、
> 脚本 **79 不变**）。django-10880 纯自研 1 跳收敛（DISTINCT 后缺
> 空格，+1/−1）；runtests 判分口径（原标签直喂 runtests.py + unittest
> -v 2 全点分名含括号子串匹配判分）解锁 verified django 系 231 例
> 判分通路。verified 首批终态：3 判 f2p_passed + 2 blocked（折损
> 40%）。零反馈 3/7 不变 + gold-assisted 3 + 纯自研 host 2。无结案
> （237 / open 4 / closed 209）。下一轮（round-103）见第 63 条。
>

> round-101 收官（2026-11-07）：**django-runner 节点格式转换——
> 四层推进验证**（v2.2.0，测试 **606→609**、脚本 **79 不变**）。
> live-sample `_normalize_django_nodes` 落地（格式转换机械解析 +
> run_one 前端统一归一化）；django-10880 四层推进实证（转换/收集/
> era 依赖/settings 全通），最终阻在 django 2.2 自有测试基建需
> runtests.py 引导（django.setup()）→ blocked_env 入档，解锁路径=
> runtests 引导判分设计（提案级）。契约 +3（转换/保留/不可解析）。
> 无结案（237 / open 4 / closed 209）。下一轮（round-102）见第 62 条。
>

> round-100 收官（2026-11-07）：**P1-6 依赖刷新第二轮——hypothesis
> 补丁 + xdist 落地**（v2.1.0，测试 **604→606**、脚本 **79 不变**）。
> hypothesis 6.170.15 + pytest-xdist 3.8.0 新增（D-051 批 A；pyproject
> dev + 许可注册表登记）；pytest 9 重议未获回应按建议默认维持 8.4.2
> （round-110 再议）；xdist 前置验证性测试 2 例落地（2 worker 并行
> 6.2s 全绿无互删，D-051 审计 4 阻塞点实证关闭）；三引擎矩阵复验
> 零漂移。计数传播第三次实踩（freshness 拦下）。无结案（237 / open 4
> / closed 209）。下一轮（round-101）见第 61 条。
>

> round-99 收官（2026-11-07）：**verified 首批开跑——n=5**
> （v2.0.0，测试 **604 不变**、脚本 **79 不变**）。gate-v99：
> seaborn-3069 **f2p_passed**（F2P 2/2，Nominal._finalize 基建 +
> plot 接线，0.13.0 对照=gold-assisted）+ flask-5014 **f2p_passed**
> （F2P 1/1，Blueprint 空名 ValueError，纯自研）+ 3 blocked（astropy
> hypothesis 钉入待查 / django F2P 节点格式缺口 / requests py2
> vendored）；折损 3/5=60% 与评估预测一致。**判分链缺口留观**：
> django-runner 节点格式转换（解锁 verified django 231 例）。无结案
> （237 / open 4 / closed 209）。下一轮（round-100）见第 60 条。
>

> round-98 收官（2026-11-07）：**D-051 三项裁决入账 + verified
> 评估 + xdist 前置审计**（v1.99.0，测试 **604 不变**、脚本 **79
> 不变**）。裁决（选项制收集）：e2e 提案批 B+A（xdist 列 round-100，
> 审计先行）；扩样批「先评估 verified」；round-100 按锚点。
> verified-eval-r98.md：500 实例入库（hf-mirror ✓），**排除口径成
> 核心裁定项**（仓级排除在 verified 上排除 457/500；建议中档池
> ~447/12+ 仓），开跑仍待批口径与 n 值；proposal-xdist-audit-r98.md：
> 4 阻塞点有条件可行。无结案（237 / open 4 / closed 209）。
> 下一轮（round-99）见第 59 条。
>

> round-97 收官（2026-11-07）：**预备轮——round-100 依赖盘点 +
> e2e 慢项提案**（v1.98.0，测试 **604 不变**、脚本 **79 不变**）。
> 预备盘点（只读 dry-run）：pytest 9.2.0 大版本 + hypothesis 6.170.15
> 补丁待 round-100 裁决，引擎层 7 件全最新；e2e 慢项提案
> reports/proposal-slow-test-r97.md（top-15 全为多步异构流程，D-049 C
> 合并不适用；建议 B 维持现状 + A pytest-xdist 列入 round-100 议程，
> 需审计 tmpspace/夹具单例并行正确性）；smoke 对账复跑 200/200 全过
> 21.1s。无结案（237 / open 4 / closed 209）。下一轮（round-98）见
> 第 58 条。
>

> round-96 收官（2026-11-07）：**D-045 扩样第二连跑——池末双例**
> （v1.97.0，测试 **603→604**、脚本 **79 不变**）。gate-r96：
> xarray-3364 **f2p_passed**（F2P 2/2，concat 缺变量跳过收集）+
> pylint-5859 **f2p_passed**（F2P 1/1，fixme 正则前瞻边界）；**口径=
> gold-assisted**（发布版对照，r73 先例），零反馈累计 3/7 不变 +
> gold-assisted 新列 2 例；derive 产品修正落地（官方 F2P 不覆写，
> 契约 +1）。**池见底**：本地 lite 可判实例全部消费，续池需换语料
> 源（总监决策项）。无结案（237 / open 4 / closed 209）。
> 下一轮（round-97）见第 57 条。
>

> round-95 收官（2026-11-07）：**文档整理优化——三处分卷**
> （v1.96.0，测试 **603 不变**、脚本 **79 不变**）。ROADMAP §5 分卷
> （1383→287 行，沿革卷 ROADMAP-HISTORY.md 1109 行，round-gate 兼容
> 回退两卷）；next-round 分卷（1167→89 行，第 1-45 号已执行项随 git
> 历史保留，D7 唯一事实源不变）；
> GLOSSARY +8 术语、INDEX/07-tasks 导航刷新。无结案（237 / open 4 /
> closed 209）。下一轮（round-96）见第 56 条。
>

（2026-11-07）：**D-045 扩样真连跑——宿主会话模型轴**
> （v1.95.0，测试 **603 不变**、脚本 **79 不变**，产品代码零改动）。
> gate-r94 三新仓：seaborn-2848 **f2p_passed**（F2P 1/1，越界 hue 零色
> 保行对齐修法）+ flask-4045 **f2p_passed**（F2P 2/2，assert→ValueError
> + Blueprint 名点检查）+ requests-1963 **env_blocked**（py2 vendored
> 布局，不补位）；**零反馈口径累计 3/7**（partial 单列不折算）；
> 模型轴=host 会话模型（总监派工），与端点轴分开记账；era 适配表
> 增补（mpl/werkzeug/pytest 钉版 + -p no:warnings）。无结案（237 /
> open 4 / closed 209；worktree 相对路径坑入册留观）。
> 下一轮（round-95）见第 55 条。
>

46. [路线] **P0/P1 改进队列（round-86 大幅清账）**——已落地：
    P0-2 gate-run.py（r85）、P1-3 code-task 拆分、P1-4 文档分卷、
    P1-5 bump-version、P1-6 依赖刷新纪律、P2-9 信任边界条款；提案
    待裁决：P2-7 D-049 分层套件；**仍待总监资源：P0-1 模型轴端点**
    （deepseek-chat 档或换家族——语料面/工具面已全就绪，扩样只差
    端点）；后续候选：P1 剩余=审查报告第 3-5 条的后续深化（runner.py
    与会话工作流的对齐）。

47. [路线] **round-87 开局：三选一**（round-86 新增）——①若提供
    deepseek-chat 档端点：扩样（r80 选批流程池余 269 + gate-run 单
    命令链，D-045 全流程）；②D-049 分层套件若获批：落地 smoke/full
    拆分；③无资源则维护轮或 P1 剩余项（runner.py 对齐）。key 轮换
    检查（收官检查单第 1 条）。

48. [路线] **round-88 开局：三选一**（round-87 新增）——①若提供
    deepseek-chat 档端点：扩样（r80 选批流程池余 269 + gate-run 单命令
    链，D-045 全流程）；②D-049 分层套件若获批：落地 smoke/full 拆分；
    ③无资源则维护轮：依赖刷新（P1-6 纪律，round-90 首跑前可提前）、
    test_scripts.py 巨石拆分（r85 评审 P2-8）或 round-gate close 闸的
    实战校准。key 轮换检查（收官检查单第 1 条）。

49. [路线] **round-89 开局：三选一**（round-88 新增）——①若提供
    deepseek-chat 档端点：扩样（r80 选批流程池余 269 + gate-run 单命令
    链，D-045 全流程）；②D-049 分层套件若获批：落地 smoke/full 拆分
    （585 项全量 ~6.5 分钟，拆分后分层收益更明确）；③无资源则维护轮：
    覆盖率常态出数（r85 评审 P2-8 余项：coverage-gate 数值无常态出数）、
    或 BASELINE-HISTORY/DECISIONS 索引化。P1-6 依赖刷新正式首跑在
    round-90（专属轮，勿提前合并其他项）。key 轮换检查（收官检查单
    第 1 条）。

50. [路线] **round-90 开局：P1-6 依赖刷新专属轮**（round-89 新增）——
    按 DEVELOPMENT §3 条款执行：除本项外不做其他例行动作；盘点
    pyproject 三类依赖与许可证白名单（清华 PyPI 优先，缺包按降级顺序
    记录）；升级须重跑全量套件双跑 + 引擎矩阵重测（970/480/29 规则
    口径），矩阵漂移即回滚；盘点结果入轮报（已更新/维持/受阻+原因），
    无自动升级。key 轮换检查（收官检查单第 1 条）。

51. [路线] ~~round-91 开局：三选一~~（round-90 新增；已被 D-050 总监派工
    取代——round-91 实为文档三层重构，见本单 round-91 收官行）。

52. [路线] **round-92 开局：三选一**（round-91 新增）——①若提供
    deepseek-chat 档端点：扩样（r80 选批流程池余 269 + gate-run 单命令
    链，D-045 全流程）；②D-049 分层套件若获批：落地 smoke/full 拆分
    （597 项全量 ~6.7 分钟）；③无资源则维护轮：DECISIONS.md 索引化
    （D-001..D-050 目录表，D-049 已裁决仍待）、或 D-050 后续轮统一
    权威源元信息块（INDEX 已豁免登记）、或 round-gate close 闸经验
    继续校准。下次依赖刷新锚点 round-100（专属轮）。
    key 轮换检查（收官检查单第 1 条）。

53. [路线] **round-93 开局：三选一**（round-92 新增）——①若提供
    deepseek-chat 档端点：扩样（r80 选批流程池余 269 + gate-run 单命令
    链，D-045 全流程）；②维护轮：权威源文档元信息八字段补齐（D-050
    尾项）+ doc-structure 扫描面扩权威源、或 CI smoke 时长对账首跑
    （验证 ≤2.5 分钟口径）、或 e2e 慢项瘦身（round-91 画像 top3：
    runner_material_redacted 19.4s / host_mode_pause 15.8s / runner_e2e
    13.3s，属多步流程非循环，须另行提案）。D-049 对账锚点 round-112
    （smoke 清单 full 复核）。下次依赖刷新锚点 round-100。key 轮换
    检查（收官检查单第 1 条）。

54. [路线] **round-94 开局：三选一**（round-93 新增）——①若提供
    deepseek-chat 档端点：扩样（r80 选批流程池余 269 + gate-run 单
    命令链，D-045 全流程）；②维护轮：e2e 慢项瘦身提案（round-91
    画像 top3：runner_material_redacted 19.4s / host_mode_pause
    15.8s / runner_e2e 13.3s——多步流程非循环，须总监批准预算后再
    动）、或 round-100 依赖刷新预备与 D-049 对账复跑。D-049 对账
    锚点 round-112；依赖刷新锚点 round-100。key 轮换检查（收官
    检查单第 1 条）。

55. [路线] **round-95 开局：三选一**（round-94 新增）——①宿主模型轴
    继续扩样（gate-r94 流程已固化：选批→冻结→derive→源取→prepare→
    基线→host 循环→判分；池余 ~21 仓可选；derive 覆写官方 F2P 的
    产品修正可顺路做）；②维护轮：round-100 依赖刷新预备（提前盘点）
    或 e2e 慢项瘦身提案；③D-049 对账复跑（smoke 清单 full 复核提前
    演练）。D-049 对账锚点 round-112；依赖刷新锚点 round-100。key
    轮换检查（收官检查单第 1 条）。

56. [路线] **round-96 开局：三选一**（round-95 新增）——①宿主模型轴
    继续扩样（gate-r94 流程固化，池余 ~21 仓；derive 覆写官方 F2P 的
    产品修正可顺路做）；②维护轮：round-100 依赖刷新预备或 e2e 慢项
    瘦身提案；③D-049 对账复跑演练。D-049 对账锚点 round-112；依赖
    刷新锚点 round-100。key 轮换检查（收官检查单第 1 条）。

57. [路线] **round-97 开局：三选一**（round-96 新增）——①续扩样需
    总监决策语料源（SWE-bench-verified / 与历史批次换算），或对
    gold-assisted 口径做零反馈复跑（xarray/pylint 重置 worktree 后
    宿主盲修）；②维护轮：round-100 依赖刷新预备（提前盘点清单）；
    ③e2e 慢项瘦身提案（须总监批预算）。D-049 对账锚点 round-112；
    依赖刷新锚点 round-100。key 轮换检查（收官检查单第 1 条）。

58. [路线] **round-98 开局：三选一**（round-97 新增）——①若总监对
    proposal-slow-test-r97（B+A）与语料源换批做裁决：按裁决执行；
    ②维护轮：round-100 依赖刷新预备第二轮（盘点 → 冻结面预演）、或
    宿主模型轴零反馈复跑实验设计（口径学价值评估先行）；③D-049
    对账锚点 round-112 前的 smoke 清单审计演练。依赖刷新锚点
    round-100。key 轮换检查（收官检查单第 1 条）。

59. [路线] **round-99 开局：二选一**（round-98 新增）——①若总监批
    verified 中档口径与 n=5：开跑 verified 首批（D-045 全流程 +
    r94/r96 era 适配表复用；django/sympy 仓适配折损预期 30-50%
    env_blocked 如实记）；②round-100 预备：xdist 阻塞点验证性测试
    先行（tests/test_xdist_audit.py，2 worker 实跑）。round-100：
    依赖刷新 + xdist 落地（若审计过）专属轮。key 轮换检查（收官
    检查单第 1 条）。

60. [路线] **round-100 开局：依赖刷新专属轮 + 两项批前遗留**
    （round-99 新增）——P1-6 正式首跑第二轮（r90 后）：pytest 9 重议、
    hypothesis 6.170.15 补丁、xdist 落地（D-051 批 A，前置审计已过
    4 阻塞点有条件可行——验证性测试 tests/test_xdist_audit.py 先行）；
    引擎矩阵重测（970/480/250 + 29 + 2 口径）；django-runner 节点格式
    转换（verified 扩样解锁项，可并入本轮或另立）。key 轮换检查
    （收官检查单第 1 条）。

61. [路线] **round-101 开局：三选一**（round-100 新增）——①django-runner
    节点格式转换落地（解锁 verified django 231 例：机械映射 module→
    file + :: 拼接，live-sample f2p 匹配口径扩展 + 契约）；②CI 命令
    切 xdist（nightly 口径改造 + 两平台矩阵回归）；③维护轮（e2e 慢项
    复测、文档保鲜）。下轮依赖刷新锚点 round-110。key 轮换检查
    （收官检查单第 1 条）。

62. [路线] **round-102 开局：三选一**（round-101 新增）——①django
    runtests 引导判分设计提案（验证性：live-sample 增 --runner runtests
    口径或 setup_cmds 注入 conftest 的合规路径论证——须过 integrity
    闸论证）；②CI 命令切 xdist（nightly 口径改造 + 两平台回归）；
    ③维护轮。下轮依赖刷新锚点 round-110。key 轮换检查（收官检查单
    第 1 条）。

63. [路线] **round-103 开局：三选一**（round-102 新增）——①verified
    继续扩样（runtests 口径已通，django 231 例可选；era 适配表复用）；
    ②维护轮：round-110 依赖刷新预备、CI 命令切 xdist、文档保鲜；
    ③e2e 慢项提案裁决执行（若总监批 A pytest-xdist）。key 轮换检查
    （收官检查单第 1 条）。

64. [路线] **round-104 开局：三选一**（round-103 新增）——①verified
    选批改造（F2P 数据质量预检工具或按 10880 模式过滤选批）；
    ②维护轮：round-110 依赖刷新预备、CI 命令切 xdist、文档保鲜；
    ③e2e 提案裁决执行。key 轮换检查（收官检查单第 1 条）。
65. [路线] **round-105 开局：三选一**（round-104 新增）——①verified
    选批改造（F2P 数据质量预检工具或按 10880 模式过滤选批）；
    ②report-adapter 深化：runner step10 --style 透传 + MCP
    code_review_run 风格参数 + 自定义 spec 校验增强；③维护轮：
    round-110 依赖刷新预备、CI 命令切 xdist、文档保鲜。key 轮换检查
    （收官检查单第 1 条）。
66. [路线] **round-106 开局：三选一**（round-105 新增）——①verified
    选批改造（F2P 数据质量预检工具或按 10880 模式过滤选批，r103 遗留建议）；
    ②维护轮：round-110 依赖刷新预备（pytest 9 重议）、CI 命令切 xdist、
    文档保鲜；③report-adapter 终章：styles/ 自定义 preset 文档化 +
    report-check 对风格变体的兼容判定（若步子小可与①合并）。key 轮换检查
    （收官检查单第 1 条）。
67. [路线] **round-107 开局：三选一**（round-106 新增）——①verified
    350 候选批起跑（verified-candidates-10880.jsonl → gate-corpus-build
    derive → gate-run prepare/run/judge；按 r99 流程 + era 适配表复用）；
    ②维护轮：round-110 依赖刷新预备（pytest 9 重议）、CI 命令切 xdist、
    文档保鲜；③report-adapter 终章（自定义 preset 文档化 + report-check
    对风格变体兼容判定）。key 轮换检查（收官检查单第 1 条）。
68. [路线] **round-108 开局：三选一**（round-107 新增）——①verified
    续批：从 350 候选再选 3-5 例（跳过已判 6 例；跨仓试 sphinx-doc/
    scikit-learn 新 era 适配或继续 django 红利）；②维护轮：round-110
    依赖刷新预备（pytest 9 重议）、CI 命令切 xdist、文档保鲜；
    ③report-adapter 终章（自定义 preset 文档化 + report-check 对
    风格变体兼容判定）。key 轮换检查（收官检查单第 1 条）。
69. [路线] **round-109 开局：三选一**（round-108 新增）——①verified
    续批第三批（django 剩余 ~160 候选或跨仓试 sphinx-doc 44 例——
    需先做 sphinx 时代表盘点）；②维护轮：round-110 依赖刷新预备
    （pytest 9 重议）、CI 命令切 xdist、文档保鲜；③report-adapter
    终章（自定义 preset 文档化 + report-check 对风格变体兼容判定）。
    key 轮换检查（收官检查单第 1 条）。
70. [路线] **round-110 开局：依赖刷新专属轮（P1-6 第三跑，锚点轮）**
    （round-109 新增）——①盘点已就位（r109：12 项已装真值；最新版探测
    改 pip install --dry-run -i 清华镜像实测，不下载二进制）；②议题：
    pytest 9 重议（r90 起维持 8.4.2）、ruff/libcst/ast-grep/hypothesis/
    coverage 按镜像实测升、引擎矩阵重测（970/480/250 + 29 + 2 口径）；
    ③备选：verified 续批或 sphinx 时代表盘点。key 轮换检查（收官检查单
    第 1 条）。
71. [路线] **round-111 起三连：行业对标 P0 执行队列**（r109 后研究简报
    brief-0867786ad184 签发，六域检索已完成）——①P0-1 sb-cli 通路：
    live-sample --export-sbcli 导出 predictions（instance_id+model_patch
    字段对齐）+ 首批 f2p_passed 样本送官方远端评测出 resolved 口径
    （round-111）；②P0-2 SWRBench 适配接入 reviewbench-eval 双轨
    （round-112）；③P0-3 github-poster.py 行内评论海报 + workflow 模板
    （round-113）；P1 Semgrep 第 4 引擎与 P2 TestGenEval 按节奏滚动。
    key 轮换检查（收官检查单第 1 条）。
72. [路线] **round-112 开局：P0-2 SWRBench 适配接入**（round-111 新增）——
    reviewbench-eval 增 SWRBench 语料适配臂（arXiv:2509.01494，
    ~1000 真实 PR；ZZR0/SWRench 数据 + ground truth 评分），与自建
    ReviewBench 双轨出数；数据走 gitee/官方源降级链 + 语料不入库
    惯例。key 轮换检查（收官检查单第 1 条）。
73. [路线] **round-113 开局：P0-3 GitHub 集成闭环**（round-112 新增）——
    ①github-poster.py（pr-kit 行内评论包 → REST POST /pulls/{n}/comments，
    token 走环境变量，commit_id/path/line 三要素）；②.github/workflows/
    review.yml 模板（pull_request + issue_comment 触发，Action 模式，
    不自建 App）；③P1 延续：SWRBench LLM 评审臂（宿主评审器跑分出 F1）。
    key 轮换检查（收官检查单第 1 条）。
74. [路线] **round-114 开局：三选一**（round-113 新增）——①P0 延伸：
    SWRBench LLM 评审臂（宿主评审器对 n=1000 出 PR 级/point 级 F1，
    对标行业 59.4%/36.2%）或 resolved 口径首批送审（sb-cli submit，
    需操作员 key）；②维护轮：文档保鲜 + round-120 依赖刷新预备；
    ③verified 续批或 sphinx 时代表盘点。key 轮换检查（收官检查单
    第 1 条）。
75. [路线] **round-115 开局：三选一**（round-114 新增）——①SWRBench 全量
    n=1000 续跑（review --stride 1，幂等缓存续跑，宿主评阅预算另批）；
    ②LLM-judge 臂（论文同款语义命中判定，与机械口径对照出行号偏移折损）；
    ③维护轮：文档保鲜 + round-120 依赖刷新预备；key 轮换检查（收官检查单
    第 1 条）。
76. [路线] **round-116 开局：三选一**（round-115 新增）——①SWRBench 全量
    n=1000 续跑（review --stride 1 幂等续跑，宿主评阅预算另批）；
    ②第三方模型 judge（消除自评循环性，需操作员 key 或开放端点）；
    ③维护轮：文档保鲜 + round-120 依赖刷新预备；key 轮换检查（收官检查单
    第 1 条）。
77. [路线] **round-117 开局：三选一**（round-116 新增）——①SWRBench 全量
    n=1000 续跑（review --stride 1 幂等续跑，宿主评阅预算另批）；
    ②第三方模型 judge（REVIEW_LLM_* 需操作员 key，r116 探测 unset）；
    ③round-120 依赖刷新执行（盘点已在 r116 备好：110 已装/18 跟踪真值；
    镜像 dry-run 逐项探测 + 引擎矩阵复核）；key 轮换检查（收官检查单第 1 条）。
78. [路线] **round-118 开局：三选一**（round-117 新增）——①SWRBench 全量
    n=1000 续跑（review --stride 1 幂等续跑，宿主评阅预算另批）；
    ②第三方模型 judge（REVIEW_LLM_* 需操作员 key，r116 探测 unset）；
    ③评审闭环实弹：对本仓自造缺陷 PR 跑 review→judge 全链（小样本
    冒烟，验证链路工程可用性）；key 轮换检查（收官检查单第 1 条）。
79. [路线] **round-119 开局：三选一**（round-118 新增）——①round-120 依赖刷新执行
    （锚点轮；盘点已在 r116 备好：110 已装/18 跟踪真值；镜像 dry-run 逐项探测 + 引擎矩阵复核）；
    ②SWRBench 全量 n=1000 续跑（review --stride 1 幂等续跑，宿主评阅预算另批）；
    ③第三方模型 judge（REVIEW_LLM_* 需操作员 key，r116 探测 unset）；
    key 轮换检查（收官检查单第 1 条）。
80. [路线] **round-120 开局：三选一**（round-119 新增）——①SWRBench 全量 n=1000 续跑
    （review --stride 1 幂等续跑；宿主评阅预算需另批）；②第三方模型 judge
    （REVIEW_LLM_* 需操作员 key，r116 探测 unset）；③维护轮：覆盖率常态出数
    （coverage-gate 数值无常态出数，r85 评审 P2-8 余项）或 BASELINE-HISTORY / DECISIONS 索引化；
    key 轮换检查（收官检查单第 1 条）。
81. [路线] **round-121 开局：三选一**（round-120 新增）——①SWRBench 全量 n=1000 续跑
    （review --stride 1 幂等续跑；宿主评阅预算需另批）；②第三方模型 judge
    （REVIEW_LLM_* 需操作员 key，r116 探测 unset）；③维护轮：BASELINE-HISTORY
    / DECISIONS 索引化（D-001..D-050 目录表）+ 权威源文档元信息八字段补齐（D-050 尾项）；
    key 轮换检查（收官检查单第 1 条）。
82. [路线] **round-122 开局：三选一**（round-121 新增）——①SWRBench 全量 n=1000 续跑
    （review --stride 1 幂等续跑；宿主评阅预算需另批）；②第三方模型 judge
    （REVIEW_LLM_* 需操作员 key，r116 探测 unset）；③维护轮：runner.py /
    doc-freshness.py 覆盖率漂移收敛（固定子集内补测试或随下轮基线一并裁定）；
    key 轮换检查（收官检查单第 1 条）。
83. [路线] **round-123 开局：三选一**（round-122 新增）——①SWRBench 全量 n=1000 续跑
    （review --stride 1 幂等续跑；宿主评阅预算需另批）；②第三方模型 judge
    （REVIEW_LLM_* 需操作员 key，r116 探测 unset）；③维护轮：技能脚本覆盖率
    常态 watch 之外——report-adapter.py 首次进入覆盖率面（66.67%），可将 report-adapter
    纳入固定子集或其各自模块补测后随下轮基线时一并裁定；
    key 轮换检查（收官检查单第 1 条）。
84. [路线] **round-124 开局：三选一**（round-123 新增）——①SWRBench 全量 n=1000 续跑
    （review --stride 1 幂等续跑；宿主评阅预算需另批）；②第三方模型 judge
    （REVIEW_LLM_* 需操作员 key，r116 探测 unset）；③维护轮：runner.py /
    doc-freshness.py 之外任何长尾 coverage（技能脚本清扫），或 BASELINE-HISTORY /
    DECISIONS 进一步索引化；
    key 轮换检查（收官检查单第 1 条）。
85. [路线] **round-125 开局：三选一**（round-124 新增）——①SWRBench 全量 n=1000 续跑
    （review --stride 1 幂等续跑；宿主评阅预算需另批）；②第三方模型 judge
    （REVIEW_LLM_* 需操作员 key，r116 探测 unset）；③维护轮：eval-harness 三角
    （agent-sample 21.83% / deepswe-sample 35.21% / precision-report 36.07%）长尾清扫
    或 coverage-gate 自身 51.27%、workspace.py 64.54% 提升（固定子集内可补测）；
    key 轮换检查（收官检查单第 1 条）。
86. [路线] **round-126 开局：三选一**（round-125 新增）——①SWRBench 全量 n=1000 续跑
    （review --stride 1 幂等续跑；宿主评阅预算需另批）；②第三方模型 judge
    （REVIEW_LLM_* 需操作员 key，r116 探测 unset）；③维护轮：eval-harness 三角余两项
    （agent-sample.py 21.83% / deepswe-sample.py 35.21%）或 coverage-gate.py 自身 51.27%
    （固定子集内可补测）或 workspace.py 64.54%；
    key 轮换检查（收官检查单第 1 条）。
87. [路线] **round-127 开局：三选一**（round-126 新增）——①SWRBench 全量 n=1000 续跑
    （review --stride 1 幂等续跑；宿主评阅预算需另批）；②第三方模型 judge
    （REVIEW_LLM_* 需操作员 key，r116 探测 unset）；③维护轮：coverage-gate.py
    自身 51.27%（固定子集内可补测的 happy/branch）或深扫技能脚本长尾
    （eval-harness 三角里 agent-sample.py 21.83% / deepswe-sample.py 35.21%，
    需要宿主 harness，若继续则持续自报）；
    key 轮换检查（收官检查单第 1 条）。
88. [路线] **round-128 开局：三选一**（round-127 新增）——①SWRBench 全量 n=1000 续跑
    （review --stride 1 幂等续跑；宿主评阅预算需另批）；②第三方模型 judge
    （REVIEW_LLM_* 需操作员 key）；③依赖盘点第六跑（round-120 锚点轮）
    （11 跟踪项此前已全零升级；可续跑）
    key 轮换检查（收官检查单第 1 条）。
89. [路线] **round-129 开局：三选一**（round-128 新增）——①SWRBench 全量 n=1000 续跑
    （review --stride 1 幂等续跑；宿主评阅预算已批，本机预算未消耗，断点续跑；本轮可直接开跑）；
    ②round-130 依赖刷新锚点（已固定为 round-129，round-128 刚完成）；
    ③SWRBench 评测完整性预检（f2p-quality.py 验 SELECT 公式/空响应可判别）
    或 release-gate 2.30.0 落 tag / push；
    key 轮换检查（收官检查单第 1 条）。
90. [路线] **round-130 开局：三选一**（round-129 新增）——①SWRBench 全量 n=1000 续跑
    （批了预算、续跑入口已就位：本轮 smoke 消化完成，
     分批 stride 100 × 10 批续跑，mechanical judge 收口）；
    ②SWRBench F2P 预检（datasets/swrenbench 子集可跑性验证）；
    ③下一次依赖刷新锚点 round-130 已过；
    key 轮换检查（收官检查单第 1 条）。
91. [路线] **round-131 开局：三选一**（round-130 新增）——①SWRBench review arm
    续跑下一 stride-50 批（每批 mechanical judge 收口，本轮全清）；
    ②如 F1 继续为零、切方案B：跑一批含 bug-fix PR 的代表性样本独立核验；
    ③依赖刷新锚点 round-140。
    key 轮换检查（收官检查单第 1 条）。
92. [路线] **round-132 开局：三选一**（round-131 新增）——①SWRBench review arm
    续跑：stride 20 × 下一批（~50 PR）；累计 130
    ②n=100+ 后若 recall 持续为 0：评估是否继续本臂（宿主文件协议无 GT 信号时量贵），
     切 F2P 评分桥/实跑桥核验；
    ③下一个 dependency refresh 锚点。
    key 轮换检查（收官检查单第 1 条）。
93. [路线] **round-133 开局：三选一**（round-132 新增）——①基于全局口径；
    ②300s 红线确认偏离 D-041 批准（writeup 触发 + release-gate 红线入参 round-128 最新），
    ③依赖刷新锚点 round-140。
    key 轮换检查（收官检查单第 1 条）。
94. [路线] **round-134 开局：三选一**（round-133 新增）——①300s 红线/D-041 处置 writeup
    （r128–r131 五连 >450s、r132/r133 双跑回落 450s 以下；是否改升级阈值属总监裁量）；
    ②依赖刷新锚点（round-140 原计划，可提前一跑）；
    ③F2P / 评分桥对标矩阵现状刷新（precision-gate 复测证据台账回血）。
    key 轮换检查（收官检查单第 1 条）。
95. [路线] **round-135 开局：D-052 裁决承接 + 例行三选一**（round-134 新增）——①总监批注 D-052（A/B/C/B+C）
    （批后执行：B= timeout 包裹 + release-gate redline_sec=600 落款 + 注入慢测反向验证；随契约轮落）；
    ②依赖刷新锚点（round-140 原计划）；
    ③F2P / 评分桥 precision-gate 复测回血。
    key 轮换检查（收官检查单第 1 条）——本轮已跑（零真实凭据，见 events-round-134.json）。
96. [路线] **round-136 开局：三选一**（round-135 新增）——①依赖刷新锚点提前执行（六月/十月依次
    第四/五/六刷新之后，第七跑 tracker 面：click/pandas/tzdata/ruff/libcst/ast-grep/pytest/hypothesis 等）；
    ②F2P / 评分桥 precision-gate 复测回血（ReviewBench 语料 + baseline + trend）；
    ③round-140 依赖刷新保持原锚 + 本轮精修 D-052 执行面（如 nightly ubuntu 超时 610→620 行注释回填，或补 windows 侧 wrapper）。
    key 轮换检查（收官检查单第 1 条）——本轮已跑（events-round-135.json）。
97. [路线] ~~round-137 开局：三选一~~ **已被 r136 收官路线吸收**（2026-11-12
    全方位审查后重排九轮路线，见 98-106 条）：①precision-gate 复测回血转
    backlog（r138 门禁落地后复测）；②D-052 执行面精修并入 r139（供应链
    锁定 + CI 面统一轮）；③评审闭环实弹冒烟并入 r138 反向验证。
98. [路线] **round-137（执行中）：归因修正轮**（2026-11-12 全方位审查新增，D-053）——
    README 两处 + PROGRESS 两处对外口径行的「host 文件协议不胜任此语料」
    改为「执行会话未实质评审（1000/1000 全空响应）；协议可用性由 r114 批
    （PR F1 0.5789，reports/reviewbench/swrenbench-r114.md）证明」；r132
    收官行勘误后缀；对外数字（0.42% 唯一对外）不动；历史记录不回改。
    验收：全仓 grep「不胜任」仅存勘误上下文；收官门六项 PASS。
99. [路线] **round-138：评审质量门禁**（D-053 对策落地）——①新脚本
    review-quality-gate.py（run/check 双动词，仿 precision-gate.py）：全 []
    批次须附 per-PR 依据字段、evidence 覆盖率阈值、unparsed 率阈值；
    ②swrenbench-import.py cmd_judge/cmd_judge_semantic 输入校验段末插前置
    硬校验（全空无依据 → rc=1 empty_batch_no_evidence，新退出码语义）；
    ③findings.json 增顶层 batch_note 字段；④反向验证样例（红线 6）+
    契约 +8 + AGENTS.md 脚本表 83→84 + coverage-baseline.json 登记；
    ⑤顺带收原 97③ 实弹冒烟。验收：造全 [] 无依据样例确认抓住；
    713→721 双跑全绿；脚本 84 处六处真值同步。
100. [路线] **round-139：供应链锁定 + CI 面**——①uv lock 生成 uv.lock 入仓；
    ②self-check.yml 改锁安装（uv sync --locked 或 export --require-hashes）；
    ③修复既有漂移：self-check.yml 依赖清单缺 tree-sitter-typescript/go；
    ④.github/dependabot.yml（pip ecosystem weekly）；⑤原 97② D-052 执行面
    精修（nightly 超时注释回填 / windows 侧 wrapper）。验收：CI 锁安装
    全绿；依赖漂移清零；LICENSE/license 门禁不变。
101. [路线] **round-140：第三方 judge 零 key 方案**（条件轮，探测先行）——
    ①探测 ollama 本地端点（REVIEW_LLM_BASE_URL=http://127.0.0.1:11434，
    走既有 loopback 白名单；模型拉取走国内镜像纪律）；②第三方模型复评
    r114 同批 19 PR 判卷；③自评/第三方对照报告（打破 r115 声明的自评
    循环）。验收：对照表两列数字 + 口径注记；探测不可用则 blocked 如实
    记录不冒充。
102. [路线] **round-141：评测口径单一事实源**——①eval-harness/eval-config.toml
    （stdlib tomllib）收双臂口径字段（分母定义/匹配规则/对外锚）；②
    swrenbench-import.py score/review/judge/quality-gate 改读配置；
    ③契约 +N。验收：改口径只动 TOML 一处；双臂 judge 数字与改前完全
    一致（回归护栏）。
103. [路线] **round-142：分级收官**——round-gate.py 增 --round-type
    full|light（light 仅豁免 suite_logs 双跑为单跑，其余五检查不减）；
    契约测试覆盖 light 路径；零代码轮改走 light。验收：light 轮收官门
    全 PASS 且双跑成本减半；full 路径行为不变。
104. [路线] **round-143：PROGRESS 沿革瘦身**——契约测试格 r102–r135 沿革
    迁出（只留当前轮 + 「沿革见 BASELINE-HISTORY/git」指针）；r102/103
    时长按「勘误式追加」补录 BASELINE-HISTORY（冻结卷只增不改）；doc
    探针同步。验收：doc-freshness/doc-structure 全绿；单元格回到
    v1.87.0 声明的纪律形态。
105. [路线] **round-144：变异测试抽检**（已修正：自研 sampler 替代 mutmut）——①~~mutmut 入 dev~~
    optional-dependencies ~~（硬约束 1 登记）~~——改为自研 stdlib 方案（见 8145337）；②
    runner/五道闸链路抽样变异验证（验证 713 契约的杀伤力，产出杀手
    分数报告）。验收：抽样模块杀手分数 ≥ 门槛建议值；未达标的契约
    补行为断言。
106. [路线] **round-145：host 协议跨平台**——provider.py host 桌面协议
    Linux 适配（CI 内可跑）+ 契约 +N。验收：Linux CI 侧 host 臂链路
    探测通过（或 blocked 如实）。
107. [路线] **round-146：OpenSSF Scorecard 对标整改**（2026-11-13 行业对标轮新增）——
    实现已先行入库：4 处 Actions SHA 钉定（checkout v4.2.2/setup-python
    v5.6.0，ls-remote 权威 SHA）+ self-check 顶层 permissions: contents:
    read + SBOM（reports/sbom/sbom-2.43.0.json，20 组件）+ Scorecard 自评
    报告（8 项 PASS / 2 项部分 / 1 项未评，SAST 缺口已补自查：astgrep 安全
    族扫自身仓安全族零命中）。收官待宿主负载恢复；候选：pip-audit CVE
    扫描进 nightly（镜像纪律）。
108. [路线] **round-147：权威手册对齐 + light 收官推广**（2026-11-13 新增）——
    实现已先行入库：复盘阶段第 3 步登记 light 收官用法（round-142 能力入
    AGENTS.md 权威源）；残留脚本数真值清理（83→85 两处，doc-freshness
    头注位盲区人工对账）。收官待宿主负载恢复。
109. [路线] **round-148：CVE 扫描闭环**（2026-11-13 行业对标轮新增）——
    实现已先行入库：pip-audit 2.10.1（OSV）审 130 包命中 7 CVE（black
    ×4/setuptools ×3，环境传递包）→ 升级修复复审计清零；nightly 增扫描
    步骤（扫描器钉 2.10.1）；Scorecard Vulnerability-Scan 缺口关闭。
    收官待宿主负载恢复。
110. [路线] **round-149：锁内 pytest 版本追查——override 实验成功**（2026-11-13
    全量推进轮新增）——实现已先行入库：[tool.uv] override-dependencies =
    [pytest>=9] 实验成功（锁干净解出 9.2.0，无冲突；与 floor 实验触发的
    semgrep 构建墙对照——override 只改选择不改约束图）；锁与 venv 分歧
    关闭；连带 coverage 7.17.3 / ruff 0.17.5 刷新，矩阵口径
    970/480/250→973/481/251 三处同步。收官待宿主负载恢复。
111. [路线] **round-150：CII Best Practices 预填自查**（2026-11-13 新增）——
    实现已先行入库：reports/cii-bestpractices-precheck.md（13 判据逐条
    映射仓内证据 + 操作员注册步骤；唯一 gap=内网 Gitea 无 https，外网
    发布时补）。操作员动作：照单注册 + 徽章回填 README。收官待负载。
112. [路线] **round-151：astgrep 适配器 WinError 206 修复**（2026-11-13 全量推进轮）——
    实现已先行入库：payload 文件传输替代 argv（Windows 32K 上限），103 文件
    SAST 全量 0 错误；18 契约全绿、矩阵逐位一致。收官待宿主负载恢复。
113. [路线] **round-152 候选**（round-151 收官登记）——①CII badge 注册
    （操作员照 reports/cii-bestpractices-precheck.md 勾选）；②第三方 judge
    （ollama 条件轮，探测先行）；③pip-audit nightly 首周观察（扫描器误报率
    与 CVE 时效性）。key 轮换检查（收官检查单第 1 条）。
114. [路线] **round-153 候选**（round-152 收官登记，已全部落地）——①event-ledger 哈希链
    接入轮流程（F4，round-153 落地）；②Gitea runner 注册与 self-check 移植
    （F2，操作员动作，仍开放）；③coverage-gate measure 重测（F6，round-153 落地）；
    ④第三方 judge（ollama 条件轮，r153 复探仍 DOWN）。
115. [路线] **round-154 候选**（round-153 收官登记，已全部落地）——①Gitea runner 注册与
    self-check 移植（F2 遗留，操作员动作）；②第三方 judge（ollama 条件轮）；
    ③CII badge 注册（操作员照单）；④pip-audit nightly 首周观察；⑤MCP 异步
    作业模式（设计稿 reports/proposal-mcp-async-r154.md，**待总监裁决**）。
116. [路线] **round-155 候选**（round-154 收官登记，①③已落地）——①MCP 异步作业实现
    （若 D-055 批准 submit/status 双工具 + jobs 资源，约一轮）；②scan SLO
    门禁化（latency-bench p95 阈值断言进 CI）**→ r155 落地（check 动词 + nightly
    接线 + 反向验证）**；③pip-audit 首周观察→ r155 落地（锁面零 CVE + venv 工具链
    soupsieve CVE 升级清零）；④CII/Gitea runner（操作员，仍开放）。
    key 轮换检查（收官检查单第 1 条）。
117. [路线] **round-156 候选**（round-155 收官登记，②③已落地）——①MCP 异步作业实现
    （D-055 待裁决，条件轮）；②SLO 门禁 nightly 首跑观察（红绿与时长对账）
    **→ r156 落地（5 runs/档实弹全 PASS，p95 0.094-0.116s 与基线一致）**；
    ③retro-report 防重跑护栏候选评估（--confirm-next 显式确认，r155 坑
    a5ba44db35ee 对策远期项）**→ r156 落地并结坑（真仓强制 --round N）**；
    ④CII/Gitea runner（操作员，仍开放）。key 轮换检查（收官检查单第 1 条）。
118. [路线] **round-157 候选**（round-156 收官登记，③已落地）——①MCP 异步作业实现
    （D-055 待裁决，条件轮）；②SLO 门禁 nightly CI 首跑观察（本地已 PASS，
    等 GitHub Actions nightly 实跑红绿）——**r157 复核：提交未推送（本地领先
    origin 8 提交），CI 未见到 r155/156 改动，条件不满足如实记录**；
    ③真仓强制 --round 的下游对账：round-gate close 对 close 面命令的约定复核
    （如有脚本化收官链路引用旧口径则同步）**→ r157 落地（MCP 面对账 + 全仓
    引用面扫余均为叙述文本）**；④CII/Gitea runner（操作员，仍开放）。
    key 轮换检查（收官检查单第 1 条）。
119. [路线] **round-158 候选**（round-157 收官登记，②已落地）——①MCP 异步作业实现
    （D-055 待裁决，条件轮）；②行数基线结构候选评估：把 SKILL.md 行数基线
    并入 doc-freshness F 面（r157 新坑对策，消「改 SKILL.md 须手动同步
    BASELINE」的手动步骤）**→ r158 落地（F10 检查 + 3 契约，坑结案）**；
    ③CII/Gitea runner（操作员，仍开放）。key 轮换检查（收官检查单第 1 条）。
120. [路线] **round-159 候选**（round-158 收官登记，②已落地）——①MCP 异步作业实现
    （D-055 待裁决，条件轮）；②F10 下游对账复核（如引 doc-freshness 判据清单
    的文档还有 F1-F9 口径处需补 F10，全仓 grep 核对）**→ r159 落地
    （DEVELOPMENT F1-F10，余留仅脚本 docstring 与冻结档案）**；③CII/Gitea runner
    （操作员，仍开放）。key 轮换检查（收官检查单第 1 条）。
121. [路线] **round-160 候选**（round-159 收官登记，②已落地）——①MCP 异步作业实现
    （D-055 待裁决，条件轮）；②suite_count_claim 首轮实战观察（r159 close 即
    首用，r160 开局复核其 PASS 证据）**→ r160 落地（首用 PASS 765==[765,765]）**；
    ③CII/Gitea runner（操作员，仍开放）；**④台账清账轮（本轮自加）：五坑取证
    结案，open 0 里程碑**。key 轮换检查（收官检查单第 1 条）。
122. [路线] **round-161 候选**（round-160 收官登记，②已落地）——①MCP 异步作业实现
    （D-055 待裁决，条件轮）；②台账零未结后的首轮：维护轮候选（依赖刷新第九跑
    ——上次刷新 r149/r150 时点，按 P1-6 纪律镜像 dry-run 逐项探测 + 引擎矩阵
    复核）**→ r161 落地（12 项探测，唯一升级 ast-grep-py 补丁级，三矩阵零漂移）**；
    ③CII/Gitea runner（操作员，仍开放）。key 轮换检查（收官检查单第 1 条）。
123. [路线] **round-162 候选**（round-161 收官登记，②已落地）——①MCP 异步作业实现
    （D-055 待裁决，条件轮）；②维护轮：540s 触发线观察复核（r160/r161 run2
    间歇越线，若续现三连则提级总监裁量 xdist worker 数）或双新检查首周观察
    收口**→ r162 落地（裁决跑 465.85/475.57s 双回落线内——间歇未三连，观察解除；
    双新检查四轮零误报收口）**；③CII/Gitea runner（操作员，仍开放）。
    key 轮换检查（收官检查单第 1 条）。
124. [路线] **round-163 候选**（round-162 收官登记，②已落地）——①MCP 异步作业实现
    （D-055 待裁决，条件轮）；②维护轮候选（依赖刷新第十跑锚点或按需提案）
    **→ r163 落地（scorecard 恢复每轮结算 + coverage 复测容差内 + 约定缺口
    登记）**；③CII/Gitea runner（操作员，仍开放）。key 轮换检查（收官检查单
    第 1 条）。
125. [路线] **round-164 候选**（round-163 收官登记，②已落地）——①MCP 异步作业实现
    （D-055 待裁决，条件轮）；②结构候选：org-scorecard 并入 round-gate close
    检查链（约定「每轮结算」机械化，+契约含反向验证；约一轮）**→ r164 落地
    （close 第八项检查 scorecard_budget，WARN 不阻断/EXCEEDED 判红，
    17 open 坑反向验证实弹）**；③CII/Gitea runner（操作员，仍开放）。
    key 轮换检查（收官检查单第 1 条）。
126. [路线] **round-165 候选**（round-164 收官登记，②已落地）——①MCP 异步作业实现
    （D-055 待裁决，条件轮）；②维护轮候选（依赖刷新第十跑锚点——r161 第九跑后
    约十轮节奏）**→ r165 改道执行 CI 门禁接线对账（doc-structure 接线 +
    mutation-sampler 登记修正 + PROGRESS L24 真值修复）**；③CII/Gitea runner
    （操作员，仍开放）。key 轮换检查（收官检查单第 1 条）。
127. [路线] **round-166 候选**（round-165 收官登记，②已落地）——①MCP 异步作业实现
    （D-055 待裁决，条件轮）；②维护轮候选（依赖刷新第十跑——r161 第九跑后第七轮，
    节奏临近可跑）或 mutation-sampler 杀手分数复跑（r144 后新增 ~19 契约的杀伤力
    抽检，按需抽检性质）**→ r166 落地（round-gate 1.0 / doc-freshness 0.1→1.0，
    +2 行为断言补盲区）**；③CII/Gitea runner（操作员，仍开放）。
    key 轮换检查（收官检查单第 1 条）。
128. [路线] **round-167 候选**（round-166 收官登记，②已落地）——①MCP 异步作业实现
    （D-055 待裁决，条件轮）；②维护轮候选（依赖刷新第十跑）**→ r167 落地
    （12/12 已最新零升级，三矩阵一致；light 收官候选）**；③CII/Gitea runner
    （操作员，仍开放）。key 轮换检查（收官检查单第 1 条）。
129. [路线] **round-168 候选**（round-167 收官登记）——①**开局首动作：r166/r167
    双跑受阻补录**（负载恢复后 light 单跑 → close 两轮 → 哈希链，日志重写
    logs/suite-r166-run1.log + logs/suite-r167-run1.log）；②维护轮候选按需；
    ③CII/Gitea runner（操作员）。key 轮换检查（收官检查单第 1 条）。
130. [路线] **round-169 候选**（round-168 收官登记）——①开局例行：核对
    HEAD 轮号与收官链（撞车纪律：开局门后先核 HEAD 轮号）；②维护轮候选
    （下一依赖刷新锚点 r170 前后或按需）；③MCP 异步作业实现（D-055 待
    总监裁决，条件轮）；④CII/Gitea runner（操作员）。key 轮换检查（收官
    检查单第 1 条）。
131. [路线] **round-170 候选**（round-169 收官登记）——①**开局首动作：r169
    补录**（负载恢复后 run1/run2 重跑重写日志 → close 169（light）→ 尾随
    commit，按 DEVELOPMENT §10 补录规程；含 2.71.0 发布闸证据）；②维护轮
    候选（依赖刷新第十一跑锚点 r170 前后）；③MCP 异步作业实现（D-055 待
    总监裁决，条件轮）；④CII/Gitea runner（操作员）。key 轮换检查（收官
    检查单第 1 条）。
132. [路线] **round-171 开局：三选一**（round-170 收官登记）——①tag 断档处置（v2.38–v2.72 未打 tag，
     D-035「tag 是唯一发布动作」不一致；待总监裁定是否补打/追认，tag 不可移动）；
     ②依赖刷新第十一跑（r167 第十跑后第 4 轮，锚点 r170 前后已到）；
     ③MCP 异步作业真作业冒烟（code_review_submit 跑一次真实 runner，budget 分档小步 + job 断线重连验证）。
     key 轮换检查（收官检查单第 1 条）。
133. [路线] **round-172 开局：三选一**（round-171 收官登记）——①MCP 异步作业 step 进度帧解析
     + 断线重连真作业回归（status.step 终态应为 10；需 runner 进度帧与 regex 对齐，+契约）；
     ②依赖刷新第十一跑（r167 第十跑后第 5 轮）；
     ③tag 链维护复核（35 tag 远端/本地逐一 verify + D-035 追认记录收口，零代码 light 候选）。
     key 轮换检查（收官检查单第 1 条）。
134. [路线] **round-173 开局：三选一**（round-172 收官登记）——①依赖刷新第十一跑（r167 第十跑后第 6 轮）；
     ②MCP 异步作业扩面：submit 支持 --config 透传与 job 取消/清理接口（需提案+裁决）；
     ③review 能力口径复核：硬规则臂 0.42% 与新增契约的语义边界（不改对外数字，仅审计）。
     key 轮换检查（收官检查单第 1 条）。
135. [路线] **round-174 开局：三选一**（round-173 收官登记）——①MCP 异步扩面提案（submit config 透传 / job 取消清理，
     先写案交裁决）；②评测口径复核（0.42% 与 778 契约语义边界审计，不改数字）；
     ③维护轮：D-052 触发线观察（r173 双跑 527/514 接近 540s，是否负载回潮如实记录）。
     key 轮换检查（收官检查单第 1 条）。
136. [路线] **round-175 开局：三选一**（round-174 收官登记）——①MCP 扩面提案裁决承接（若批 B/C，按阶段实现 + 契约 + 双跑/gate/tag）；
     ②评测口径复核（0.42% 与 778 契约语义边界审计，不改数字）；
     ③维护轮：D-052 触发线观察（r173 双跑 527/514 接近 540s；r174 单跑 243.69s 回落，负载信号如实记录）。
     key 轮换检查（收官检查单第 1 条）。
137. [路线] **round-176 开局：三选一**（round-175 收官登记）——①MCP 扩面提案裁决承接（reports/proposal-mcp-async-ext-r174.md，
     候选 A/B/C，需总监裁定；提案人不得自批）；②D-052 判定粒度明确化（「任一跑 >540s」vs「双跑中位 >540s」）
     + D-052 维护轮，必要时写 DECISIONS 勘误；③维护轮：下一依赖刷新锚点观察（r173 第十一跑后第 3 轮）。
     key 轮换检查（收官检查单第 1 条）。
138. [路线] **round-177 开局：三选一**（round-176 收官登记）——①阶段 C（purge 留存）需总监再次裁决，
     未批前不实现（提案人不得自批）；②MCP 异步作业扩面回归：cancel 后 job 清理与 runs/jobs 目录审计，
     或 cancel 的 Unix 侧进程组信号实测（Windows 已验）；③维护轮：下一依赖刷新锚点观察（r173 后第 4 轮）。
     key 轮换检查（收官检查单第 1 条）。
139. [路线] **round-178 开局：三选一**（round-177 收官登记）——①阶段 C（purge 留存）仍需总监单独裁决，
     未批前不实现；②维护轮：下一依赖刷新锚点观察（r173 后第 5 轮，~10 轮节奏）；
     ③MCP 异步作业验收面扩展：jobs 资源增加 cancel 作业摘要/event-ledger 重放对账（须先提案）。
     key 轮换检查（收官检查单第 1 条）。
140. [路线] **round-179 开局：三选一**（round-178 收官登记）——①jobs 资源提案裁决承接（A/B，需总监裁定；
     提案人不得自批）；②阶段 C（purge 留存）裁决承接（同样需总监裁定）；
     ③维护轮：依赖刷新锚点观察（r173 后第 6 轮，~10 轮节奏）或评测口径季度对账。
     key 轮换检查（收官检查单第 1 条）。
141. [路线] **round-180 开局：三选一**（round-179 收官登记）——①阶段 C（purge）已批准：实现 code_review_purge
     （confirm + 单 id + 终态三重闸 + 账本摘要），工具 15→16、+3 契约；②维护轮：依赖刷新锚点观察（r173 后第 7 轮）；
     ③评测口径季度对账（0.42% 与 786→791 契约语义边界，不改数字）。
     key 轮换检查（收官检查单第 1 条）。
142. [路线] **round-181 开局：三选一**（round-180 收官登记）——①MCP 异步作业全链收官复核
     （submit/status/cancel/purge + resources/ledger 的契约与真作业证据一致性审计，零代码 light）；
     ②依赖刷新锚点观察（r173 后第 8 轮，~10 轮节奏临近）；
     ③评测口径季度对账（0.42% 与 794 契约语义边界，不改数字）。
     key 轮换检查（收官检查单第 1 条）。
143. [路线] **round-182 开局：三选一**（round-181 收官登记）——①依赖刷新锚点观察/准备（r173 后第 9 轮，
     ~10 轮节奏临近，r182/r183 可跑）；②评测口径季度对账（0.42% 与 794 契约语义边界，不改数字）；
     ③CI nightly 全量口径复核（ubuntu timeout 600 / windows timeout-minutes 45 兜底是否仍生效）。
     key 轮换检查（收官检查单第 1 条）。
144. [路线] **round-183 开局：三选一**（round-182 收官登记）——①CI nightly 全量口径复核
     （ubuntu timeout 600 / windows job timeout-minutes 45 是否仍生效，零代码 light）；
     ②评测口径季度对账（0.42% 与 794 契约语义边界，不改数字）；
     ③维护轮：依赖刷新下一锚点约 r192 未到，期间只做例行观察。
     key 轮换检查（收官检查单第 1 条）。
145. [路线] **round-184 开局：三选一**（round-183 收官登记）——①评测口径季度对账（0.42% 与 794 契约语义边界，
     不改数字；上次 r175）；②维护轮：依赖刷新下一锚点约 r192 未到，例行观察；
     ③事件账本哈希链与轮报对账复核（runs/rounds-ledger 34+ 条，零代码 light）。
     key 轮换检查（收官检查单第 1 条）。
146. [路线] **round-185 候选**（round-184 收官登记）——①MCP ledger flaky 留观
     复核（r184 全量 1 次失败 + 隔离 3/3 过；复现则修测试隔离，零复现则观察
     期满结案）；②维护轮：依赖刷新下一锚点约 r192（例行观察）；③事件账本
     哈希链与轮报对账复核（第 145 条③顺延，零代码 light）。
     key 轮换检查（收官检查单第 1 条）。
147. [路线] **round-186 候选**（round-185 收官登记）——①结构候选：close 门
     账本追加幂等性复核（r185 账本对账发现 r154 双记——_append_ledger_record
     无同轮去重，close 重跑会双记；如确证则加幂等守卫 + 反向验证，约一轮）；
     ②维护轮：依赖刷新下一锚点约 r192（例行观察，未到）；③CII/Gitea
     runner（操作员）。key 轮换检查（收官检查单第 1 条）。
148. [路线] **round-187 候选**（round-186 收官登记）——①维护轮：依赖刷新
     第十三跑锚点约 r192（例行观察，未到；r182 第十二跑后第 5 轮）；②CII/
     Gitea runner（操作员）；③零候选时 light 观察轮（契约 797 首周观察）。
     key 轮换检查（收官检查单第 1 条）。
149. [路线] **round-188 候选**（round-187 收官登记）——①维护轮：依赖刷新
     第十三跑锚点约 r192（例行观察，未到）；②CII/Gitea runner（操作员）；
     ③零候选时 light 观察轮（契约 797 观察期延续）。
     key 轮换检查（收官检查单第 1 条）。
150. [路线] **round-189 候选**（round-188 收官登记）——①弹窗修复实证观察：
     MCP 真作业冒烟（submit→done 全链）确认无黑窗（用户侧复证）；②维护轮：
     依赖刷新第十三跑锚点约 r192（例行观察，未到）；③CII/Gitea runner
     （操作员）。key 轮换检查（收官检查单第 1 条）。
151. [路线] **round-190 候选**（round-189 收官登记）——①维护轮：依赖刷新
     第十三跑锚点约 r192（例行观察，临近）；②CII/Gitea runner（操作员）；
     ③零候选时 light 观察轮（契约 798 观察期延续）。
     key 轮换检查（收官检查单第 1 条）。
152. [路线] **round-191 候选**（round-190 收官登记）——①维护轮候选：发布闸
     证据面顺序硬化候选评估（--out 写入先于 git_state 检查的证据面文件在重跑
     场景使树脏——闸内自查或先清 --out 的顺序修正，约一轮）；②MCP async
     家族 flaky 观察期重启（读写硬化后全量双跑零复现即观察收口）；③CII/
     Gitea runner（操作员）。key 轮换检查（收官检查单第 1 条）。
153. [路线] **round-192 候选**（round-191 收官登记）——①维护轮候选：MCP
     async 家族观察期复核（r190 硬化后连续全量轮零复现即收口）；②依赖刷新
     第十四跑锚点约 r200（例行观察，未到）；③CII/Gitea runner（操作员）。
     key 轮换检查（收官检查单第 1 条）。
154. [路线] **round-193 候选**（round-192 收官登记）——①维护轮候选：依赖
     刷新第十四跑锚点约 r200（例行观察，未到）；②CII/Gitea runner（操作员）；
     ③零候选时 light 观察轮（契约 801 观察期延续）。
     key 轮换检查（收官检查单第 1 条）。
155. [路线] **round-194 起候选队列**（round-193 收官登记，吸收地图 Top10 滚动）——
     ①trace.py 补 Langfuse 评分回挂+评测集导出（评测闭环第一块板，约一轮）；
     ②评审意见质量指标 pytest 化进 CI（DeepEval 式 G-Eval，与 precision 护栏
     互补，约一轮）；③prompt/模型变更回归门（promptfoo 式 YAML 矩阵，约一轮）；
     ④SWE-agent ACI 准则审查 16 工具 + precision 护栏复测（约一轮）；⑤mcp-scan
     投毒扫描进 nightly（低成本）；⑥影子 git 检查点（编码循环 workspace 档）；
     ⑦repo_map 中心度排序单变量复评（D-031 重验，读设计不引依赖）；⑧Serena
     符号级取用对照实验；⑨SKILL.md 渐进披露规范对齐；⑩elicitation 承载批准书
     交互（远期）。依赖刷新第十四跑锚点约 r200；CII/Gitea runner（操作员）。
     key 轮换检查（收官检查单第 1 条）。
156. [路线] **round-195 起执行队列**（round-194 收官登记；权威源=reports/upgrade-roadmap-r194.md 三阶段路线）——
     阶段一七项按序执行：①AB-07 ACI 工具面审计（S）；②AB-08 mcp-scan 进
     nightly（S）；③AB-09 工具描述规范（S，与②同轮）；④AB-12 Plan 工具面
     收窄（S）；⑤AB-17 repo_map 中心度复评（S-M，D-031 重验）；⑥AB-03 提示
     变更回归门（S-M）；⑦AB-15 原子 Edit/终端闸对照审计（S）。上游补研先行
     （5 处 schema 缺口）；依赖刷新第十四跑锚点约 r200；CII/Gitea runner
     （操作员）。key 轮换检查（收官检查单第 1 条）。
157. [路线] **round-196 起执行队列**（round-195 收官登记；权威源=reports/upgrade-roadmap-r194.md）——
     阶段一剩余：②③AB-08 mcp-scan 进 nightly + AB-09 工具描述规范（一轮）；
     ④AB-12 Plan 工具面收窄（一轮）；⑤AB-17 repo_map 中心度复评（D-031
     重验实验，一轮）；⑥AB-03 提示变更回归门（一轮）；AB-15 已于 r195 完成。
     依赖刷新第十四跑锚点约 r200；CII/Gitea runner（操作员）。key 轮换
     检查（收官检查单第 1 条）。
158. [路线] **round-197 起执行队列**（round-196 收官登记；权威源=reports/upgrade-roadmap-r194.md）——
     阶段一剩余：④AB-12 Plan 工具面收窄（一轮）；⑤AB-17 repo_map 中心度
     复评（D-031 重验实验，一轮）；⑥AB-03 提示变更回归门（一轮）。观察项：
     **首个 CI nightly 复核 mcp-scan 动态枚举**（ubuntu 上 tools 枚举成功→
     报告落 reports/mcp-scan/baseline.json）。依赖刷新第十四跑锚点约 r200；
     CII/Gitea runner（操作员）。key 轮换检查（收官检查单第 1 条）。
159. [路线] **round-198 起执行队列**（round-197 收官登记；权威源=reports/upgrade-roadmap-r194.md）——
     阶段一仅余：⑥AB-03 提示变更回归门（一轮；promptfoo CLI 复用可行性
     评估先行，不可行则 precision-gate 加声明层）。观察项：首个 CI nightly
     复核 mcp-scan 动态枚举（ubuntu tools 枚举→baseline 落盘）。AB-12/AB-17
     已于 r197 完成（后者=决定性负结果，终局证据）。依赖刷新第十四跑锚点
     约 r200；CII/Gitea runner（操作员）。key 轮换检查（收官检查单第 1 条）。
160. [路线] **round-198 执行队列**（round-197 收官登记；权威源=reports/upgrade-roadmap-r194.md）——
     阶段一收官项：⑥AB-03 提示变更回归门（promptfoo CLI 复用可行性评估
     先行，不可行则 precision-gate 加 YAML 声明层）。完成后阶段一（七项）
     全清，进阶段二（AB-01 trace 评分回挂起）。观察项：首个 CI nightly
     复核 mcp-scan 动态枚举（baseline 落盘）。依赖刷新锚点约 r200；CII/
     Gitea runner（操作员）。key 轮换检查（收官检查单第 1 条）。
161. [路线] **round-199 起执行队列**（round-198 收官登记；权威源=reports/upgrade-roadmap-r194.md 阶段二）——
     **阶段一开始**：①AB-01 trace.py 补 Langfuse 评分回挂+评测集导出
     （评测闭环第一块板，score API 上游补研先行）；②AB-02 质量指标
     pytest 化（依赖①评测集）。观察项：首个 CI nightly 复核 mcp-scan
     动态枚举（baseline 落盘）。依赖刷新第十四跑锚点约 r200；CII/Gitea
     runner（操作员）。key 轮换检查（收官检查单第 1 条）。
162. [路线] **round-200 起执行队列**（round-199 收官登记；权威源=reports/upgrade-roadmap-r194.md 阶段二）——
     **依赖刷新第十四跑锚点到（r200，专属轮）**：镜像 dry-run 逐项探测+
     三引擎矩阵重测（87 脚本口径）；完成后阶段二续：②AB-02 质量指标
     pytest 化（judge 指标集，依赖①已就绪）。观察项：首个 CI nightly
     复核 mcp-scan 动态枚举（baseline 落盘）。CII/Gitea runner（操作员）。
     key 轮换检查（收官检查单第 1 条）。
163. [路线] **round-201 起执行队列**（round-200 收官登记；权威源=reports/upgrade-roadmap-r194.md 阶段二）——
     阶段二续：②AB-02 质量指标 pytest 化（judge 指标集，AB-01 评测集
     导出器已就绪）。观察项：首个 CI nightly 复核 mcp-scan 动态枚举
     （baseline 落盘）。下一依赖锚点约 r210。CII/Gitea runner（操作员）。
     key 轮换检查（收官检查单第 1 条）。
164. [路线] **round-202 起执行队列**（round-201 收官登记；权威源=reports/upgrade-roadmap-r194.md 阶段二）——
     阶段二续：⑪AB-11 影子 git 检查点（编码循环 workspace 本地档 edit 前
     快照+一键回滚，Cline 方案复用）。观察项：首个 CI nightly 复核
     mcp-scan 动态枚举（baseline 落盘）。下一依赖锚点约 r210；CII/Gitea
     runner（操作员）。key 轮换检查（收官检查单第 1 条）。
165. [路线] **round-203 起执行队列**（round-202 收官登记；权威源=reports/upgrade-roadmap-r194.md 阶段二）——
     ①影子检查点 bare 判定上游补研（git worktree+separate --git-dir 判定
     序；裁决后定缺省值）；②阶段二续：⑧AB-18 Serena 符号级对照实验 或
     ⑫AB-13 Hooks 对照。观察项：首个 CI nightly 复核 mcp-scan 动态枚举。
     下一依赖锚点约 r210；CII/Gitea runner（操作员）。key 轮换检查
     （收官检查单第 1 条）。
166. [路线] **round-204 执行队列**（round-203 收官登记；权威源=reports/upgrade-roadmap-r194.md 阶段二）——
     ①影子 init 延迟修复：shadow init 移到首个 fix 轮（wt 物理存在后）+
     core.bare=false 钉住（根因=init 时 wt 不存在 → bare init）；验收=
     缺省 on + code-task 全链 e2e 绿；②完成后阶段二续：⑧AB-18 Serena
     符号级对照实验 或 ⑫AB-13 Hooks 对照。观察项：首个 CI nightly 复核
     mcp-scan 动态枚举。下一依赖锚点约 r210；CII/Gitea runner（操作员）。
     key 轮换检查（收官检查单第 1 条）。
167. [路线] **round-205 起执行队列**（round-204 收官登记；权威源=reports/upgrade-roadmap-r194.md 阶段二）——
     阶段二续：⑧AB-18 Serena 符号级取用对照实验（符号级 vs 整文件
     取窗的材料成本/命中对照）或 ⑫AB-13 Hooks 拦截器对照（五道闸改写
     返回查缺）。观察项：首个 CI nightly 复核 mcp-scan 动态枚举。
     下一依赖锚点约 r210；CII/Gitea runner（操作员）。key 轮换检查
     （收官检查单第 1 条）。
168. [路线] **round-206 起执行队列**（round-205 收官登记；权威源=reports/upgrade-roadmap-r194.md 阶段二）——
     阶段二续：④AB-04 评测任务三件套重构（task/solver/validator 命名
     与目录约定）或 ㉑AB-21 SKILL.md 对齐。AB-13/17 已于 r205 完成
     （后者=已对齐零缺口终局）。观察项：首个 CI nightly 复核 mcp-scan
     动态枚举。下一依赖锚点约 r210；CII/Gitea runner（操作员）。
     key 轮换检查（收官检查单第 1 条）。
169. [路线] **round-207 起执行队列**（round-206 收官登记；权威源=reports/upgrade-roadmap-r194.md 阶段二）——
     阶段二续：④AB-04 评测任务三件套重构（task/solver/validator 命名
     与目录约定）。观察项：首个 CI nightly 复核 mcp-scan 动态枚举。
     下一依赖锚点约 r210；CII/Gitea runner（操作员）。key 轮换检查
     （收官检查单第 1 条）。
170. [路线] **round-208 起执行队列**（round-207 收官登记；权威源=reports/upgrade-roadmap-r194.md 阶段二）——
     **阶段二七项全清**（AB-01/02/03/04/11/13/15/17/21 全部落地或审计
     确认已对齐；终局结论不再重议）。进阶段三条件轮（AB-06 DSPy / AB-20
     记忆管线 / AB-10 elicitation / AB-14 沙箱——逐项总监裁决）或维护轮
     （依赖刷新第十四跑锚点约 r210）。观察项：首个 CI nightly 复核
     mcp-scan 动态枚举。CII/Gitea runner（操作员）。key 轮换检查
     （收官检查单第 1 条）。
171. [路线] **round-209 起执行队列**（round-208 收官登记；权威源=reports/upgrade-roadmap-r194.md）——
     依赖刷新第十五跑锚点 r210（下一轮即到——专属轮）；完成后阶段三
     条件轮逐项总监裁决（AB-06/20/10/14——需总监批准不自行启动）。
     观察项：CI nightly mcp-scan 枚举复核。CII/Gitea runner（操作员）。
     key 轮换检查（收官检查单第 1 条）。
172. [路线] **round-210 执行队列**（round-209 收官登记）——依赖刷新第十五跑
     专属轮：pyproject 白名单内依赖版本刷新（uv lock --upgrade-package 逐包
     定向，清华镜像）+ 测试双跑 + release-gate + 版本增补；无可用升级如实
     N/A 记录。完成后回维护轮节奏或总监裁决阶段三条件轮。观察项：CI
     nightly mcp-scan 枚举复核；CII/Gitea runner（操作员）；key 轮换检查
     （收官检查单第 1 条）。
173. [路线] **round-211 起执行队列**（round-210 收官登记）——回维护轮节奏；
     阶段三条件轮（AB-06 DSPy / AB-20 记忆管线 / AB-10 elicitation / AB-14
     沙箱）逐项总监裁决（需总监批准不自行启动）。观察项：CI nightly
     mcp-scan 枚举复核（操作员）。CII/Gitea runner（操作员）。key 轮换
     检查（收官检查单第 1 条）。**依赖双面核验纪律**：刷新轮必须 lock
     grep + uv pip list 比对；探针先证工具可用再信输出（31f6c8f13828）。
174. [路线] **round-212 起执行队列**（round-211 收官登记）——维护轮节奏持续；
     阶段三条件轮（AB-06 DSPy / AB-20 记忆管线 / AB-10 elicitation / AB-14
     沙箱）逐项总监裁决（需批准不自行启动）。观察项：CI nightly mcp-scan
     枚举复核（操作员）。CII/Gitea runner（操作员）。key 轮换检查
     （收官检查单第 1 条）。依赖双面核验纪律延续（31f6c8f13828）。
175. [路线] **round-213 起执行队列**（round-212 收官登记）——**吸收列表
     对账收口后仅余两条工作流**：①维护轮节奏（五检+观察项扫描）；
     ②阶段三条件轮 6 项（AB-06/10/14/16/20/22）逐项总监裁决（需批准
     不自行启动）。观察项：CI nightly mcp-scan 枚举复核（操作员）。
     CII/Gitea runner（操作员）。key 轮换检查（收官检查单第 1 条）。
     依赖双面核验纪律延续（31f6c8f13828）。
176. [路线] **round-214 起执行队列**（round-213 收官登记；阶段三已获总监
     2026-11-27 全量批准）——②AB-22 配方化（report-adapter preset YAML
     化 + 被审仓 rules 注入，纯代码无 LLM 依赖）→ ③AB-16 rails 对照 +
     on_fail 标准化 → ④AB-20 记忆三级管线（无 LLM key：基建+决策提示
     +契约，live 面如实 blocked）→ ⑤AB-06 DSPy 提示优化循环（同约束）→
     ⑥AB-14 沙箱可行性（Linux 先行，Windows 面=设计档）+ RouteLLM
     读设计。观察项：CI nightly/CII/key 轮换（操作员）。
177. [路线] **round-215 起执行队列**（round-214 收官登记）——③AB-16 rails
178. [路线] **round-215 起执行队列**（round-214 收官登记）——③AB-16 rails
     对照 + 闸面 on_fail 动作标准化 → ④AB-20 记忆三级管线 → ⑤AB-06 DSPy
     提示优化循环 → ⑥AB-14 沙箱可行性 + RouteLLM 读设计。**两条新纪律**：
     新脚本模板必须含 UTF-8 stdout reconfigure 自防御（3fbe8bfb4bc5）；
     kill 测试进程树后 git status 复核真仓夹具污染 + test_taint 临时
     副本加固候选（round-214 第二坑）。观察项：CI nightly/CII/key
     轮换（操作员）。
179. [路线] **round-216 起执行队列**（round-215 收官登记）——④AB-20 记忆
     三级管线（无 LLM key：基建+决策提示自写+契约，live 面 blocked
     如实标注）→ ⑤AB-06 DSPy 提示优化循环（同约束）→ ⑥AB-14 沙箱
     可行性（Linux 先行，Windows 面=设计档）+ RouteLLM 读设计。
     纪律延续：新脚本 UTF-8 自防御 + kill 后 git status 复核。
     观察项：CI nightly/CII/key 轮换（操作员）。
180. [路线] **round-217 起执行队列**（round-216 收官登记）——⑤AB-06 DSPy
     提示优化循环（无 LLM key：优化器基建+护栏对照协议，live 优化
     blocked 如实标注）→ ⑥AB-14 沙箱可行性（Linux 先行，Windows 面=
     设计档）+ RouteLLM 读设计。纪律延续：新脚本 UTF-8 自防御 + kill
     后 git status 复核。观察项：CI nightly/CII/key 轮换（操作员）。
181. [路线] **round-218 起执行队列**（round-217 收官登记）——⑥AB-14 沙箱
     可行性（Linux Landlock 先行→Windows 面为设计档）+ RouteLLM 读设计
     （难度路由读设计不引依赖）——**阶段三收官轮**。完成后阶段三
     全项终局（AB-06/10/14/16/20/22 + RouteLLM 七项全清）。纪律延续：
     新脚本 UTF-8 自防御 + kill 后 git status 复核。观察项：CI nightly/
     CII/key 轮换（操作员）。
182. [路线] **round-219 起执行队列**（round-218 收官登记）——**吸收计划
     三阶段全清，回到维护轮节奏**（五检+观察项扫描）。观察项：CI
     nightly mcp-scan 枚举复核（操作员）。CII/Gitea runner（操作员）。
     key 轮换检查（收官检查单第 1 条）。依赖双面核验纪律延续
     （31f6c8f13828）。下一依赖锚点约 r220（专属轮）。**改进候选待评估**：
     「scripts 必须含 reconfigure 自防御」静态判据（r214 候选）+
     test_taint 临时副本加固（r214 候选）——维护轮顺手评估。
     对照 + 闸面 on_fail 动作标准化 → ④AB-20 记忆三级管线（无 LLM
     key：基建+决策提示+契约，live 面 blocked）→ ⑤AB-06 DSPy 提示
     优化循环（同约束）→ ⑥AB-14 沙箱可行性（Linux 先行，Windows 面=
     设计档）+ RouteLLM 读设计。**新脚本模板纪律**：必须含 UTF-8 stdout
     reconfigure 自防御（3fbe8bfb4bc5）+「scripts 必须含 reconfigure」
     静态判据候选（doc-structure/triggers-audit 增判据，下轮评估）。
     观察项：CI nightly/CII/key 轮换（操作员）。
183. [路线] **round-220 起执行队列**（round-219 收官登记）——**依赖刷新
     第十六跑锚点约 r220（专属轮）**：国内镜像逐包探测 + lock/venv 双面
     核验 + 三引擎矩阵重测；无升级如实记录。维护轮继续五检与观察项扫描：
     CI nightly mcp-scan 枚举复核、CII/Gitea runner、key 轮换（操作员）。
     S10 已落地，新增脚本按 main/_emit 约定自防御；污点测试临时副本已加固，
     不重复立项。提交后补跑 release-gate git_state 全项签核。
184. [路线] **round-221 起执行队列**（round-220 收官登记）——回到维护轮节奏：
     五检（freshness/drift/structure/dead-code/secret）+ 观察项扫描。观察项：
     CI nightly mcp-scan 枚举复核、CII/Gitea runner、key 轮换（操作员）；
     MCP async `test_purge_guards` 本轮再次偶发，隔离 2.42s 通过，继续留观。
     下一依赖刷新锚点约 r230；提交后补跑 release-gate git_state 全项签核。
185. [路线] **round-222 起执行队列**（round-221 收官登记）——继续维护轮：
     五检 + 观察项扫描；MCP async 家族已 27/27 全绿，`test_purge_guards`
     继续留观但不阻塞。CI nightly mcp-scan 枚举复核、CII/Gitea runner、
     key 轮换仍为操作员动作。下一依赖刷新锚点约 r230；提交后补跑
     release-gate git_state 全项签核。
186. [路线] **round-223 开局：三选一**（round-222 收官登记）——①用户裁定数据集缓存清理（swe-out 98GB /
     swebench pro-runs+live-runs 约 20GB，报告数字已固化，原始产物不可恢复）；
     ②测试偶发 pid 竞态复现与加固（test_cancel_running_job 在 xdist 下首跑红，需定位真正竞态点）；
     ③维护轮：依赖刷新下一锚点观察（r220 第十六跑后第 3 轮，~10 轮节奏未到）。
     key 轮换检查（收官检查单第 1 条）。
187. [路线] **round-224 开局：三选一**（round-223 收官登记）——①MCP cancel 竞态观察：下一轮双跑若再现 killed_pids=[]
     再采进程树/文件时间戳定位，不再据并发噪声入坑；②依赖刷新锚点观察（r220 第十六跑后第 4 轮，~10 轮节奏未到）；
     ③数据集二次盘点（确认剩余 ~9GB 缓存与 imagecache 是否仍需保留，零代码 light）。
     key 轮换检查（收官检查单第 1 条）。
188. [路线] **round-225 开局：三选一**（round-224 收官登记）——①用户裁定剩余 2GB 缓存是否清理
     （verified-runs 四轮 / swe-work / live 小产物 / swe-out harness，未批不删）；
     ②依赖刷新第十七跑（r220 第十六跑后第 5 轮，~10 轮节奏可提前提案）；
     ③维护轮：评测口径季度对账（0.42% 与 849 契约语义边界，不改数字）。
     key 轮换检查（收官检查单第 1 条）。
189. [路线] **round-226 开局：三选一**（round-225 收官登记）——①用户裁定剩余 2GB 缓存清理
     （verified-runs 四轮 / swe-work / live 小产物 / swe-out harness，未批不删）；
     ②依赖刷新第十七跑（r220 第十六跑后第 6 轮，~10 节奏可提前提案）；
     ③维护轮：MCP cancel 竞态观察 + D-052 触发线观察（本轮双跑均线内）。
     key 轮换检查（收官检查单第 1 条）。
190. [路线] **round-227 开局：三选一**（round-226 收官登记）——①依赖刷新第十八跑锚点观察（r226 第十七跑后第 1 轮，~10 轮节奏未到）；
     ②维护轮：全仓口径与计数季度对账（README / PROGRESS / BASELINE 数字一致性，零代码 light）；
     ③MCP cancel 竞态与 D-052 触发线观察（双跑若再现异常再定位，不预判）。
     key 轮换检查（收官检查单第 1 条）。
191. [路线] **round-228 开局：三选一**（round-227 收官登记）——①依赖刷新第十八跑提案（r226 后第 2 轮，~10 节奏未到）；
     ②维护轮：对外口径与门禁面季度复核（README / CI nightly / release-gate 数字一致性，零代码 light）；
     ③MCP cancel 竞态与 D-052 触发线观察（若双跑异常再定位）。
     key 轮换检查（收官检查单第 1 条）。
192. [路线] **round-229 开局：三选一**（round-228 收官登记）——①依赖刷新第十八跑提案（r226 后第 3 轮，~10 节奏未到）；
     ②维护轮：项目体积与缓存盘点（确认 7GB 剩余内容是否仍需保留，零代码 light）；
     ③MCP cancel 竞态与 D-052 触发线观察（双跑异常再定位）。
     key 轮换检查（收官检查单第 1 条）。
193. [路线] **round-230 开局：三选一**（round-229 收官登记）——①依赖刷新第十八跑提案（r226 后第 4 轮，~10 节奏可提前提案）；
     ②维护轮：评测口径与门禁面季度对账（0.42% / host unavailable / gate 证据，零代码 light）；
     ③MCP cancel 竞态与 D-052 触发线观察（若双跑异常再定位）。
     key 轮换检查（收官检查单第 1 条）。
194. [路线] **round-231 开局：三选一**（round-230 收官登记）——①用户裁定是否提前跑依赖刷新第十八跑
     （提案建议不提前，锚点约 r236；若批则本轮执行 full 双跑+gate/tag）；
     ②维护轮：对外口径与门禁面季度对账（0.42% / host unavailable / gate 证据，零代码 light）；
     ③MCP cancel 竞态与 D-052 触发线观察（双跑异常再定位）。
     key 轮换检查（收官检查单第 1 条）。
195. [路线] **round-232 开局：三选一**（round-231 收官登记）——①维护轮：评测口径与门禁面季度对账
     （0.42% / host unavailable / gate 证据，零代码 light；上次 r228）；
     ②MCP cancel 竞态与 D-052 触发线观察（若双跑异常再定位）；
     ③等待新开发任务（当前自主维护候选已全部收敛，不再空转）。
     key 轮换检查（收官检查单第 1 条）。

196. [路线] **round-233 开局：三选一**（round-232 收官登记）——①阶段 5 批次一 P0 施工轮：M1 mcp-selfscan + M4 工具分级门控 + M2 循环边界 + M3 回填重试（代码轮 full 双跑；前置=反向验证样例先行 + precision-gate 基线不回退）；②维护轮：季度对账顺延；③等新任务或总监对 D-054 裁决（裁决后批次三并入 r236 依赖刷新锚点轮）。
197. [路线] **round-234 开局：三选一**（round-233 收官登记）——①批次二 P1-stdlib 施工轮（M5 多端点 fallback 链 + M7 pii-scan.py + M6 变更感知测试选择 + M8 记忆比对臂，代码轮 full 双跑；前置=反向验证样例先行）；②维护轮：季度对账顺延；③等新任务或总监对 D-054 裁决（裁决后批次三并入 r236 依赖刷新锚点轮）。
198. [路线] **round-235 开局：三选一**（round-234 收官登记）——①批次二后半施工轮：M6 变更感知测试选择（fix-apply 闸五提速，stdlib ast+git diff）+ M8 记忆比对臂（mem0 思想强化 memory-pipeline：抽取→比对→ADD/UPDATE/DELETE/归档）（代码轮 full 双跑；前置=反向验证样例先行）；②维护轮：季度对账顺延；③等新任务或总监对 D-054 裁决（裁决后批次三并入 r236 依赖刷新锚点轮）。
199. [路线] **round-236 开局：三选一**（round-235 收官登记）——①依赖刷新第十九跑：锚点约 r236 已到（11 直接依赖只读探测 → 提案或执行 full 双跑+gate/tag；若总监批准 D-054 则批次三依赖并入本轮裁定）；②维护轮：季度对账顺延；③等新任务。批次四 backlog（借设计）与 D-054（依赖批准，提案人≠批准人）仍待总监裁决。
200. [路线] **round-237 开局：三选一**（round-236 收官登记）——①总监对两项待批事项裁决后执行（D-054 依赖批准 → 批次三落地；依赖刷新第十九跑裁定）；②维护轮：季度对账顺延；③等新任务。批次四 backlog 借设计项按计划待总监点名。
201. [路线] **round-238 开局：三选一**（round-237 收官登记）——①维护轮：评测口径与门禁面季度对账顺延（上次 r228，可再顺延至锚点对齐）；②依赖锚点 r244 前无动作；③等新任务（阶段 5 已收口，批次三/四条件激活均无触发迹象）。
202. [路线] **round-239 开局：三选一**（round-238 收官登记）——①公开仓 CI 复验收官（若绿：同步闭环登记；若红：按 job 级证据续诊）；②维护轮：季度对账顺延；③等新任务。依赖锚点 r244 不变。
203. [路线] **round-240 开局：三选一**（round-239 收官登记）——①公开仓 nightly 修复裁定：nightly 装 dev 依赖（pytest 等）或测试面环境分层（把 .venv/host-memory 依赖测移出 CI 全量面），配套 astgrep×3 runner 特有失败诊断；②维护轮：季度对账顺延；③等新任务。依赖锚点 r244 不变。
204. [路线] **round-241 开局：三选一**（round-240 收官登记）——①公开仓 nightly 修复裁定（条目 203 ①顺延：dev 依赖或测试面环境分层 + astgrep×3 诊断）；②许可决策：开源授权（Apache-2.0/MIT）或维持全权利保留（总监裁定后同步 README/SECURITY/LICENSE 三处口径）；③等新任务。依赖锚点 r244 不变。
