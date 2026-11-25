"""engines — 复用引擎适配层（允许第三方依赖，AGENTS.md 硬约束 1 白名单）。

每引擎一个 adapter：对外暴露统一诊断/补丁接口，产物一律经
repair/scripts/fix-apply.py 的五道闸落盘；引擎能力矩阵见 BASELINE.md。
Phase 2A 填充：ruff_adapter.py（lint+autofix）、libcst_adapter.py（codemod）。
"""
