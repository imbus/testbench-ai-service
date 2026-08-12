import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ClassVar
from urllib.parse import urlsplit

import requests
from fastapi import Request, Response
from starlette.concurrency import iterate_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from testbench_ai_service.log import logger
from testbench_ai_service.utils.log_sanitizer import (
    format_body,
    format_body_text,
    redact_secrets,
)


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
        cls._log_request_body(kwargs)
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

    @classmethod
    def _log_request_body(cls, kwargs: dict) -> None:
        json_body = kwargs.get("json")
        if json_body is not None:
            logger.debug("Testbench request body: %s", format_body(redact_secrets(json_body)))
            return

        raw_body = kwargs.get("data")
        if raw_body is None:
            raw_body = kwargs.get("files")
        if raw_body is None:
            return

        try:
            size = f"{len(raw_body)} bytes"
        except TypeError:
            size = "size unknown"
        logger.debug("Testbench request body: <non-JSON body, %s>", size)


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
            logger.debug("Request Body: %s", format_body_text(body_text))

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

            # TODO: sanitize response_body to remove sensitive info
            logger.debug(f"Response Body: {response_body}")

        process_time = time.time() - start_time
        logger.debug(f"Processed in {process_time:.3f} seconds")

        return response
