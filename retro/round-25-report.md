# 复盘轮报 round-25

open 6 / closed 68

## 分类统计

- 手工：66
- 行为回归：3
- 误报：3
- 补丁返工：2

## 未结坑明细

| ID | 类别 | 坑 | 根因 | 对策 | 来源 |
|---|---|---|---|---|---|
| 04b97450c2ff | 手工 | astropy-14365（QDP 命令大小写不敏感）第三版仍 unresolved：命令段已大小写无关（该文件 8/9 | issue 只提了命令，但格式语义是整体的；上游期望（写回路径的大小写、roun | 按检查单建议再试一版（整条 _type_re 用 re.IGNORECASE 编 | retro/events-round-20.json |
| 1336d8bf9067 | 手工 | 扩样到 n=18：sklearn-14087 / sklearn-14092 / matplotlib-22711 /  | 首轮补丁常只修到症状层：14087 两处根因叠加（分支判断用了构造参数、list | 把 harness 反馈当规格用：失败时分桶信息（哪几个参数化过了、哪几个没过） | retro\events-round-24.json |
| 1e32072ad9ee | 手工 | 并发会话在同一仓库改同一批文件：接手会话开始后，上一会话又继续跑了 round-22/round-23 并提交（口径复算 | 同一工作区允许多个会话并行推进，彼此不知情；提交用 git add -A 会把别 | 每个会话只提交自己负责的文件路径（git add <具体路径>，不用 -A）；改 | retro\events-round-24.json |
| 49fa4d3befa5 | 手工 | 扩样链路收官：13 个扩展镜像全部就位（12/13 经共享缓存 + 最后 1 个经**进程私有缓存**下载，绕开并发会话 | 两个会话共用同一 imagecache → docker-image-fetch | 本轮取最后一个镜像改用进程私有缓存目录（不动并行会话正在用的下载器）；正式修法（ | retro/events-round-25.json |
| 5cf72b52d188 | 手工 | matplotlib-22835（scalar mappable 的 format_cursor_data 在 Boun | Artist.format_cursor_data 无条件调用 self.nor | 改为 try/except：inverse 抛错时回退到默认有效位数（3），正常 | retro/events-round-25.json |
| 7122b4b567a4 | 手工 | sympy-13437 长期未过却没进台账：F2P `test_bell` 在 agent7/agent8/agent1 | 未过实例只在正文叙述里记录，没有与「扩样余量」这类坑条目建立一一对应；口径复算时 | 本轮把三个未过实例（astropy-14365 / django-11019 / | retro\events-round-24.json |

## 改进候选（按 权重×数量 排序）

- **手工：6 个未结坑** — 纳入下一轮改进候选，明确责任与验收口径
