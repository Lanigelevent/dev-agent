# 复盘轮报 round-26

open 9 / closed 68

## 分类统计

- 手工：69
- 行为回归：3
- 误报：3
- 补丁返工：2

## 未结坑明细

| ID | 类别 | 坑 | 根因 | 对策 | 来源 |
|---|---|---|---|---|---|
| 04b97450c2ff | 手工 | astropy-14365（QDP 命令大小写不敏感）第三版仍 unresolved：命令段已大小写无关（该文件 8/9 | issue 只提了命令，但格式语义是整体的；上游期望（写回路径的大小写、roun | 按检查单建议再试一版（整条 _type_re 用 re.IGNORECASE 编 | retro/events-round-20.json |
| 0a290edc8ade | 手工 | sympy-13146（Float 指数的 evalf 结果不抵消）第三版定位并修复：`_aresame` 只用 `!= | evalf 后 x**2.5 的指数是 prec 53（默认精度，未被重新 ev | `_aresame` 追加 Float 精度比较（精度不同即视为不同）→ Mul | retro\events-round-26.json |
| 1336d8bf9067 | 手工 | 扩样到 n=18：sklearn-14087 / sklearn-14092 / matplotlib-22711 /  | 首轮补丁常只修到症状层：14087 两处根因叠加（分支判断用了构造参数、list | 把 harness 反馈当规格用：失败时分桶信息（哪几个参数化过了、哪几个没过） | retro\events-round-24.json |
| 1e32072ad9ee | 手工 | 并发会话在同一仓库改同一批文件：接手会话开始后，上一会话又继续跑了 round-22/round-23 并提交（口径复算 | 同一工作区允许多个会话并行推进，彼此不知情；提交用 git add -A 会把别 | 每个会话只提交自己负责的文件路径（git add <具体路径>，不用 -A）；改 | retro\events-round-24.json |
| 49fa4d3befa5 | 手工 | 扩样链路收官：13 个扩展镜像全部就位（12/13 经共享缓存 + 最后 1 个经**进程私有缓存**下载，绕开并发会话 | 两个会话共用同一 imagecache → docker-image-fetch | 本轮取最后一个镜像改用进程私有缓存目录（不动并行会话正在用的下载器）；正式修法（ | retro/events-round-25.json |
| 5cf72b52d188 | 手工 | matplotlib-22835（scalar mappable 的 format_cursor_data 在 Boun | Artist.format_cursor_data 无条件调用 self.nor | 改为 try/except：inverse 抛错时回退到默认有效位数（3），正常 | retro/events-round-25.json |
| 7122b4b567a4 | 手工 | sympy-13437 长期未过却没进台账：F2P `test_bell` 在 agent7/agent8/agent1 | 未过实例只在正文叙述里记录，没有与「扩样余量」这类坑条目建立一一对应；口径复算时 | 本轮把三个未过实例（astropy-14365 / django-11019 / | retro\events-round-24.json |
| b0a450995f3d | 手工 | 定位上游语义的一个可复用手法：拿**新版库的实际行为**当规格反推根因，比逐行读上游补丁更快也更不容易被实现细节带偏 | 两处根因都藏在「同一个数学对象在两处的精度/结构不同」这种细节上（sympy 的 | sympy-13146：本地装一份新版 sympy 实测同一段代码的输出差异（1 | retro\events-round-26.json |
| c6434af6f7e6 | 手工 | matplotlib-22835 仍 unresolved：本轮把「不可反演的 norm 该怎么给有效位数」摸清了一半— | 上游期望是逐值给有效位数（`cbook._g_sig_digits` 只看 de | 保留为未结项并把线索写细：下一轮可直接从「边界命中时 delta 取半宽」这个方 | retro\events-round-26.json |

## 改进候选（按 权重×数量 排序）

- **手工：9 个未结坑** — 纳入下一轮改进候选，明确责任与验收口径
