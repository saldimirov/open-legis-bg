from pathlib import Path

import pytest

from open_legis.loader.akn_parser import parse_akn_file
from open_legis.loader.validators import ValidationError, validate_parsed


def test_validate_accepts_minimal(tmp_path):
    parsed = parse_akn_file(Path("tests/data/minimal_act.xml"))
    validate_parsed(parsed, source_path=Path("tests/data/minimal_act.xml"))


def test_validate_rejects_eid_path_mismatch():
    parsed = parse_akn_file(Path("tests/data/minimal_act.xml"))
    parsed.elements[0].e_id = "wrong_id"
    parsed.elements[2].parent_e_id = "wrong_parent"
    with pytest.raises(ValidationError, match="parent_e_id"):
        validate_parsed(parsed, source_path=Path("tests/data/minimal_act.xml"))


def test_validate_rejects_eli_path_mismatch(tmp_path):
    parsed = parse_akn_file(Path("tests/data/minimal_act.xml"))
    src = tmp_path / "akn" / "zakon" / "1950" / "zzd" / "expressions" / "2024-01-01.bul.xml"
    src.parent.mkdir(parents=True)
    src.write_text("x")
    with pytest.raises(ValidationError, match="ELI"):
        validate_parsed(parsed, source_path=src)
