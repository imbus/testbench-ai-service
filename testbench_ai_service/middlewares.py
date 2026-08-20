import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ClassVar
from urllib.parse import urlsplit

import requests
from fastapi import Request, Response
from starlette.concurrency import iterate_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from testbench_ai_service.log import VERBOSE, logger, truncate_payload
from testbench_ai_service.models.logging import DEFAULT_MAX_PAYLOAD_LENGTH
from testbench_ai_service.utils.log_sanitizer import (
    format_body,
    format_body_text,
    redact_secrets,
)

#: Content types whose bodies are safe to write into the log as text.
TEXTUAL_CONTENT_TYPES = ("json", "text/", "xml")


def _body_size(body: object) -> str:
    try:
        return f"{len(body)} bytes"  # type: ignore[arg-type]
    except TypeError:
        return "size unknown"


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
        cls._log_response_body(response)
        return response

    @classmethod
    def _log_request_body(cls, kwargs: dict) -> None:
        if not logger.isEnabledFor(VERBOSE):
            return

        json_body = kwargs.get("json")
        if json_body is not None:
            logger.log(
                VERBOSE, "Testbench request body: %s", format_body(redact_secrets(json_body))
            )
            return

        raw_body = kwargs.get("data")
        if raw_body is None:
            raw_body = kwargs.get("files")
        if raw_body is None:
            return

        logger.log(VERBOSE, "Testbench request body: <non-JSON body, %s>", _body_size(raw_body))

    @classmethod
    def _log_response_body(cls, response) -> None:
        if not logger.isEnabledFor(VERBOSE):
            return

        content_type = response.headers.get("Content-Type", "")
        text = response.text
        is_textual = isinstance(content_type, str) and any(
            marker in content_type.lower() for marker in TEXTUAL_CONTENT_TYPES
        )
        if not is_textual or not isinstance(text, str):
            logger.log(
                VERBOSE,
                "Testbench response body: <non-text body, %s>",
                _body_size(response.content),
            )
            return

        logger.log(VERBOSE, "Testbench response body: %s", format_body_text(text))


class LoggingMiddleware(BaseHTTPMiddleware):
    """Logs request/response metadata at DEBUG and, at VERBOSE, their payloads."""

    def __init__(self, app, max_payload_length: int = DEFAULT_MAX_PAYLOAD_LENGTH) -> None:
        super().__init__(app)
        self.max_payload_length = max_payload_length

    async def dispatch(
        self, request: Request, call_next: Callable[..., Awaitable[Response]]
    ) -> Response:
        start_time = time.time()

        # Reading and buffering payloads is only worth it when a sink is at VERBOSE.
        log_payloads = logger.isEnabledFor(VERBOSE)

        client_addr = (
            f"{request.client.host}:{request.client.port}" if request.client else "unknown"
        )
        logger.debug(f"Request: {request.method} {request.url} from {client_addr}")
        if log_payloads and request.method in ("POST", "PUT", "PATCH"):
            body_bytes = await request.body()
            body_text = body_bytes.decode("utf-8", errors="replace") if body_bytes else ""
            logger.log(
                VERBOSE,
                "Request Body: %s",
                truncate_payload(format_body_text(body_text), self.max_payload_length),
            )

        # Process request and get response
        response = await call_next(request)

        logger.debug(f"Response Status: {response.status_code}")

        # Paths to skip response body logging, e.g. docs, openapi
        skip_paths = ["/", request.app.docs_url, request.app.redoc_url, request.app.openapi_url]

        if log_payloads and request.url.path not in skip_paths:
            # Capture response body chunks from body_iterator and cache them
            if hasattr(response, "body_iterator"):
                response_body_chunks = [chunk async for chunk in response.body_iterator]
                response.body_iterator = iterate_in_threadpool(iter(response_body_chunks))
                response_body = b"".join(response_body_chunks).decode("utf-8", errors="replace")
            else:
                # For non-streaming responses fallback - may not apply often
                response_body = getattr(response, "body", b"").decode("utf-8", errors="replace")

            logger.log(
                VERBOSE,
                "Response Body: %s",
                truncate_payload(format_body_text(response_body), self.max_payload_length),
            )

        process_time = time.time() - start_time
        logger.debug(f"Processed in {process_time:.3f} seconds")

        return response
