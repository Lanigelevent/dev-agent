# round-18 结案证据

> 结案口径：**对策已落地 + 有仓库内可验证锚点**（不许「标完成即完成」）。

## 坑 59b6f195b91c（Phase 3B 扩样三路由实测全阻）→ closed

**原坑**：SWE-bench 扩样三条路由（tasks 仓克隆 / 预构建镜像直拉 / 容器构建）
在当时的网络窗口下全阻——github 直连 21s 连接失败、gitee mirrors 对该仓 401、
docker 客户端拉取假启动；材料齐备但拉不到镜像。

**对策落地（两件）**

1. `scripts/docker-image-fetch.py`——四阶段逐层下载器：plan（token+manifest
   选 amd64）→ fetch（逐 blob **并行 Range 分段**，`--segments 16 --workers 8`，
   sha256 强制校验）→ assemble（OCI image layout tar）→ load（docker load）。
   **绕开 docker 客户端的假启动路径**，连接数上限 16（aria2 社区硬约定）。
2. `skills/eval-harness/scripts/gold-sample.py`——单命令「映射 → 下载 →
   docker load → 官方 harness 评测 → 报告 → 台账」，断点续跑（已 DONE 跳过、
   已载镜像直评、单实例失败不阻断）。

**验收锚点**

- gold 口径 **8/8 resolved**（跨 django×3 / sympy×2 / astropy / scikit-learn
  四仓）：run 报告在 `reports/swebench/code-review-agent.gold.*.json`（8 份）。
- 本轮再补 **agent 侧口径**（编码循环产补丁）：`skills/eval-harness/scripts/
  agent-sample.py` + 台账 `datasets/swe-out/agent-sample/eval5/`。
- 结论：网络窗口不再是扩样的前置条件——**镜像获取已不依赖 docker 客户端，
  也不依赖 github 直连**（国内 gitee 镜像 + 逐层下载器覆盖四仓）。

## 坑 ea05cfe2247f（docker 客户端在慢 CDN 下假启动）→ closed

**原坑**：docker 客户端的 "Pulling from" 是假启动——manifest 秒回、blob 307→CDN
挂死，40 分钟零层完成；探针实测 blob 段仅 258KB/s（round-10）。

**对策落地**：同上的逐层下载器（`scripts/docker-image-fetch.py`）——用
curl 语义（跨主机剥 Authorization、Range 断点续传）直接取 blob，sha256 强制
校验后组装 OCI tar 再 `docker load`。**docker 客户端路径降级为兜底，主路径
不再经过它。**

**验收锚点**

- 实测吞吐：16 段 99KB/s（round-13），窗口期 5.4GB 镜像数十分钟完成
  （round-17）；7 个评测镜像现均已 `docker load` 就位（`docker images`
  实测：django_1776 ×3、sympy_1776 ×2、astropy_1776、scikit-learn_1776）。
- 本轮 7 例 agent 补丁 + 8 例 gold 补丁的 harness 判定全部跑在**这些镜像**
  之上（台账 `datasets/swe-out/agent-sample/eval5/`、
  `datasets/swe-out/gold-sample/gold-sample-ledger.json`），即产出链路本身
  已被真实评测闭环验证。

**遗留（如实记录）**：国际直连（github/dockerhub）在部分时段仍不可达；
主路径已改为国内源优先（铁律 8），直连仅作回退并记录降级原因——这不是
未结坑，而是已固化的下载纪律。
