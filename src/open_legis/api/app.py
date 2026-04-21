from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from open_legis.api.middleware import ETagMiddleware, SecurityHeadersMiddleware
from open_legis.api.rate_limit import limiter
from open_legis.api.routes_aliases import router as aliases_router
from open_legis.api.routes_discovery import router as discovery_router
from open_legis.api.routes_dumps import router as dumps_router
from open_legis.api.routes_eli import router as eli_router
from open_legis.api.routes_meta import router as meta_router
from open_legis.api.routes_ui import router as ui_router
from open_legis.mcp.server import mcp

_DESCRIPTION = "Free, open, machine-readable database of Bulgarian legislation sourced from the State Gazette (dv.parliament.bg)."

_TAGS = [
    {
        "name": "eli",
        "description": "ELI-compliant endpoints for resolving works, expressions, and elements.",
    },
    {
        "name": "discovery",
        "description": "List, search, and explore relationships between legislative acts.",
    },
    {
        "name": "aliases",
        "description": "Redirect helpers — look up an act by DV issue reference or external identifier.",
    },
    {
        "name": "dumps",
        "description": "Pre-built data dumps for bulk download.",
    },
    {
        "name": "meta",
        "description": "Health and operational endpoints.",
    },
]


def create_app() -> FastAPI:
    from open_legis.api.deps import reset_for_tests
    from open_legis.settings import Settings

    reset_for_tests()
    settings = Settings()

    servers = [{"url": settings.public_url, "description": "Production"}] if settings.public_url else []

    app = FastAPI(
        title="open-legis",
        description=_DESCRIPTION,
        version="0.1.0",
        openapi_tags=_TAGS,
        servers=servers or None,
        license_info={"name": "CC0 1.0", "url": "https://creativecommons.org/publicdomain/zero/1.0/"},
        contact={"name": "open-legis", "url": "https://github.com/saldimirov/open-legis"},
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(ETagMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(ui_router)
    app.include_router(meta_router)
    app.include_router(eli_router)
    app.include_router(discovery_router, prefix="/v1")
    app.include_router(aliases_router, prefix="/v1")
    app.include_router(dumps_router, prefix="/v1")
    app.mount("/mcp", mcp.streamable_http_app())
    return app
