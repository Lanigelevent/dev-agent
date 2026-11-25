# 规则：可变共享状态的派生数据同步

**适用**：Python 类/对象持有派生状态（缓存数组、句柄列表、索引表）的方法改动。

**判据**：改动某个引发状态迁移的方法（set/update/reset 类）时，必须列出所有
持有该状态派生副本的对象属性或外部引用，逐一确认同步路径存在且被调用。

**反例形态**：`set_val(v)` 更新了 `self.val`，但 `self.handles`（按旧 val
派生的位置数组）未重算——读侧拿到 `val=[0.2,0.6]` 而 `handles=[0.1,0.34]`，
状态自相矛盾。

**评审动作**：对 set/update 类方法的 diff，问一句"这个方法改的状态，还有谁
持有旧副本？"——答不出就要求补证据。

出处：SWE-bench 实例 matplotlib__matplotlib-22711（round-33 容器探针实测
定位；状态探针见 reports/swebench/probe-state-22711.json）。
