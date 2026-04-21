from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from open_legis.settings import Settings

router = APIRouter(prefix="/dumps", tags=["dumps"])


class DumpItem(BaseModel):
    name: str
    size: int


class DumpList(BaseModel):
    items: list[DumpItem]


def _dumps_dir() -> Path:
    return Settings().dumps_dir


@router.get("/", response_model=DumpList)
def list_dumps() -> DumpList:
    d = _dumps_dir()
    if not d.exists():
        return DumpList(items=[])
    return DumpList(
        items=[
            DumpItem(name=f.name, size=f.stat().st_size)
            for f in sorted(d.iterdir())
            if f.is_file() and f.name != ".keep"
        ]
    )


@router.get("/{name}")
def get_dump(name: str) -> FileResponse:
    if "/" in name or ".." in name:
        raise HTTPException(status_code=400, detail="bad name")
    f = _dumps_dir() / name
    if not f.exists() or not f.is_file():
        raise HTTPException(status_code=404, detail="not found")
    media = (
        "application/gzip"
        if name.endswith(".gz")
        else "application/octet-stream"
    )
    return FileResponse(f, media_type=media, filename=name)
