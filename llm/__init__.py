"""llm — 模型提供者抽象层（治理壳，stdlib 零依赖）。

两种后端（provider.select 选择）：
- openai 兼容：REVIEW_LLM_BASE_URL/MODEL/API_KEY 环境变量，SSRF 白名单与重试；
- host 宿主模型：CRA_LLM_PROVIDER=host 时启用，提示词文件进出协议
  （<run>/llm-tasks/<id>.prompt.md ↔ .response.md），桌面端宿主模型
  按 SKILL.md 填写响应后 --resume 续跑；幂等 id=sha256(system+user)[:12]。
"""
