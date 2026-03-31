import time

from fastapi import Request, Response
from starlette.concurrency import iterate_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from testbench_ai_service.log import logger


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: callable) -> Response:
        start_time = time.time()

        # Log request and request body
        logger.debug(
            f"Request: {request.method} {request.url} from {request.client.host}:{request.client.port}"
        )
        if request.method in ("POST", "PUT", "PATCH"):
            body_bytes = await request.body()
            body_text = body_bytes.decode("utf-8", errors="replace") if body_bytes else ""
            # TODO: sanitize body_text to remove sensitive info
            logger.debug(f"Request Body: {body_text}")

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
