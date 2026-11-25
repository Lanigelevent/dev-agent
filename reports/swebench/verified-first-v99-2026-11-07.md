# round-99 verified 首批开跑：n=5（2 判 f2p_passed + 3 blocked）

## 结论先行

- **批次**：gate-v99 = astropy-12907 / django-10880 / seaborn-3069 /
  flask-5014 / requests-1142（D-052 批准：中档口径 + n=5 + difficulty/
  plen 过滤；取源 5/5 gitee 无降级）。
- **结果（partial 不折算 resolved）**：
  - **mwaskom__seaborn-3069 = f2p_passed**（F2P 2/2；修法=Nominal scale
    三 tweaks 落 _finalize 基建（grid off / ±0.5 半步限 / y 反转）+
    plot.py 接线——gold 对照 0.13.0）。
  - **pallets__flask-5014 = f2p_passed**（F2P 1/1；修法=Blueprint 空名
    ValueError——纯自研，无 gold 对照）。
  - astropy-12907 = **blocked_data**（hypothesis 入 setup 后 venv 重建
    仍缺，待查 setup 执行面）。
  - django-10880 = **blocked_data**（verified F2P 节点为 django-runner
    格式「test_x (module.Class)」，pytest 无法收集——**判分链节点格式
    转换缺口**，环境本身可收集 175 项）。
  - psf__requests-1142 = **env_blocked**（2014 年代 py2 vendored 布局，
    r94 同根因）。
- **口径**：模型轴=host 会话模型（r94 同轴）；零反馈累计 **3/7 不变**
  + gold-assisted 3 例（r96×2 + 本轮 seaborn）+ 纯自研 host 轴 1 例
  （flask-5014）。n 值不外推。
- **verified 折损率实测**：5 例中 3 blocked（60%）——与评估报告预测
  （30-50%）一致偏高，django 判分链格式缺口为新增形态。

## 产品/判分链缺口（留观 → 修正候选）

1. **django-runner 节点格式转换**：verified 的 django 系 F2P/P2P 全为
   「test_x (module.Class)」格式，判分前需转 pytest node id（机械映射
   module→file + :: 拼接）——修好即解锁 verified 的 django 231 例。
2. astropy 的 setup_cmds 执行面排查（hypothesis 钉入未生效）。

## 证据

- 批次：datasets/swebench/verified/gate-v99-batch.jsonl（+ v99-notes/）
- 判分：reports/_work/v99/live-sample-ledger.json
- 补丁：datasets/swebench/verified-runs-v99/<iid>/single/out/edits.patch
- gold 对照：seaborn 0.13.0（logs/r96-goldref/s13.tar.gz）
