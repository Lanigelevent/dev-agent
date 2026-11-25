# 复盘轮报 round-2

open 7 / closed 2

## 分类统计

- 手工：8
- 行为回归：1

## 未结坑明细

| ID | 类别 | 坑 | 根因 | 对策 | 来源 |
|---|---|---|---|---|---|
| 07cf8ce1f8cc | 手工 | fix-apply 文档字符串与 SKILL.md 提及其他脚本的旗标拼写，被 doc-drift 参数漂移误判 | 不知道 doc-drift 会把同现脚本名与 --flag 的行当参数断言 | 写文档时散文体不出现 --旗标 拼写，git 旗标改文字描述 | retro\events-round-baseline.json |
| 2ae5d49858cb | 手工 | GitHub 直连被重置（Connection was reset），真实语料克隆改走 Gitee 镜像 | 网络环境对 github.com 的限制 | 真实语料策展统一走 Gitee 镜像 mirrors/<repo>，逐仓验证可用 | retro\events-round-realcorpus.json |
| 8bad50975bae | 手工 | Windows 下 py 打印 CRLF 行尾，bash 反引号取 ID 带  导致按 ID 查找失败 | py print 输出 
 与 bash 分词冲突 | 脚本提取 ID 后必须 strip()，或改用文件传递 | retro\events-round-org.json |
| a8c51e998c03 | 手工 | 评测窗口 12→36 个月经两人规则变更（提案 retro/批准 director），collect 验证 19→30 | - | 行为级配置变更沿用 _governance 式留痕：提案、批准、验证三件齐全 | retro\events-round-realcorpus.json |
| aceff6563e08 | 手工 | collect-samples --limit 0 语义是第一个样本即 break 而非不限 | 哨兵值 0 与「不限」语义冲突（len>=0 恒真） | 全量采集传显式大数；哨兵值语义在 docstring 里写清 | retro\events-round-realcorpus.json |
| b67f26397fe9 | 手工 | gitee.com/mirrors/jinja2 镜像不存在，克隆失败要求认证 | 并非所有上游仓库都有官方 Gitee 镜像 | 策展阶段逐仓验证；失败仓进入失败案例双轨 | retro\events-round-realcorpus.json |
| d2c22ec68c70 | 手工 | 测试 fixture 的测试文件未提交导致工作树脏，闸门守卫把行为回归测试用例本身拦下 | 五道闸前置条件与测试夹具准备顺序冲突 | 凡进五道闸链路的夹具先提交再送审 | retro\events-round-baseline.json |

## 改进候选（按 权重×数量 排序）

- **手工：7 个未结坑** — 纳入下一轮改进候选，明确责任与验收口径
