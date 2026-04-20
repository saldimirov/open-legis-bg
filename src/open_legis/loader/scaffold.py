import datetime as dt
from pathlib import Path

_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">
  <act contains="originalVersion">
    <meta>
      <identification source="#openlegis">
        <FRBRWork>
          <FRBRthis value="/akn/bg/act/{year}/{slug}/main"/>
          <FRBRuri value="/akn/bg/act/{year}/{slug}"/>
          <FRBRalias value="{title}" name="short"/>
          <FRBRalias value="{title}" name="eli" other="/eli/bg/{act_type}/{year}/{slug}"/>
          <FRBRdate date="{expression_date}" name="Generation"/>
          <FRBRauthor href="#parliament"/>
          <FRBRcountry value="bg"/>
          <FRBRnumber value="1"/>
        </FRBRWork>
        <FRBRExpression>
          <FRBRthis value="/akn/bg/act/{year}/{slug}/{language}@{expression_date}/main"/>
          <FRBRuri value="/akn/bg/act/{year}/{slug}/{language}@{expression_date}"/>
          <FRBRdate date="{expression_date}" name="Generation"/>
          <FRBRauthor href="#parliament"/>
          <FRBRlanguage language="{language}"/>
        </FRBRExpression>
        <FRBRManifestation>
          <FRBRthis value="/akn/bg/act/{year}/{slug}/{language}@{expression_date}/main.xml"/>
          <FRBRuri value="/akn/bg/act/{year}/{slug}/{language}@{expression_date}.xml"/>
          <FRBRdate date="{expression_date}" name="Generation"/>
          <FRBRauthor href="#parliament"/>
          <FRBRformat value="application/akn+xml"/>
        </FRBRManifestation>
      </identification>
      <publication date="{expression_date}" name="Държавен вестник" number="{dv_broy}" showAs="ДВ"/>
      <references source="#openlegis">
        <TLCOrganization eId="parliament" href="/ontology/organization/bg/NarodnoSabranie" showAs="Народно събрание"/>
        <TLCPerson eId="openlegis" href="/ontology/person/openlegis" showAs="open-legis"/>
      </references>
    </meta>
    <preface><p>{title}</p></preface>
    <body>
      <!-- Author articles below; structure: part/title/chapter/section/article/paragraph/point/letter -->
      <article eId="art_1">
        <num>Чл. 1</num>
        <heading>TODO</heading>
        <paragraph eId="art_1__para_1">
          <num>(1)</num>
          <content><p>TODO текст на разпоредбата.</p></content>
        </paragraph>
      </article>
    </body>
  </act>
</akomaNtoso>
"""


def scaffold_fixture(
    root: Path,
    act_type: str,
    year: int,
    slug: str,
    expression_date: dt.date,
    language: str,
    title: str,
    dv_broy: int,
    dv_year: int,
) -> Path:
    out_dir = root / act_type / str(year) / slug / "expressions"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{expression_date.isoformat()}.{language}.xml"
    if out.exists():
        raise FileExistsError(out)
    out.write_text(
        _TEMPLATE.format(
            act_type=act_type,
            year=year,
            slug=slug,
            expression_date=expression_date.isoformat(),
            language=language,
            title=title,
            dv_broy=dv_broy,
            dv_year=dv_year,
        )
    )
    return out
