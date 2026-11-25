# round-102 verified 首批续：django-10880 f2p_passed + runtests 判分口径落地

## 结论先行

- **django__django-10880 = f2p_passed**（F2P 1/1；补丁 +1/−1 单空格；
  纯自研——`DISTINCT` 后缺空格致 `DISTINCTCASE` 语法错误）。
- **runtests 判分口径落地**（live-sample `test_runner: django-runtests`）：
  verified 的 django 系任务原标签直喂 runtests.py（自带 settings 配置 +
  django.setup() 引导），判分走 unittest -v 2 输出解析（全点分名含括号
  子串匹配）。解锁 verified django 系 231 例的判分通路。
- **修复过程**：四层推进（r101）→ runtests 口径（本轮）→ 循环 1 跳
  收敛（读测试+代码→单空格编辑）→ runtests 判分 f2p_passed。
- **verified 首批终态**：3 判 f2p_passed（seaborn-3069 gold-assisted /
  flask-5014 纯自研 / django-10880 纯自研）+ 2 blocked（astropy
  blocked_data / requests env_blocked）。折损 2/5=40%。
- **口径**：模型轴=host 会话模型；零反馈累计 3/7 不变 + gold-assisted
  3 例 + 纯自研 host 轴 2 例。n 值不外推。
- **版本 2.3.0**；契约 **609 不变**；脚本 79 不变；live-sample 产品
  代码改动（runtests 口径 + django 节点转换，上轮 + 本轮）。
- **台账**：无新坑（237 条 / open 4 / closed 209 不变）。
- **证据**：reports/_work/v99/live-sample-ledger.json；
  datasets/swebench/verified-runs-v99/<iid>/single/out/edits.patch。

## 过程要点

1. runtests 口径落地四步：①`test_runner` 任务字段分支（cmds 替换 +
   judge 双路）②unittest -v 2 输出判分器 `_judge_django_runtests`
   （全点分名含括号子串匹配）③cmd.exe 双引号标签（POSIX 单引号
   不认）④python 路径绝对化（相对路径在 cwd=repo_dir 下断裂——
   r51 同根因复发）。
2. judge 的 FAILED 语义修正：F2P 在 base FAILED（正确基线行为）不再
   计入 missing（missing 专指收集失败/结果缺失）。
