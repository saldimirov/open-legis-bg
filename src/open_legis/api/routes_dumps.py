from pathlib import Path

from fastapi import APIRouter, HTTPException, Path as FPath, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from open_legis.api.errors import COMMON_ERRORS
from open_legis.api.rate_limit import limiter
from open_legis.settings import Settings

router = APIRouter(prefix="/dumps", tags=["dumps"])


class DumpItem(BaseModel):
    name: str = Field(..., description="File name of the dump.")
    size: int = Field(..., description="File size in bytes.")


class DumpList(BaseModel):
    items: list[DumpItem]


def _dumps_dir() -> Path:
    return Settings().dumps_dir


@router.get("/", response_model=DumpList, summary="List available dumps", description="Returns names and sizes of all pre-built data dumps available for download.")
def list_dumps() -> DumpList:
    d = _dumps_dir()
    if not d.exists():
        return DumpList(items=[])
    return DumpList(items=[DumpItem(name=f.name, size=f.stat().st_size) for f in sorted(d.iterdir()) if f.is_file() and f.name != ".keep"])


@router.get(
    "/{name}",
    summary="Download a dump",
    description="Streams a dump file by name. `.gz` files are served as `application/gzip`; all others as `application/octet-stream`.",
    responses={200: {"description": "The dump file."}, **COMMON_ERRORS},
)
@limiter.limit("10/day")
def get_dump(
    request: Request,
    name: str = FPath(..., description="File name as returned by `GET /v1/dumps/`."),
) -> FileResponse:
    if "/" in name or ".." in name:
        raise HTTPException(status_code=400, detail="bad name")
    f = _dumps_dir() / name
    if not f.exists() or not f.is_file():
        raise HTTPException(status_code=404, detail="not found")
    media = "application/gzip" if name.endswith(".gz") else "application/octet-stream"
    return FileResponse(f, media_type=media, filename=name)
