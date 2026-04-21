import hashlib

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-XSS-Protection": "1; mode=block",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


class ETagMiddleware(BaseHTTPMiddleware):
    """Adds ETag header to GET 200 responses and returns 304 on match."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response = await call_next(request)

        # Only ETag GET responses with a fixed body (skip streaming dumps)
        if (
            request.method != "GET"
            or response.status_code != 200
            or request.url.path.startswith("/v1/dumps/")
            or not hasattr(response, "body_iterator")
        ):
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        etag = f'"{hashlib.sha256(body).hexdigest()[:24]}"'

        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag, "Cache-Control": response.headers.get("Cache-Control", "")})

        headers = dict(response.headers)
        headers["ETag"] = etag
        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )
