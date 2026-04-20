from pathlib import Path

from open_legis.loader.akn_parser import ParsedAkn
from open_legis.loader.uri import parse_eli


class ValidationError(Exception):
    pass


def validate_parsed(parsed: ParsedAkn, source_path: Path) -> None:
    _validate_eli_matches_path(parsed, source_path)
    _validate_unique_eids(parsed)
    _validate_parent_references_exist(parsed)


def _validate_eli_matches_path(parsed: ParsedAkn, source_path: Path) -> None:
    u = parse_eli(parsed.work.eli_uri)
    path_parts = source_path.resolve().parts
    # fixtures/akn/<type>/<year>/<slug>/expressions/<date>.<lang>.xml
    try:
        i = path_parts.index("akn")
    except ValueError:
        return  # ad-hoc test path, skip
    expected = path_parts[i + 1 : i + 4]
    if (expected[0], int(expected[1]), expected[2]) != (u.act_type, u.year, u.slug):
        raise ValidationError(
            f"ELI {parsed.work.eli_uri!r} does not match fixture path {source_path}"
        )


def _validate_unique_eids(parsed: ParsedAkn) -> None:
    seen: set[str] = set()
    for el in parsed.elements:
        if el.e_id in seen:
            raise ValidationError(f"Duplicate eId {el.e_id!r}")
        seen.add(el.e_id)


def _validate_parent_references_exist(parsed: ParsedAkn) -> None:
    all_ids = {el.e_id for el in parsed.elements}
    for el in parsed.elements:
        if el.parent_e_id and el.parent_e_id not in all_ids:
            raise ValidationError(
                f"Element {el.e_id!r} has parent_e_id {el.parent_e_id!r} "
                f"which does not exist"
            )
