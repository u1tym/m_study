from __future__ import annotations

import json
import logging
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("study.api")

_MAX_PAYLOAD_CHARS = 65536
_SKIP_PATH_PREFIXES = ("/docs", "/redoc", "/openapi.json")


def _truncate(s: str, max_len: int = _MAX_PAYLOAD_CHARS) -> str:
    if len(s) <= max_len:
        return s
    return f"{s[:max_len]}...<truncated {len(s) - max_len} chars>"


def _sanitize_for_log(obj: Any, max_str: int = 8192) -> Any:
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return _truncate(obj, max_str)
    if isinstance(obj, list):
        return [_sanitize_for_log(x, max_str) for x in obj[:500]]
    if isinstance(obj, dict):
        return {k: _sanitize_for_log(v, max_str) for k, v in list(obj.items())[:500]}
    return _truncate(str(obj), max_str)


def _decode_request_body(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return f"<binary {_truncate(repr(raw), 200)}>"
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _truncate(text)


def _decode_response_body(raw: bytes, content_type: str | None) -> Any:
    if not raw:
        return None
    ct = (content_type or "").lower()
    if "application/json" in ct or raw[:1] in (b"{", b"["):
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
    try:
        return _truncate(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return f"<binary len={len(raw)}>"


class APILoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        path = request.url.path
        if path.startswith(_SKIP_PATH_PREFIXES) or path == "/favicon.ico":
            return await call_next(request)

        raw_body = await request.body()

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": raw_body, "more_body": False}

        request._receive = receive  # type: ignore[attr-defined]
        request.state.log_request_body = _decode_request_body(raw_body)

        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

        body_chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            body_chunks.append(chunk)
        raw_resp = b"".join(body_chunks)

        skip_response_log = path.startswith("/docs") or "text/html" in (response.media_type or "")
        response_payload = None if skip_response_log else _decode_response_body(
            raw_resp, response.media_type
        )

        log_record = {
            "event": "api_access",
            "method": request.method,
            "path": path,
            "query": dict(request.query_params),
            "request_body": _sanitize_for_log(request.state.log_request_body),
            "status_code": response.status_code,
            "response_body": _sanitize_for_log(response_payload),
            "duration_ms": elapsed_ms,
        }
        logger.info(json.dumps(log_record, ensure_ascii=False, default=str))

        out_headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() != "content-length"
        }
        return Response(
            content=raw_resp,
            status_code=response.status_code,
            headers=out_headers,
            media_type=response.media_type,
            background=response.background,
        )
