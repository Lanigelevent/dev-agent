# dev-agent 容器镜像（r243：分发面 + workspace 容器档真机验证）
# 治理壳 stdlib 直接可跑；引擎层经 uv.lock 锁安装（linux x86_64 wheels）
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml uv.lock requirements-lock.txt README.md LICENSE ./
COPY skills/ skills/
COPY engines/ engines/
COPY agent/ agent/
COPY llm/ llm/
COPY mcp/ mcp/
COPY tests/ tests/
COPY docs/ ./docs/
COPY interop/ interop/

RUN pip install --no-cache-dir uv \
    && uv sync --extra dev --frozen

ENV PATH="/app/.venv/bin:$PATH"
