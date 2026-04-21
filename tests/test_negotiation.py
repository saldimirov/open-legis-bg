import pytest

from open_legis.api.negotiation import Format, pick_format


@pytest.mark.parametrize("accept,override,expected", [
    ("application/json", None, Format.JSON),
    ("application/akn+xml", None, Format.AKN),
    ("text/turtle", None, Format.TURTLE),
    ("*/*", None, Format.JSON),
    ("", None, Format.JSON),
    ("application/akn+xml, application/json;q=0.9", None, Format.AKN),
    ("text/turtle;q=0.5, application/json;q=0.8", None, Format.JSON),
    ("application/json", "akn", Format.AKN),
    ("application/json", "ttl", Format.TURTLE),
    ("application/json", "json", Format.JSON),
])
def test_pick_format(accept, override, expected):
    assert pick_format(accept=accept, override=override) == expected


def test_bad_override_rejected():
    with pytest.raises(ValueError):
        pick_format(accept="application/json", override="xml-doc")
