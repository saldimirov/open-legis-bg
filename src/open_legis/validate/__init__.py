from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Issue:
    severity: Literal["error", "warn", "info"]
    code: str
    message: str
    path: str | None = None
    detail: str | None = None


@dataclass
class LayerResult:
    name: str
    issues: list[Issue] = field(default_factory=list)
    stats: dict[str, int | float] = field(default_factory=dict)
