# 复盘轮报 round-17

open 2 / closed 42

## 分类统计

- 手工：39
- 误报：3
- 行为回归：2

## 未结坑明细

| ID | 类别 | 坑 | 根因 | 对策 | 来源 |
|---|---|---|---|---|---|
| 59b6f195b91c | 手工 | Phase 3B 扩样三路由实测全阻：① swe-bench-tasks 任务仓（github 直连 21s 连接失败、 | 本机网络窗口对 github/dockerhub 生态整体不可达（round-5 | 扩样材料已备齐待窗口：datasets/swebench/lite-test-i | retro/events-round-gold6.json |
| ea05cfe2247f | 手工 | docker 客户端拉取在慢 CDN 下假启动复现：curl 逐层实测 blob 258KB/s（较 round-8 的 | docker 客户端对 307→CDN 的 blob 流处理在慢源下疑似无限等待 | 镜像获取第三条路：curl -C - 断点续传逐层下载 + docker loa | retro/events-round-baseline-reg.json |

## 改进候选（按 权重×数量 排序）

- **手工：2 个未结坑** — 纳入下一轮改进候选，明确责任与验收口径
