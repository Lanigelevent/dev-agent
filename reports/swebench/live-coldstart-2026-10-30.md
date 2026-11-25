# round-66 冷启动资源面收口：官方镜像命名确认 + Docker Hub 全链路不可达判定 + 补源 9/9

日期：2026-10-30 ｜ 版本：v1.67.0 ｜ 状态：镜像命名规则源码级确认；可达性按硬约束 8 实测判死；补源 9/9 就位；**本轮零冷启动 resolved / f2p_passed 主张**

## 结论

1. **官方镜像命名规则已确认（源码级）**：SWE-bench Live 官方 harness
   （microsoft/SWE-bench-Live `evaluation/evaluation.py` 的
   `get_default_image_name`）构造为
   `starryzhang/sweb.eval.x86_64.<instance_id 双下划线→_1776_ 小写>`
   （linux 平台 med=x86_64，win 平台 med=win）。round-64 时连命名规则都
   未确认——这是本轮的净增量，后续任何可达性恢复后的探测可直接引用。
2. **可达性按硬约束 8 实测判死，不傻等**：国内 8 源（docker.1ms.run /
   docker.1panel.live / hub.rat.dev / docker.m.daocloud.io / dockerproxy.net /
   docker.xuanyuan.me / dockerhub.icu / registry.dockermirror.com）对
   llama_deploy-330 官方镜像探测 `usable_rank=[]`——token/manifest 阶段
   SSL 握手超时 / 401 / 无认证 realm；`hub.docker.com` 元数据 API 8/8 超时；
   国际直连回退 `registry-1.docker.io`（降级原因：国内 8 源判死 + hub 元数据
   不可达）也在 token 阶段超时。Docker Hub 全链路从本网络不可达，D-045 的
   `resolved` 口径在本机**仍然阻塞**，阻塞点从 round-64 的「未曝光官方镜像」
   收窄为「官方镜像存在性与命名已确认、拉取链路不可达」。
3. **补源 9/9 全就位**：round-65 的 5/7 + 本轮 4 条——haystack GitHub 3 s /
   7 011 KB、reflex GitHub 2 s / 2 883 KB（单提交 depth-1 取法验证有效，
   「全量克隆 429/211 MB」的担忧不成立）、instructlab GitHub 2 s / 7 327 KB、
   pvlib-python GitHub 4 s / 34 803 KB（round-65 双源超时为网络抖动，本轮
   重试解锁）。sha 完整性逐一 cat-file 验证通过。
4. **D-045 执行面现状（如实）**：九条候选「源就位 9/9 + 镜像可达 0/9 +
   基线可判 1/9」（llama_deploy-330 已 `baseline_ok`，round-65）；其余 8 条
   基线未跑。`resolved` 口径待镜像可达性；`f2p_passed` 部分口径的通路已就绪
   （live-sample.py 本地 venv pytest），跑不跑由预算决定（D-045：跑不动
   记 blocked 不补位，样本量如实缩水）。

## 1. 官方镜像命名规则（源码级确认）

SWE-bench Live 官方 harness
[microsoft/SWE-bench-Live](https://github.com/microsoft/SWE-bench-Live)
`evaluation/evaluation.py` `get_default_image_name`（逐字引用）：

```python
def get_default_image_name(instance_id: str, platform: Literal["windows", "linux"]) -> str:
    if platform == "linux":
        med = "x86_64"
    else:
        med = "win"
    name = instance_id.replace("__", "_1776_").lower()
    image = f"starryzhang/sweb.eval.{med}.{name}"
    return image
```

> 逐字引用自 microsoft/SWE-bench-Live `evaluation/evaluation.py`
> `get_default_image_name`（GitHub API base64 原文转写，round-66 已核对）。
> 实例行可自带 `docker_image` 字段（harness `instance.get("docker_image",
> get_default_image_name(...))`），本地 lite.parquet 无该列，故默认命名生效。

## 2. 可达性实测（硬约束 8：国内源优先、慢即判死）

### 2.1 国内 8 源（docker-mirror-probe.py，llama_deploy-330 官方镜像）

| 源 | 阶段 | 结果 | 耗时 |
| --- | --- | --- | --- |
| docker.1ms.run | token | SSL 握手超时 | 16.3 s |
| docker.1panel.live | token | SSL 握手超时 | 18.5 s |
| hub.rat.dev | token | HTTP 401 | 0.6 s |
| docker.m.daocloud.io | token | SSL 握手超时 | 16.3 s |
| dockerproxy.net | token | SSL 握手超时 | 18.3 s |
| docker.xuanyuan.me | token | SSL 握手超时 | 15.5 s |
| dockerhub.icu | token | SSL 握手超时 | 30.4 s |
| 8 源合计 | — | `usable_rank=[]` | — |

`usable_rank=[]`——与 round-64 结论一致。

### 2.2 Docker Hub 全链路 / 国际直连回退

| 端点 | 用途 | 结果 |
| --- | --- | --- |
| hub.docker.com/v2/repositories/...（8 镜像逐个） | 元数据存在性核查 | 8/8 超时（12 s/请求） |
| registry-1.docker.io（token→manifest→blob） | 国际直连回退 | token 阶段 30 s 超时 |

降级记录：国内 8 源 usable_rank=[] 且 hub.docker.com 元数据不可达，才走
registry-1.docker.io 回退；回退也判死，未拉取任何镜像、未伪造状态。

## 3. 补源 9/9（datasets/swe-repos/，不入库）

| 仓库（实例） | 来源（秒） | 大小 | 轮次 | 状态 |
| --- | --- | --- | --- | --- |
| conan（conan-17092） | GitHub 37 | 1 487 KB | round-65 | 源就位 |
| cfn-lint（cfn-lint-3749） | GitHub 73 | 2 699 KB | round-65 | 源就位（实例不可判：malformed_node_ids） |
| keras（keras-20389） | gitee 2 | 1 595 KB | round-65 | 源就位 |
| llama_deploy（llama_deploy-330） | GitHub 58 | 2 043 KB | round-65 | 源就位 + baseline_ok |
| pdm（pdm-3237） | GitHub 85 | 2 979 KB | round-65 | 源就位 |
| haystack（haystack-8489） | GitHub 3 | 7 011 KB | round-66 | 源就位 |
| reflex（reflex-4087） | GitHub 2 | 2 883 KB | round-66 | 源就位 |
| instructlab（instructlab-2526） | GitHub 2 | 7 327 KB | round-66 | 源就位 |
| pvlib-python（pvlib-2249） | GitHub 4 | 34 803 KB | round-66 | 源就位 |

## 4. 对 D-045 的影响

- 资源面从 round-65 的「源 5/9、镜像 0/9、基线 1/9」推进到
  「**源 9/9、镜像 0/9（命名已确认）、基线 1/9**」。
- `resolved` 口径仍阻塞于 Docker Hub 全链路不可达；`f2p_passed` 部分口径
  通路就绪（本地 venv pytest），跑不跑由预算决定，blocked 原样保留不补位。
- 阻塞点收窄的表述：round-64「未曝光官方镜像」→ round-66「官方镜像存在性
  与命名已确认、拉取链路不可达」。后续任何网络面变化（镜像源恢复、代理
  可用、获得授权的镜像搬运）都可用本轮确认的命名规则直接探测。

## 5. 证据与复跑

```
# 官方镜像探测（国内 8 源）
.venv/Scripts/python.exe scripts/docker-mirror-probe.py \
  --image starryzhang/sweb.eval.x86_64.run-llama_1776_llama_deploy-330

# 国际直连回退（记录降级原因后）
.venv/Scripts/python.exe scripts/docker-mirror-probe.py \
  --image starryzhang/sweb.eval.x86_64.run-llama_1776_llama_deploy-330 \
  --mirrors registry-1.docker.io

# 补源（单提交 depth-1，硬约束 8 纪律：gitee 优先 → GitHub 回退，各 150s 上限；
# 取法定式 = git init + remote add + fetch --depth 1 origin <sha>，round-51 定式）
git -C datasets/swe-repos/haystack fetch --depth 1 origin 906177329bcc54f6946af361fcd3d0e334e6ce5f
# （新目录需先 git init + remote add origin https://github.com/deepset-ai/haystack.git）
```

证据文件：`logs/seed-live-sources.log`（round-65）、
`logs/seed-live-sources-r66.log`（本轮四条）、`logs/mirror-probe-r66-llamadeploy.json`
（可达性判死原始 JSON）、`datasets/swe-repos/`（不入库）、
`reports/swebench/live-coldstart-2026-10-30.md`（本报告）。

## 6. 边界（不宣称的部分）

- 本轮**零**冷启动 resolved / f2p_passed 结论；命名规则确认与可达性判定
  只回答「资源面能不能拉镜像」，不回答「agent 能不能解」。
- 镜像存在性未经官方 registry 确认（hub.docker.com 与 registry-1.docker.io
  均不可达）——命名规则来自官方 harness 源码，但「该命名下镜像已发布」
  未经验证，网络恢复后先探测存在性再谈拉取。
- instructlab/pvlib 的 round-65 超时判死结论被本轮重试推翻——「慢即判死」
  是单次跑次纪律，跨轮重试合法且本轮已把降级原因逐次记录。
