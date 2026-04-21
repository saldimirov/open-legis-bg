from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["meta"])

_ROBOTS = """\
User-agent: *
Allow: /eli/
Allow: /v1/works
Allow: /v1/search
Allow: /docs
Allow: /redoc
Disallow: /v1/dumps/
Disallow: /ui/
"""



@router.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots() -> str:
    return _ROBOTS


@router.get(
    "/health",
    summary="Health check",
    description="Returns `{\"status\": \"ok\"}` when the service is up. No database query.",
    responses={200: {"content": {"application/json": {"example": {"status": "ok"}}}}},
)
def health() -> dict[str, str]:
    return {"status": "ok"}
