import datetime as dt
from dataclasses import dataclass
from typing import Literal, Optional, Union

_VALID_TYPES = {
    "konstitutsiya", "kodeks", "zakon", "zid", "byudjet", "naredba", "pravilnik",
    "postanovlenie", "ukaz", "reshenie-ks", "reshenie-ns",
}


@dataclass(frozen=True)
class EliUri:
    act_type: str
    year: int
    slug: str
    expression_date: Optional[Union[dt.date, Literal["latest"]]] = None
    language: Optional[str] = None
    element_path: Optional[str] = None

    def e_id(self) -> Optional[str]:
        if self.element_path is None:
            return None
        return self.element_path.replace("/", "__")


def parse_eli(uri: str) -> EliUri:
    if not uri.startswith("/eli/bg/"):
        raise ValueError(f"Not a Bulgarian ELI URI: {uri!r}")
    parts = uri[len("/eli/bg/"):].split("/")
    if len(parts) < 3:
        raise ValueError(f"Too short: {uri!r}")

    act_type, year_s, slug, *rest = parts
    if act_type not in _VALID_TYPES:
        raise ValueError(f"Unknown act_type {act_type!r}")
    try:
        year = int(year_s)
    except ValueError as e:
        raise ValueError(f"Non-numeric year {year_s!r}") from e
    if year < 1800 or year > 2200:
        raise ValueError(f"Year out of range: {year}")

    expression_date: Optional[Union[dt.date, Literal["latest"]]] = None
    language: Optional[str] = None
    element_path: Optional[str] = None

    if rest:
        if len(rest) < 2:
            raise ValueError(f"Expression URI needs date + language: {uri!r}")
        date_s, language, *elem = rest
        if date_s == "latest":
            expression_date = "latest"
        else:
            try:
                expression_date = dt.date.fromisoformat(date_s)
            except ValueError as e:
                raise ValueError(f"Bad date {date_s!r}") from e
        if not language.isascii() or len(language) != 3:
            raise ValueError(f"Bad language code {language!r}")
        if elem:
            element_path = "/".join(elem)

    return EliUri(
        act_type=act_type,
        year=year,
        slug=slug,
        expression_date=expression_date,
        language=language,
        element_path=element_path,
    )


def build_eli(u: EliUri) -> str:
    path = f"/eli/bg/{u.act_type}/{u.year}/{u.slug}"
    if u.expression_date is None:
        return path
    if u.expression_date == "latest":
        date_s = "latest"
    else:
        date_s = u.expression_date.isoformat()
    path += f"/{date_s}/{u.language}"
    if u.element_path:
        path += f"/{u.element_path}"
    return path
