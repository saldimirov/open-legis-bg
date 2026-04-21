import enum
from typing import Optional


class Format(str, enum.Enum):
    JSON = "json"
    AKN = "akn"
    TURTLE = "ttl"


_MEDIA_TYPE_TO_FORMAT = {
    "application/json": Format.JSON,
    "application/akn+xml": Format.AKN,
    "text/turtle": Format.TURTLE,
}

_OVERRIDE_TO_FORMAT = {
    "json": Format.JSON,
    "akn": Format.AKN,
    "ttl": Format.TURTLE,
    "turtle": Format.TURTLE,
}


def pick_format(accept: str = "", override: Optional[str] = None) -> Format:
    if override is not None:
        if override not in _OVERRIDE_TO_FORMAT:
            raise ValueError(f"Unknown format override {override!r}")
        return _OVERRIDE_TO_FORMAT[override]

    if not accept or "*/*" in accept:
        return Format.JSON

    parsed: list[tuple[Format, float]] = []
    for token in accept.split(","):
        mt, _, params = token.strip().partition(";")
        mt = mt.strip().lower()
        q = 1.0
        for p in params.split(";"):
            if p.strip().startswith("q="):
                try:
                    q = float(p.split("=", 1)[1])
                except ValueError:
                    pass
        if mt in _MEDIA_TYPE_TO_FORMAT:
            parsed.append((_MEDIA_TYPE_TO_FORMAT[mt], q))

    if not parsed:
        return Format.JSON
    parsed.sort(key=lambda x: x[1], reverse=True)
    return parsed[0][0]


def media_type(fmt: Format) -> str:
    return {
        Format.JSON: "application/json",
        Format.AKN: "application/akn+xml",
        Format.TURTLE: "text/turtle",
    }[fmt]
