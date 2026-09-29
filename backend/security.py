"""
IntelliClaim AI - API protection

- Per-client rate limits (slowapi) on endpoints that write data or call an
  AI provider. Limits are keyed by endpoint, so varying a path parameter
  does not open a fresh bucket.
- An optional admin key: when ADMIN_API_KEY is set, destructive and costly
  endpoints require it in the X-Admin-Key header.
"""

import hmac
import logging
from typing import Annotated

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from config import settings

logger = logging.getLogger("intelliclaim.security")

# Per-client limits
UPLOAD_LIMIT = "10/minute"
WRITE_LIMIT = "30/minute"
AI_LIMIT = "10/minute"
SEARCH_LIMIT = "20/minute"
BULK_LIMIT = "3/minute"
PROVIDER_CHECK_LIMIT = "5/minute"


def client_ip(request: Request) -> str:
    """The caller's address, accounting for TRUSTED_PROXY_COUNT reverse proxies.

    Each proxy appends the address it received the request from to
    X-Forwarded-For, so with N trusted proxies the client is the Nth entry
    from the right; anything further left was supplied by the client itself.
    """
    hops = settings.TRUSTED_PROXY_COUNT
    if hops > 0:
        forwarded = request.headers.get("x-forwarded-for", "")
        addresses = [part.strip() for part in forwarded.split(",") if part.strip()]
        if addresses:
            return addresses[max(len(addresses) - hops, 0)]
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=client_ip, key_style="endpoint", enabled=settings.RATE_LIMIT_ENABLED)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 in the API's {"detail": ...} shape, with Retry-After."""
    retry_after = exc.limit.limit.get_expiry() if exc.limit is not None else 60
    logger.warning("Rate limit reached by %s on %s (%s)", client_ip(request), request.url.path, exc.detail)
    return JSONResponse(
        status_code=429,
        content={"detail": f"Too many requests ({exc.detail}). Please try again later."},
        headers={"Retry-After": str(retry_after)},
    )


async def require_admin_key(x_admin_key: Annotated[str | None, Header()] = None) -> None:
    """Require a matching X-Admin-Key header when ADMIN_API_KEY is configured."""
    expected = settings.ADMIN_API_KEY
    if not expected:
        return
    if x_admin_key is None or not hmac.compare_digest(x_admin_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Admin-Key header")
