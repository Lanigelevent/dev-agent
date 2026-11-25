# SAST 自查（round-146，astgrep 安全族对自身仓）

- 扫描面：skills/*/scripts + llm + agent + engines 共 103 文件；发现 107 条。
- 规则分布：{"astgrep:print-debug": 107}
- **设计性误报澄清**：print-debug 为主——本仓 CLI 契约（硬约束 2）stdout 单一 JSON 输出，print 是合法通道，不构成缺陷。
- 非 print 发现 0 条：[]
- **round-151 完整性勘误**：首扫 7 个大文件因 WinError 206（argv 32K 上限）
  扫描失败——适配器 payload 文件传输修复后 103 文件全量 0 错误、134 条
  （补齐 27 条同为 print-debug 设计性输出）；安全族仍零命中。
