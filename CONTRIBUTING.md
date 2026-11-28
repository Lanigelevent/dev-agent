# 贡献指南（Contributing）

感谢关注 dev-agent。本项目当前以**治理先行的单人维护为主**：问题反馈与讨论随时欢迎；
代码改动请先读本文与 [AGENTS.md](AGENTS.md)（主流程与硬约束的唯一权威源）。

## 报告问题

- 提交 issue 前请用问题模板填写：现象、复现步骤、期望与实际、环境（OS / Python / 版本号，版本号见 README「当前状态」表）。
- 评审结论类问题请附**最小复现**（目标仓库 + 变更范围 + 实跑命令）；本项目对外只认可复算的证据，不带复现的报告难以受理。

## 开发环境搭建

```bash
git clone <仓库地址>
cd dev-agent
uv sync                 # 引擎层依赖（锁安装）
# 治理壳用任意 Python ≥3.11；全量测试用 .venv 的 Python 3.12
# Windows 宿主注意：跑套件须置空 PYTHONUTF8 / PYTHONIOENCODING（见 AGENTS.md）
```

## 本地验证（提交前必跑）

```bash
python -m unittest discover -s tests          # 契约面
.venv/Scripts/python.exe -m pytest tests -n 2 -q   # 全量（改代码时）
```

- 文档改动跑 `doc-structure.py` 与 `doc-freshness.py`；结论改动先搜全部引用处（维护红线 7）。
- 每个检查器都要带反向验证（红线 6）：造违规样例确认抓得住。

## 分层依赖与写路径（硬边界）

- 治理壳（`skills/*/scripts`、`llm/`）只用标准库；引擎层依赖须过许可证白名单并经批准登记。
- 一切写被审仓库的动作**只经 `fix-apply.py` 五道闸**；修复分支永不自动合并；提案人 ≠ 批准人。

## 提交规范

- Conventional Commits；每轮工作按轮次闸（`round-gate.py`）开局与收官，提交信息带轮次。
- 结构性改动先立 ADR（`docs/DECISIONS.md`），行为级优化须过反向验证与精度基线。
