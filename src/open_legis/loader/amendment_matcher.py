"""Match ZID works to their target base laws and populate the amendment table.

Two strategies:
1. history_parse  — parse the (обн./изм.) publication history from the law's AKN
                    preface.  Gives exact broy+year references → very high precision.
2. title_match    — Jaccard word-overlap on ZID titles after genitive normalisation.
                    Falls back for laws without a parseable history.

history_parse runs first and is preferred.  title_match fills gaps.

Note: "Решение № X на Конституционния съд" in a history string is a Constitutional
Court decision (reshenie_ks), NOT the Constitution.  These are stored as unresolved
until we have reshenie_ks works in the corpus.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.model import schema as m

# ── Publication history parser ────────────────────────────────────────────────

# Matches a block of DV issue refs after "изм.," or "доп.," etc.:
#   бр. 11 и 45 от 2002 г., бр. 99 от 2003 г.
# We extract individual (broy_list, year) groups.
_HISTORY_SEGMENT_RE = re.compile(
    r"бр\.\s*([\d,\s]+(?:и\s*\d+)?)\s+от\s+(\d{4})\s*г\.",
    re.IGNORECASE,
)

# Detect a КС decision entry — must NOT be treated as a ZID amendment
_KS_DECISION_RE = re.compile(
    r"Решение\s+№\s*\d+\s+на\s+Конституционния\s+съд",
    re.IGNORECASE,
)

# Detect the "изм." block (vs. "обн." original publication)
_IZM_BLOCK_RE = re.compile(
    r"(?:изм\.|доп\.)[^;)]*",
    re.IGNORECASE,
)


def _broyes_from_segment(segment: str) -> list[int]:
    """Extract individual issue numbers from e.g. '11, 45 и 99'."""
    return [int(n) for n in re.findall(r"\d+", segment)]


def parse_history_refs(history_text: str) -> list[tuple[int, int]]:
    """Return (broy, year) pairs for amendment references in a law's history string.

    Ignores the original 'обн.' entry and Constitutional Court decisions.
    """
    refs: list[tuple[int, int]] = []

    # Split into semicolon-delimited clauses
    for clause in history_text.split(";"):
        clause = clause.strip()
        # Skip КС decisions
        if _KS_DECISION_RE.search(clause):
            continue
        # Skip the original publication clause (starts with обн.)
        if re.match(r"\(?обн\.", clause, re.IGNORECASE):
            continue
        # Extract all bр. X от Y г. groups in this clause
        for m in _HISTORY_SEGMENT_RE.finditer(clause):
            year = int(m.group(2))
            for broy in _broyes_from_segment(m.group(1)):
                refs.append((broy, year))

    return refs


def extract_history_from_expression(expr: m.Expression) -> str | None:
    """Return the raw publication history string from an AKN expression's preface."""
    try:
        from lxml import etree
        NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
        root = etree.fromstring(expr.akn_xml.encode())
        for p in root.findall(f".//{{{NS}}}preface/{{{NS}}}p"):
            text = (p.text or "").strip()
            if "обн." in text.lower() and "дв" in text.lower():
                return text
    except Exception:
        pass
    return None


# ── History-based matching ────────────────────────────────────────────────────

@dataclass
class MatchResult:
    zid: m.Work
    target: m.Work
    score: float          # 1.0 for history matches, Jaccard for title matches
    extracted: str        # extracted target name or "history:broy/year"
    source: str = "title" # "history" or "title"


def match_from_history(session: Session) -> list[MatchResult]:
    """For each ZID, confirm its title-extracted target using the target's history.

    Strategy: title matching gives us a candidate target; if that target's history
    includes a reference to the ZID's own DV issue, we have a double-confirmed match
    (score=1.0).  Without history confirmation the match stays as a title match.
    """
    base_types = [
        m.ActType.ZAKON, m.ActType.KODEKS, m.ActType.KONSTITUTSIYA,
        m.ActType.NAREDBA, m.ActType.PRAVILNIK, m.ActType.BYUDJET,
    ]

    # Build title→work index for base laws
    base_works = session.scalars(
        select(m.Work).where(m.Work.act_type.in_(base_types))
    ).all()
    base_by_id: dict = {w.id: w for w in base_works}

    # Build history index: work_id → set of (broy, year) refs
    history_refs: dict = {}
    for work in base_works:
        expr = session.scalars(
            select(m.Expression).where(
                m.Expression.work_id == work.id,
                m.Expression.is_latest.is_(True),
            )
        ).one_or_none()
        if not expr:
            continue
        history = extract_history_from_expression(expr)
        if history:
            refs = parse_history_refs(history)
            if refs:
                history_refs[work.id] = set(refs)

    # For each ZID: title-extract targets, then check history confirmation
    zids = session.scalars(
        select(m.Work).where(m.Work.act_type == m.ActType.ZID)
    ).all()

    # Pre-build title→works map for fast lookup
    from collections import defaultdict
    title_to_works: dict[str, list] = defaultdict(list)
    for w in base_works:
        title_to_works[w.title.lower()].append(w)

    results: list[MatchResult] = []
    for zid in zids:
        zid_key = (zid.dv_broy, zid.dv_year)
        for extracted in _extract_targets(zid.title):
            # Find best title-matching base law
            best_score = 0.0
            best_target = None
            for cand in base_works:
                score = _jaccard(extracted, cand.title)
                if score > best_score:
                    best_score = score
                    best_target = cand
            if best_target is None or best_score < 0.45:
                continue

            # Check if target's history confirms this ZID's DV issue
            confirmed = zid_key in history_refs.get(best_target.id, set())
            if confirmed:
                results.append(MatchResult(
                    zid=zid,
                    target=best_target,
                    score=1.0,
                    extracted=f"history+title:{extracted[:50]}",
                    source="history",
                ))

    return results


# ── Title-based matching (fallback) ──────────────────────────────────────────

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

_MULTI_TARGET_RE = re.compile(
    r"[,\s]+и\s+(?=(?:Закона|Кодекса|Наредбата|Правилника|Конституцията))"
    r"|,\s+(?=(?:Закона|Кодекса|Наредбата|Правилника|Конституцията))"
)

_DV_REF_RE = re.compile(r"\s*\(ДВ[^)]*\)\s*$")

_NOUN_GENITIVE: dict[str, str] = {
    "Закона": "Закон",
    "Кодекса": "Кодекс",
    "Правилника": "Правилник",
    "Наредбата": "Наредба",
    "Конституцията": "Конституция",
    "Тарифата": "Тарифа",
}

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


def _extract_targets(title: str) -> list[str]:
    match = _ZID_PREFIX_RE.match(title)
    if not match:
        return []
    remainder = title[match.end():]
    remainder = _DV_REF_RE.sub("", remainder).strip()
    parts = _MULTI_TARGET_RE.split(remainder)
    return [_normalise(p.strip()) for p in parts if p.strip()]


def _jaccard(a: str, b: str) -> float:
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


_ZID_TITLE_PATTERN = re.compile(
    r"^(Закон\s+за\s+изменение|Закон\s+за\s+допълнение"
    r"|Наредба\s+за\s+изменение|Наредба\s+за\s+допълнение"
    r"|Поправка\s)",
    re.IGNORECASE,
)


def match_all(session: Session, min_score: float = 0.45) -> list[MatchResult]:
    """Return best matches combining history-parse (score=1.0) and title Jaccard."""
    history_results = match_from_history(session)

    # Build set of (zid_id, target_id) already covered by history
    history_pairs = {(r.zid.id, r.target.id) for r in history_results}

    # Title matching for ZIDs not already covered
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

    title_results: list[MatchResult] = []
    for zid in zids:
        for extracted in _extract_targets(zid.title):
            best_score = 0.0
            best_target = None
            for cand in candidates:
                score = _jaccard(extracted, cand.title)
                if score > best_score:
                    best_score = score
                    best_target = cand
            if best_target and best_score >= min_score:
                if (zid.id, best_target.id) not in history_pairs:
                    title_results.append(MatchResult(
                        zid=zid,
                        target=best_target,
                        score=best_score,
                        extracted=extracted,
                        source="title",
                    ))

    all_results = history_results + title_results
    return sorted(all_results, key=lambda r: r.score, reverse=True)


# ── DB population ─────────────────────────────────────────────────────────────

def populate_amendments(session: Session, matches: list[MatchResult]) -> int:
    """Write element-level amendment rows, skipping existing ones.

    For each match, parse the ZID's AKN body to extract per-§ change
    instructions (target_e_id, operation). If parsing fails or yields nothing,
    fall back to one summary row per (ZID, target) pair with no e_id.
    """
    from open_legis.loader.zid_parser import parse_zid_expression

    # Existing rows keyed by (amending_work_id, target_work_id, target_e_id or "")
    existing: set[tuple] = set(
        (row[0], row[1], row[2] or "")
        for row in session.execute(
            select(
                m.Amendment.amending_work_id,
                m.Amendment.target_work_id,
                m.Amendment.target_e_id,
            )
        ).all()
    )

    count = 0

    for r in matches:
        effective = r.zid.adoption_date or dt.date(r.zid.dv_year, 1, 1)

        # Load the ZID's latest expression for body parsing
        expr = session.scalars(
            select(m.Expression).where(
                m.Expression.work_id == r.zid.id,
                m.Expression.is_latest.is_(True),
            )
        ).one_or_none()

        instructions = parse_zid_expression(expr.akn_xml) if expr else []

        # Filter instructions to this target (for omnibus: match by law name)
        target_instructions = _filter_instructions(instructions, r)

        if target_instructions:
            for inst in target_instructions:
                key = (r.zid.id, r.target.id, inst.target_e_id or "")
                if key in existing:
                    continue
                session.add(m.Amendment(
                    amending_work_id=r.zid.id,
                    target_work_id=r.target.id,
                    target_e_id=inst.target_e_id,
                    operation=inst.operation,
                    effective_date=effective,
                    notes=inst.raw_text[:500] if inst.raw_text else None,
                ))
                existing.add(key)
                count += 1
        else:
            # Fallback: one summary row with no e_id
            key = (r.zid.id, r.target.id, "")
            if key not in existing:
                session.add(m.Amendment(
                    amending_work_id=r.zid.id,
                    target_work_id=r.target.id,
                    operation=m.AmendmentOp.SUBSTITUTION,
                    effective_date=effective,
                ))
                existing.add(key)
                count += 1

    session.commit()
    return count


def _filter_instructions(instructions, r: "MatchResult"):
    """Return instructions relevant to this match target.

    For single-target ZIDs: all instructions with no target_law.
    For omnibus ZIDs: instructions whose target_law matches r.target.title.
    """
    from open_legis.loader.zid_parser import ChangeInstruction

    no_law = [i for i in instructions if i.target_law is None]
    with_law = [i for i in instructions if i.target_law is not None]

    if not with_law:
        # Single-target ZID — all instructions belong to this target
        return no_law

    # Omnibus: find instructions for this specific target law
    target_title = r.target.title.lower()
    matched = [
        i for i in with_law
        if _jaccard(i.target_law.lower(), target_title) >= 0.35
    ]
    return matched if matched else no_law
