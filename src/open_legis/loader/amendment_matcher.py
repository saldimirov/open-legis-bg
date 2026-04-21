"""Match ZID works to their target base laws and populate the amendment table."""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.model import schema as m

# ── Title prefix patterns ─────────────────────────────────────────────────────

_ZID_PREFIX_RE = re.compile(
    r"^(?:"
    r"Закон за изменение и допълнение на\s+"
    r"|Закон за допълнение и изменение на\s+"
    r"|Закон за изменение на\s+"
    r"|Закон за допълнение на\s+"
    r"|Закон за отмяна на\s+"
    r"|Поправка (?:на допусната[\w\s,]+(?:в|на)\s+|в\s+)"
    r")",
    re.IGNORECASE,
)

# Split multiple targets: ", Закона/Кодекса/..." or " и Закона/..."
_MULTI_TARGET_RE = re.compile(
    r"[,\s]+и\s+(?=(?:Закона|Кодекса|Наредбата|Правилника|Конституцията))"
    r"|,\s+(?=(?:Закона|Кодекса|Наредбата|Правилника|Конституцията))"
)

# Remove trailing DV parentheticals: "(ДВ, бр. 100 от 2025 г.)"
_DV_REF_RE = re.compile(r"\s*\(ДВ[^)]*\)\s*$")

# ── Genitive → nominative normalisation ──────────────────────────────────────

# Simple noun forms (definite article stripped)
_NOUN_GENITIVE: dict[str, str] = {
    "Закона": "Закон",
    "Кодекса": "Кодекс",
    "Правилника": "Правилник",
    "Наредбата": "Наредба",
    "Конституцията": "Конституция",
    "Кодекса": "Кодекс",
    "Тарифата": "Тарифа",
}

# Adjectives in definite masculine genitive → indefinite nominative
# "Наказателния" → "Наказателен", "Семейния" → "Семеен", etc.
_ADJ_GENITIVE: dict[str, str] = {
    "Наказателния": "Наказателен",
    "Наказателно-процесуалния": "Наказателно-процесуален",
    "Гражданския": "Граждански",
    "Гражданскопроцесуалния": "Гражданскопроцесуален",
    "Търговския": "Търговски",
    "Семейния": "Семеен",
    "Изборния": "Изборен",
    "Данъчно-осигурителния": "Данъчно-осигурителен",
    "Административния": "Административен",
    "Административнопроцесуалния": "Административнопроцесуален",
    "Устройствения": "Устройствен",
}


def _normalise(name: str) -> str:
    for gen, nom in _ADJ_GENITIVE.items():
        name = name.replace(gen, nom)
    for gen, nom in _NOUN_GENITIVE.items():
        name = re.sub(rf"\b{gen}\b", nom, name)
    return name.strip()


# ── Extraction ────────────────────────────────────────────────────────────────

def extract_targets(title: str) -> list[str]:
    """Return normalised target law names extracted from a ZID/Поправка title."""
    m = _ZID_PREFIX_RE.match(title)
    if not m:
        return []
    remainder = title[m.end():]
    remainder = _DV_REF_RE.sub("", remainder).strip()
    parts = _MULTI_TARGET_RE.split(remainder)
    return [_normalise(p.strip()) for p in parts if p.strip()]


# ── Matching ──────────────────────────────────────────────────────────────────

def _jaccard(a: str, b: str) -> float:
    wa = set(a.lower().split())  # split() already collapses whitespace
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


@dataclass
class MatchResult:
    zid: m.Work
    target: m.Work
    score: float
    extracted: str


_ZID_TITLE_PATTERN = re.compile(
    r"^(Закон\s+за\s+изменение|Закон\s+за\s+допълнение"
    r"|Наредба\s+за\s+изменение|Наредба\s+за\s+допълнение"
    r"|Поправка\s)",
    re.IGNORECASE,
)


def match_all(session: Session, min_score: float = 0.45) -> list[MatchResult]:
    """Return best matches for all ZID works against base-law works."""
    zids = session.scalars(
        select(m.Work).where(m.Work.act_type == m.ActType.ZID)
    ).all()

    candidates = [
        w for w in session.scalars(
            select(m.Work).where(
                m.Work.act_type.in_([
                    m.ActType.ZAKON, m.ActType.KODEKS, m.ActType.KONSTITUTSIYA,
                    m.ActType.NAREDBA, m.ActType.PRAVILNIK, m.ActType.BYUDJET,
                ])
            )
        ).all()
        if not _ZID_TITLE_PATTERN.match(w.title)
    ]

    results: list[MatchResult] = []
    for zid in zids:
        for extracted in extract_targets(zid.title):
            best_score = 0.0
            best_target = None
            for cand in candidates:
                score = _jaccard(extracted, cand.title)
                if score > best_score:
                    best_score = score
                    best_target = cand
            if best_target and best_score >= min_score:
                results.append(MatchResult(
                    zid=zid,
                    target=best_target,
                    score=best_score,
                    extracted=extracted,
                ))

    return sorted(results, key=lambda r: r.score, reverse=True)


# ── DB population ─────────────────────────────────────────────────────────────

def populate_amendments(session: Session, matches: list[MatchResult]) -> int:
    """Write matches to the amendment table, skipping existing rows. Returns insert count."""
    existing = set(
        session.execute(
            select(m.Amendment.amending_work_id, m.Amendment.target_work_id)
        ).all()
    )

    count = 0
    for r in matches:
        key = (r.zid.id, r.target.id)
        if key in existing:
            continue
        import datetime as dt
        session.add(m.Amendment(
            amending_work_id=r.zid.id,
            target_work_id=r.target.id,
            operation=m.AmendmentOp.SUBSTITUTION,
            effective_date=r.zid.adoption_date or dt.date(r.zid.dv_year, 1, 1),
        ))
        existing.add(key)
        count += 1

    session.commit()
    return count
