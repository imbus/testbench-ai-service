import json
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ClassVar
from urllib.parse import urlsplit

import requests
from fastapi import Request, Response
from starlette.concurrency import iterate_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from testbench_ai_service.log import log_in_request, logger


class RequestScopeMiddleware:
    """Mark every record logged while serving an HTTP or websocket request (design D4).

    Records that carry no user are then ``request``-scoped and never reach the
    activity view, whoever is looking. Websocket connections are requests too;
    leaving them unmarked would let their records through as ``service``.

    Deliberately set without a reset: uvicorn logs an unhandled exception after
    the app returns, in the same per-request task, and that traceback belongs
    to the request, not to the service. Each request runs in its own task with
    its own context copy, so the value cannot leak into another request.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            log_in_request.set(True)
        await self.app(scope, receive, send)


class OutboundRequestLoggingMiddleware:
    """Log every HTTP request sent to configured Testbench servers."""

    _installed: ClassVar[bool] = False
    _testbench_server_urls: ClassVar[set[str]] = set()

    @classmethod
    def install(cls, testbench_server_url: str) -> None:
        cls._testbench_server_urls.add(testbench_server_url.rstrip("/"))
        if cls._installed:
            return

        original_request = requests.sessions.Session.request

        @wraps(original_request)
        def logged_request(session, method, url, *args, **kwargs):
            return cls._log_testbench_request(
                original_request, session, method, url, *args, **kwargs
            )

        requests.sessions.Session.request = logged_request
        cls._installed = True

    @classmethod
    def _log_testbench_request(cls, request, session, method, url, *args, **kwargs):
        url_text = str(url)
        if not any(
            url_text == server_url or url_text.startswith(f"{server_url}/")
            for server_url in cls._testbench_server_urls
        ):
            return request(session, method, url, *args, **kwargs)

        request_url = urlsplit(url_text)
        sanitized_url = f"{request_url.scheme}://{request_url.netloc}{request_url.path}"
        start_time = time.perf_counter()
        logger.debug("Testbench request: %s %s", method.upper(), sanitized_url)
        try:
            response = request(session, method, url, *args, **kwargs)
        except Exception:
            duration = time.perf_counter() - start_time
            logger.debug(
                "Testbench request failed: %s %s in %.3f seconds",
                method.upper(),
                sanitized_url,
                duration,
            )
            raise

        duration = time.perf_counter() - start_time
        logger.debug(
            "Testbench response: %s %s returned %s in %.3f seconds",
            method.upper(),
            sanitized_url,
            response.status_code,
            duration,
        )
        return response


_REDACTED = "<redacted>"
#: Bodies of these paths carry credentials as a whole and are never logged.
_NEVER_LOG_BODY = frozenset({"/admin/api/session"})
#: A JSON key containing any of these (case-insensitive) has its value masked.
_SENSITIVE_KEY_PARTS = ("password", "token", "api_key", "secret")


def _mask(value):
    if isinstance(value, dict):
        return {
            key: _REDACTED
            if any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS)
            else _mask(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask(item) for item in value]
    return value


def redact_body(path: str, text: str) -> str:
    """Make a request or response body safe to log."""
    if path in _NEVER_LOG_BODY:
        return _REDACTED
    try:
        data = json.loads(text)
    except ValueError:
        return text
    return json.dumps(_mask(data), ensure_ascii=False)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[..., Awaitable[Response]]
    ) -> Response:
        start_time = time.time()

        client_addr = (
            f"{request.client.host}:{request.client.port}" if request.client else "unknown"
        )
        logger.debug(f"Request: {request.method} {request.url} from {client_addr}")
        if request.method in ("POST", "PUT", "PATCH"):
            body_bytes = await request.body()
            body_text = body_bytes.decode("utf-8", errors="replace") if body_bytes else ""
            logger.debug(f"Request Body: {redact_body(request.url.path, body_text)}")

        # Process request and get response
        response = await call_next(request)

        logger.debug(f"Response Status: {response.status_code}")

        # Paths to skip response body logging, e.g. docs, openapi
        skip_paths = ["/", request.app.docs_url, request.app.redoc_url, request.app.openapi_url]

        if request.url.path not in skip_paths:
            # Capture response body chunks from body_iterator and cache them
            if hasattr(response, "body_iterator"):
                response_body_chunks = [chunk async for chunk in response.body_iterator]
                response.body_iterator = iterate_in_threadpool(iter(response_body_chunks))
                response_body = b"".join(response_body_chunks).decode("utf-8", errors="replace")
            else:
                # For non-streaming responses fallback - may not apply often
                response_body = getattr(response, "body", b"").decode("utf-8", errors="replace")

            logger.debug(f"Response Body: {redact_body(request.url.path, response_body)}")

        process_time = time.time() - start_time
        logger.debug(f"Processed in {process_time:.3f} seconds")

        return response
