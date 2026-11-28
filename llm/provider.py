#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM 提供者抽象层（治理壳，零第三方依赖，AGENTS.md 硬约束 1）。

后端选择（select）：
- 显式 CRA_LLM_PROVIDER=host|openai|none 优先；
- 未显式：已配置 REVIEW_LLM_BASE_URL + REVIEW_LLM_MODEL → openai；
- 否则 none（返回 None 不阻塞调用方——保持既有降级语义）。

openai 后端：泛化自编排器 _llm_call——SSRF 白名单（公网 https 或回环；
内网/私有/保留地址拒绝）、重定向逐跳复验（302 跳内网/保留段即拒）、
响应体分块读取封顶（超限报错不撑内存）、重试参数读 agent.json args、
token 经回调上报。
host 宿主模型后端（桌面端会话内推荐，零 API key）：提示词文件进出协议——
幂等 id=sha256(system+"\\0"+user)[:12]；无响应时写 <base>/<id>.prompt.md 并
抛 HostLLMPending（调用方转 WAIT_HOST_LLM）；宿主模型填写 <id>.response.md
后 --resume 续跑，同材料同 id 命中响应直接返回。

用法示例（调用方）：
    from llm import provider
    text, meta = provider.complete(system, user, base_dir=<run>/llm-tasks,
                                    args=agent_args, on_tokens=回调)

本模块是库，无退出码；HostLLMPending 由编排器转 WAIT_HOST_LLM（退出码 1）。
"""
from collections.abc import Callable
import hashlib
import ipaddress
import json
import os
import re
import socket
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

RESERVED_HOST_PAT = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|169\.254\.|::1$|"
    r"172\.(1[6-9]|2\d|3[01])\.)")
MAX_RESPONSE_BYTES = 4 * 1024 * 1024   # 响应体读取上限（OWASP：限制响应大小）
_READ_CHUNK = 65536                    # 分块读取块大小


class HostLLMPending(Exception):
    """host 后端等待宿主模型填写响应；调用方应转 WAIT_HOST_LLM 并支持 --resume。"""

    def __init__(self, task_id, prompt_path, response_path):
        self.task_id = task_id
        self.prompt_path = prompt_path
        self.response_path = response_path
        super().__init__("WAIT_HOST_LLM:%s" % task_id)


class _SSRFRejected(Exception):
    """SSRF 白名单拒绝（重定向跳转违规）；不可重试，立即返回错误。"""


def _endpoint_error(raw_url: str,
                    resolve: bool = False) -> str | None:
    """SSRF 白名单检查（:97-110 同源逻辑，初连与重定向逐跳复用）。

    返回 None=放行；否则错误文案（含「白名单拒绝」）。回环端点豁免
    （localhost/127./::1 显式放行，测试回环端点依赖此开关）。
    resolve=True（重定向跳转目标不可信）时对域名跳转目标做 DNS 解析并
    逐 IP 复核保留段（is_private/is_loopback/is_link_local），防公网
    域名 302 跳内网；域名解析失败交由真实请求自然失败，不误报 SSRF。
    """
    parsed = urllib.parse.urlparse(raw_url)
    host = (parsed.hostname or "").lower()
    loopback = host in ("localhost", "::1") or host.startswith("127.")
    if not host:
        return "SSRF 白名单拒绝: 空 host"
    if parsed.scheme != "https" and not loopback:
        return "非 https 公网端点被白名单拒绝"
    if not loopback and (host.startswith("10.") or host.startswith("192.168.")
                         or host.startswith("169.254.")
                         or host.endswith((".internal", ".local"))
                         or RESERVED_HOST_PAT.match(host)):
        return "内网地址被白名单拒绝: %s" % host
    if loopback:
        return None
    # IP 字面量保留段复核：字符串白名单漏网形态（如 IPv6 映射
    # ::ffff:192.168.1.1）由 ipaddress 判定兜底；域名无 IP 形态跳过。
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if addr is not None and (addr.is_private or addr.is_loopback
                             or addr.is_link_local):
        return "解析 IP 命中保留段被白名单拒绝: %s" % host
    if resolve and addr is None:
        try:
            infos = socket.getaddrinfo(host, None)
        except OSError:
            return None  # 解析失败不误报 SSRF，交由真实请求自然失败
        for info in infos:
            ip_text = info[4][0]
            try:
                hop = ipaddress.ip_address(ip_text.split("%")[0])
            except ValueError:
                return "解析 IP 形态异常被白名单拒绝: %s → %s" % (host, ip_text)
            if hop.is_private or hop.is_loopback or hop.is_link_local:
                return "解析 IP 命中保留段被白名单拒绝: %s → %s" % (host, ip_text)
    return None


class _SSRFRedirectHandler(urllib.request.HTTPRedirectHandler):
    """重定向逐跳复验：每一跳重跑白名单 + ipaddress 解析 IP 保留段检查。

    违规跳转抛 _SSRFRejected（不跟进、不重试），替代默认「跟随任何
    http(s) 跳转」行为——302 跳内网是 OWASP SSRF 防护清单的典型绕过。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        err = _endpoint_error(newurl, resolve=True)
        if err:
            raise _SSRFRejected(err)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_SSRF_OPENER_INSTALLED = False


def _ensure_ssrf_opener():
    """urlopen 全局走 SSRF opener（重定向逐跳复验），进程内幂等一次。

    仍以 urllib.request.urlopen 为调用面——既有单测对 urlopen 的打桩
    （tests/test_agent.py TestOpenAIProviderJSONMode._patch_urlopen）
    依赖该调用面；install_opener 进程级生效，其余 urlopen 调用方一并
    获得重定向复验（行为差异仅限违规重定向被拒，其余默认行为不变）。
    """
    global _SSRF_OPENER_INSTALLED
    if not _SSRF_OPENER_INSTALLED:
        urllib.request.install_opener(
            urllib.request.build_opener(_SSRFRedirectHandler()))
        _SSRF_OPENER_INSTALLED = True


def _read_capped(r, cap):
    """分块读取响应体并封顶：超限抛错不撑内存（OWASP 响应大小限制）。

    64KB 分块推进，累计超 cap 立即中止（后续字节不再读入内存）。
    """
    chunks, total = [], 0
    while True:
        chunk = r.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > cap:
            raise ValueError("响应体超上限被拒绝: %d > %d" % (total, cap))
        chunks.append(chunk)
    return b"".join(chunks)


def select(env: dict | None = None) -> str:
    """决定当前后端：显式指定 > openai 环境完备 > none。"""
    env = os.environ if env is None else env
    mode = (env.get("CRA_LLM_PROVIDER") or "").strip().lower()
    if mode in ("host", "openai", "none"):
        return mode
    if env.get("REVIEW_LLM_BASE_URL") and env.get("REVIEW_LLM_MODEL"):
        return "openai"
    return "none"


def task_id(system: str, user: str) -> str:
    """幂等任务 id：同一提示词（同一评审材料）跨重跑不变。"""
    return hashlib.sha256(
        (system + "\x00" + user).encode("utf-8")).hexdigest()[:12]


def complete(system: str, user: str, base_dir: str | None = None,
             args: dict | None = None,
             on_tokens: "Callable[[int], None] | None" = None) -> tuple[str | None, dict]:
    """统一入口：返回 (text|None, meta)；host 等待时抛 HostLLMPending。"""
    mode = select()
    if mode == "none":
        return None, {"provider": "none"}
    if mode == "host":
        return _host_complete(system, user, base_dir)
    return _openai_fallback(system, user, args or {}, on_tokens)


def _host_complete(system: str, user: str,
                   base_dir: str | None) -> tuple[str, dict]:
    base = Path(base_dir) if base_dir else Path.cwd() / "llm-tasks"
    base.mkdir(parents=True, exist_ok=True)
    tid = task_id(system, user)
    response = base / ("%s.response.md" % tid)
    if response.is_file():
        text = response.read_text(encoding="utf-8", errors="replace")
        return text, {"provider": "host", "task_id": tid,
                      "response": str(response)}
    prompt = base / ("%s.prompt.md" % tid)
    prompt.write_text("# system\n\n%s\n\n# user\n\n%s\n" % (system, user),
                      encoding="utf-8", newline="\n")
    (base / ("%s.meta.json" % tid)).write_text(
        json.dumps({"status": "waiting", "task_id": tid,
                    "prompt": prompt.name}, ensure_ascii=False),
        encoding="utf-8", newline="\n")
    raise HostLLMPending(tid, str(prompt), str(response))


def _openai_complete(system: str, user: str, args: dict | None,
                     on_tokens: "Callable[[int], None] | None",
                     base_url: str | None = None, model: str | None = None,
                     api_key: str | None = None) -> tuple[str | None, dict]:
    base_url = base_url if base_url is not None else os.environ.get("REVIEW_LLM_BASE_URL", "")
    model = model if model is not None else os.environ.get("REVIEW_LLM_MODEL", "")
    parsed = urllib.parse.urlparse(base_url)
    host = (parsed.hostname or "").lower()
    loopback = host in ("localhost", "::1") or host.startswith("127.")
    if not host or not model:
        return None, {"provider": "openai", "error": "未配置 BASE_URL/MODEL"}
    err = _endpoint_error(base_url)
    if err:
        return None, {"provider": "openai", "error": err}
    cb = _circuit_check()
    if cb is not None:
        return None, {"provider": "openai", "error": cb, "circuit": "open"}
    port = parsed.port
    netloc = host + (":%d" % port if port else "")
    url = urllib.parse.urlunparse(
        (parsed.scheme, netloc, "/chat/completions", "", "", ""))
    body = {
        "model": model, "temperature": 0,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    # round-77：部分 openai 兼容端点（如 DeepSeek）的工具调用先验会把
    # 结构化协议输出劫持成私有标记（DSML），导致编码循环整轮不可解析；
    # JSON 模式在端点侧强制合法 JSON 输出（提示词已含 "JSON" 满足
    # DeepSeek 的要求）。默认关闭，经环境变量显式开启。
    if os.environ.get("REVIEW_LLM_JSON_MODE", "") == "1":
        body["response_format"] = {"type": "json_object"}
    body = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    api_key = api_key if api_key is not None else os.environ.get("REVIEW_LLM_API_KEY", "")
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    attempts = int((args or {}).get("retry_max_attempts", 3) or 3)
    backoff = int((args or {}).get("retry_backoff_base_seconds", 2) or 2)
    _ensure_ssrf_opener()
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(_read_capped(r, MAX_RESPONSE_BYTES)
                                  .decode("utf-8"))
            usage = data.get("usage") or {}
            if on_tokens and usage:
                on_tokens(usage.get("total_tokens", 0))
            content = data["choices"][0]["message"]["content"]
            # round-77：个别端点在 JSON 模式下偶发空内容响应（finish 原因
            # 不明），空内容对编码循环等于浪费一轮——按可重试失败处理。
            if not (content or "").strip():
                raise ValueError("empty content from endpoint (retryable)")
            _circuit_record_success()
            return content, {
                "provider": "openai", "model": model}
        except _SSRFRejected as exc:
            return None, {"provider": "openai", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - 网络层重试
            last_error = str(exc)
            if attempt >= attempts:
                _circuit_record_failure()
                return None, {"provider": "openai", "error": last_error}
            time.sleep(backoff * attempt)
    return None, {"provider": "openai", "error": last_error}



# ---- M5 多端点 fallback 链（批次二 M5，round-234）----
def _endpoint_chain():
    """端点链：REVIEW_LLM_ENDPOINTS（JSON 数组）优先，缺省回退单端点 env。

    形态 [{"base_url","model","api_key"?}...]；每端点过 _endpoint_error
    （SSRF 白名单逐端点不放松），违规端点剔除并 stderr 记录降级原因。
    """
    raw = os.environ.get("REVIEW_LLM_ENDPOINTS", "")
    chain = []
    if raw.strip():
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                for e in data:
                    if isinstance(e, dict) and e.get("base_url") and e.get("model"):
                        chain.append({"base_url": str(e["base_url"]),
                                      "model": str(e["model"]),
                                      "api_key": e.get("api_key")})
        except ValueError:
            sys.stderr.write("REVIEW_LLM_ENDPOINTS 非法 JSON，忽略" + chr(10))
    if not chain:
        base_url = os.environ.get("REVIEW_LLM_BASE_URL", "")
        model = os.environ.get("REVIEW_LLM_MODEL", "")
        if base_url and model:
            chain.append({"base_url": base_url, "model": model,
                          "api_key": os.environ.get("REVIEW_LLM_API_KEY", "") or None})
    kept = []
    for i, e in enumerate(chain):
        err = _endpoint_error(e["base_url"])
        if err:
            sys.stderr.write("端点 %d 白名单拒绝剔除: %s" % (i, err) + chr(10))
            continue
        kept.append(e)
    return kept


def _mask(base_url: str) -> str:
    return re.sub(r"https://([^/@]+)@", "https://***@", base_url)[:60]


def _openai_fallback(system: str, user: str, args: dict | None,
                     on_tokens: "Callable[[int], None] | None") -> tuple[str | None, dict]:
    """端点链依次尝试；每端点失败 stderr 记录降级原因，全部失败如实降级。

    熔断语义不变（_openai_complete 内自检自记）；链级只在全灭时返回
    末端点错误并标 degraded=true。
    """
    chain = _endpoint_chain()
    if not chain:
        return None, {"provider": "openai", "error": "未配置任何端点"}
    last = None
    for i, e in enumerate(chain):
        text, meta = _openai_complete(system, user, args, on_tokens,
                                      base_url=e["base_url"], model=e["model"],
                                      api_key=e.get("api_key"))
        if text is not None:
            if i > 0:
                sys.stderr.write("LLM 端点降级命中备选 %d（%s）" % (i, _mask(e["base_url"])) + chr(10))
            return text, dict(meta, endpoint_used=i)
        last = {"provider": "openai", "error": meta.get("error"),
                "endpoint_used": i}
        if i + 1 < len(chain):
            sys.stderr.write("LLM 端点 %d（%s）失败降级: %s" % (
                i, _mask(e["base_url"]), str(meta.get("error"))[:80]) + chr(10))
    return None, dict(last, degraded=True)

# ---- M2 循环边界三件套（批次一 M2，round-233）----
# 熔断器：进程内跨调用连续失败计数；阈值后快失败，冷却到期自动复位。
CIRCUIT_THRESHOLD = 3
CIRCUIT_COOLDOWN_SECONDS = 300
_CIRCUIT = {"fails": 0, "opened_at": 0.0}


def _circuit_check() -> str | None:
    """熔断开启期间快失败；返回错误文案或 None（放行）。"""
    if _CIRCUIT["fails"] < CIRCUIT_THRESHOLD:
        return None
    left = CIRCUIT_COOLDOWN_SECONDS - (time.monotonic() - _CIRCUIT["opened_at"])
    if left <= 0:
        _CIRCUIT["fails"] = 0
        return None
    return "熔断开启（连续 %d 次失败），冷却剩 %.0fs" % (
        _CIRCUIT["fails"], left)


def _circuit_record_failure() -> None:
    _CIRCUIT["fails"] += 1
    if _CIRCUIT["fails"] == CIRCUIT_THRESHOLD:
        _CIRCUIT["opened_at"] = time.monotonic()
        sys.stderr.write(
            "LLM 熔断开启：连续 %d 次失败，冷却 %ds" % (
                _CIRCUIT["fails"], CIRCUIT_COOLDOWN_SECONDS) + chr(10))


def _circuit_record_success() -> None:
    if _CIRCUIT["fails"]:
        _CIRCUIT["fails"] = 0


def trim_tool_result(text: str, max_chars: int = 20000,
                     max_lines: int = 500) -> tuple[str, bool, int, int]:
    """工具结果回填裁剪（M2 统一助手）：双阈值保头部，返回 (头, 是否裁剪, 总字符, 总行数)。

    纯函数不写文件；外置落盘由调用方（materials._truncate_for_history 等）负责。
    """
    if not text:
        return text, False, 0, 0
    lines = text.splitlines()
    total_lines = len(lines)
    total_chars = len(text)
    over_chars = total_chars > max_chars
    over_lines = total_lines > max_lines
    if not (over_chars or over_lines):
        return text, False, total_chars, total_lines
    kept = text[:max_chars] if over_chars else text
    if over_lines:
        kept = "\n".join(kept.splitlines()[:max_lines])
    return kept, True, total_chars, total_lines


# ---- M3 结构化输出回填重试（批次一 M3，round-233）----
def _extract_json(text: str | None) -> tuple[object | None, str | None]:
    """宽松 JSON 提取：剥代码围栏后解析；返回 (obj, None) 或 (None, 原因)。"""
    if not text or not str(text).strip():
        return None, "空响应"
    s = str(text).strip()
    if s.startswith("```"):
        first_nl = s.find(chr(10))
        if first_nl != -1:
            s = s[first_nl + 1:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    try:
        return json.loads(s), None
    except ValueError as exc:
        return None, "非 JSON 响应: %s" % str(exc)[:120]


def complete_json(system: str, user: str, base_dir: str | None = None,
                  args: dict | None = None,
                  on_tokens: "Callable[[int], None] | None" = None,
                  validate: "Callable[[object], bool] | None" = None,
                  repair_rounds: int = 1) -> tuple[object | None, dict]:
    """complete + JSON 提取/校验 + 失败回填重试（M3）。

    返回 (obj, meta)；失败时 obj=None，meta["unparsed"]= 原因（如实计数，
    不冒充成功）。HostLLMPending 原样上抛（WAIT_HOST_LLM 流程不变）。
    D-053 门禁语义不变：全空 [] 响应属有效 JSON，原样返回——执行质量问题
    由 review-quality-gate 判定，不在此层掩饰。
    """
    text, meta = complete(system, user, base_dir=base_dir, args=args,
                          on_tokens=on_tokens)
    if text is None:
        return None, meta
    obj, err = _extract_json(text)
    if validate is not None and obj is not None and not validate(obj):
        err = "校验未通过（schema/要素）"
    if err is None:
        return obj, meta
    for _ in range(max(int(repair_rounds), 0)):
        user2 = user + "\n\n[系统] 上次响应未通过校验：%s；请修正后重新输出完整 JSON，不要解释。" % err
        text2, meta2 = complete(system, user2, base_dir=base_dir, args=args,
                                on_tokens=on_tokens)
        obj, err = _extract_json(text2)
        if validate is not None and obj is not None and not validate(obj):
            err = "校验未通过（schema/要素）"
        if err is None:
            meta.update({"repaired": True})
            return obj, meta
    return None, dict(meta, unparsed=err)
