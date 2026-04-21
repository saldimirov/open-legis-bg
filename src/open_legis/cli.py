import typer

app = typer.Typer(help="open-legis — tools for the Bulgarian legislation database")


@app.command()
def load(path: str = typer.Argument("fixtures/akn", help="Path to fixtures directory")) -> None:
    """Load fixtures into the database."""
    from pathlib import Path

    from open_legis.loader.cli import load_directory
    from open_legis.model.db import make_engine
    from open_legis.settings import Settings

    settings = Settings()
    engine = make_engine(settings.database_url)
    load_directory(Path(path), engine=engine)
    typer.echo(f"loaded {path}")


@app.command()
def dump(
    out: str = typer.Option("dumps/latest.tar.gz", help="Output tarball path"),
    fixtures: str = typer.Option("fixtures/akn", help="Fixtures root"),
) -> None:
    """Build a deterministic snapshot tarball."""
    from pathlib import Path

    from open_legis.dumps.build import build_tarball
    from open_legis.model.db import make_engine
    from open_legis.settings import Settings

    engine = make_engine(Settings().database_url)
    build_tarball(engine=engine, fixtures_dir=Path(fixtures), out_path=Path(out))
    typer.echo(f"wrote {out}")


@app.command("dump-sql")
def dump_sql(
    out: str = typer.Option("dumps/latest.sql.gz", help="Output SQL.gz path"),
) -> None:
    """Build a gzipped pg_dump of the current database."""
    from pathlib import Path

    from open_legis.dumps.build import build_sql_dump
    from open_legis.settings import Settings

    build_sql_dump(database_url=Settings().database_url, out_path=Path(out))
    typer.echo(f"wrote {out}")


@app.command("new-fixture")
def new_fixture(
    type_: str = typer.Option(..., "--type"),
    slug: str = typer.Option(..., "--slug"),
    year: int = typer.Option(...),
    date: str = typer.Option(..., "--date"),
    language: str = typer.Option("bul", "--lang"),
    title: str = typer.Option(..., "--title"),
    dv_broy: int = typer.Option(..., "--dv-broy"),
    root: str = typer.Option("fixtures/akn", "--root"),
) -> None:
    """Scaffold a new AKN fixture skeleton."""
    import datetime as _dt
    from pathlib import Path

    from open_legis.loader.scaffold import scaffold_fixture

    out = scaffold_fixture(
        root=Path(root),
        act_type=type_,
        slug=slug,
        year=year,
        expression_date=_dt.date.fromisoformat(date),
        language=language,
        title=title,
        dv_broy=dv_broy,
        dv_year=_dt.date.fromisoformat(date).year,
    )
    typer.echo(f"created {out}")


@app.command("scrape-dv")
def scrape_dv(
    idobj: int = typer.Option(..., "--idobj", help="DV issue idObj to scrape"),
    out: str = typer.Option("fixtures/akn", "--out", help="Output fixtures root"),
    load_after: bool = typer.Option(True, "--load/--no-load", help="Load into DB after scrape"),
    types: str = typer.Option("zakon,kodeks", "--types", help="Comma-separated act types to include"),
) -> None:
    """Scrape laws from a single DV issue and optionally load them."""
    import datetime as _dt
    from pathlib import Path

    from open_legis.scraper.dv_client import get_issue_materials, get_material_text, get_issue_metadata
    from open_legis.scraper.dv_to_akn import detect_act_type, convert_material, LEGISLATIVE_TYPES

    allowed_types = {t.strip() for t in types.split(",")} if types else LEGISLATIVE_TYPES
    out_root = Path(out)

    issue = get_issue_metadata(idobj)
    if not issue:
        typer.echo(f"Could not find issue for idObj={idobj}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Scraping broy={issue.broy} year={issue.year} date={issue.date}")

    materials = get_issue_materials(idobj)
    typer.echo(f"Found {len(materials)} materials")

    saved: list[Path] = []
    for mat in materials:
        title, body = get_material_text(mat.idMat)
        if not title:
            continue
        act_type = detect_act_type(title)
        if act_type not in allowed_types:
            typer.echo(f"  skip {act_type}: {title[:60]}")
            continue

        typer.echo(f"  {act_type}: {title[:70]}")
        slug, xml = convert_material(
            title=title,
            body=body,
            idMat=mat.idMat,
            issue=issue,
            position=mat.page,
        )

        # Write to fixtures/akn/{act_type}/{year}/{slug}/expressions/{date}.bul.xml
        expr_dir = out_root / act_type / str(issue.year) / slug / "expressions"
        expr_dir.mkdir(parents=True, exist_ok=True)
        akn_path = expr_dir / f"{issue.date}.bul.xml"
        akn_path.write_text(xml, encoding="utf-8")
        typer.echo(f"    -> {akn_path}")
        saved.append(akn_path)

    typer.echo(f"Saved {len(saved)} fixtures")

    if load_after and saved:
        from open_legis.loader.cli import load_directory
        from open_legis.model.db import make_engine
        from open_legis.settings import Settings

        engine = make_engine(Settings().database_url)
        load_directory(out_root, engine=engine)
        typer.echo("Loaded into DB")


if __name__ == "__main__":
    app()
