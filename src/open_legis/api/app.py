from fastapi import FastAPI

from open_legis.api.routes_aliases import router as aliases_router
from open_legis.api.routes_discovery import router as discovery_router
from open_legis.api.routes_eli import router as eli_router
from open_legis.api.routes_meta import router as meta_router


def create_app() -> FastAPI:
    from open_legis.api.deps import reset_for_tests

    reset_for_tests()

    app = FastAPI(
        title="open-legis",
        description="An open machine-readable database of Bulgarian legislation.",
        version="0.1.0",
    )
    app.include_router(meta_router)
    app.include_router(eli_router)
    app.include_router(discovery_router)
    app.include_router(aliases_router)
    return app
