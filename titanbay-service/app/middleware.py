"""
Custom middleware for production observability and performance.

Provides:
- **Request ID injection**: Every request/response carries a unique trace ID
  (``X-Request-ID`` header) for distributed tracing and log correlation.
- **Request timing**: Logs wall-clock duration of every request, enabling
  latency monitoring without an external APM agent.

These are critical for operating at scale — without a request ID, correlating
a client-reported error to a specific server log entry is near-impossible when
serving millions of concurrent requests across many container replicas.
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Header name used for request tracing across services.
# If the client/gateway already supplies one, we honour it; otherwise we generate.
REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Injects a unique request ID into every request/response cycle.

    Behaviour:
    - If the incoming request already has an ``X-Request-ID`` header (e.g. set
      by an API gateway or load balancer), that value is reused for end-to-end
      tracing.
    - Otherwise a new UUID4 is generated.
    - The ID is attached to ``request.state.request_id`` so downstream handlers
      and services can include it in log messages.
    - The ID is echoed back in the response ``X-Request-ID`` header so the
      caller can correlate the response with their logs.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Honour existing request ID from upstream gateway, or generate new one
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """
    Logs the wall-clock duration of every HTTP request.

    The ``X-Process-Time`` header is added to every response so that clients
    (and load-balancer health checks) can observe per-request latency without
    needing server-side dashboards.

    At scale (millions of global users), this data feeds into percentile
    latency metrics (p50, p95, p99) that drive auto-scaling decisions.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Process-Time"] = f"{elapsed_ms:.2f}ms"

        # Log at DEBUG for high-throughput endpoints, INFO for slow requests
        if elapsed_ms > 500:
            logger.warning(
                "%s %s completed in %.2fms (SLOW)",
                request.method,
                request.url.path,
                elapsed_ms,
            )
        else:
            logger.debug(
                "%s %s completed in %.2fms",
                request.method,
                request.url.path,
                elapsed_ms,
            )

        return response
