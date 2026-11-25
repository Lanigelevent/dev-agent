# 复盘轮报 round-6

open 2 / closed 27

## 分类统计

- 手工：25
- 误报：3
- 行为回归：1

## 未结坑明细

| ID | 类别 | 坑 | 根因 | 对策 | 来源 |
|---|---|---|---|---|---|
| a1ea933d8e26 | 手工 | Docker 探测：Windows 与 WSL Ubuntu 均无 docker 二进制（Program Files/D | 用户可能将 WSL 或已卸载的 Docker Desktop 记为可用 | 如实报告探测结果；harness 评测步 Docker 门控，Phase 3B  | retro\events-round-swebench.json |
| dcd866f9d912 | 手工 | swe_run.py 五种安全写法（白名单/normpath+isabs/safe_join）均被静态启发式以路径穿越误 | 启发式对 CLI 参数进 os.path.join 的模式无条件报警，校验代码不 | SWE-bench agent 侧管道降级为宿主可执行工作流文档（agent/s | retro\events-round-swebench.json |

## 改进候选（按 权重×数量 排序）

- **手工：2 个未结坑** — 纳入下一轮改进候选，明确责任与验收口径
