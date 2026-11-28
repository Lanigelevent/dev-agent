# 安全政策（Security Policy）

## 支持版本

| 版本 | 支持状态 |
|---|---|
| main（v2.x 最新） | ✅ 支持，安全问题按下方渠道报告 |
| 更早 tag | ❌ 不再单独修复，请升级到 main |

## 报告漏洞

**请勿在公开 issue 中披露可被利用的细节。** 请通过 GitHub 私有渠道报告
（Security Advisories → Report a vulnerability），或联系仓库所有者；72 小时内确认收到，
修复或缓解方案与披露时间线将与你协商确定。

## 范围与设计边界

- 本项目的安全承诺是**治理面**：唯一写入口 + 五道闸（批准书 sha256 绑定、工作树干净、
  HEAD 与 base_sha 一致、git apply 预检、行为回归）+ 失败自动回滚 + 产物脱敏（硬约束 5）。
- 评审/修复动作只针对被审仓库**只读**，除 `fix-apply.py` 外不存在写路径。
- 明确不在承诺内：被审仓库自身代码的漏洞（那是评审的产出对象而非本工具的攻击面）、
  宿主环境自身的安全配置、LLM 端点侧的服务质量（见 README「已知限制」）。

## 已知安全机制

- MCP stdio 服务器：进程边界即信任边界；16 工具清单 sha256 固化 + 分级门控
  （`mcp/tools-pin.json`、`mcp/tools-policy.json`，漂移拒服务）。
- LLM 端点 SSRF 白名单（公网 https 或回环，重定向逐跳复验）；响应体读取封顶。
- 凭据形态扫描与 PII 出站脱敏闸（`secret-scan.py`、`pii-scan.py`）。
