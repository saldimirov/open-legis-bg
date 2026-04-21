from typing import Optional

import typer

app = typer.Typer(help="open-legis — tools for the Bulgarian legislation database")


@app.command()
def load(
    path: str = typer.Argument("fixtures/akn", help="Path to fixtures directory"),
    if_empty: bool = typer.Option(False, "--if-empty", help="Skip loading if the database already has works."),
) -> None:
    """Load fixtures into the database."""
    from pathlib import Path

    from sqlalchemy import text

    from open_legis.loader.cli import load_directory
    from open_legis.model.db import make_engine
    from open_legis.settings import Settings

    settings = Settings()
    engine = make_engine(settings.database_url)

    if if_empty:
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM work")).scalar()
        if count:
            typer.echo(f"skipping load — {count} works already in DB")
            return

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
    types: str = typer.Option("zakon,zid,kodeks", "--types", help="Comma-separated act types to include"),
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


@app.command("scrape-dv-batch")
def scrape_dv_batch(
    year: Optional[int] = typer.Option(None, "--year", help="Single year to scrape"),
    from_year: Optional[int] = typer.Option(None, "--from-year"),
    to_year: Optional[int] = typer.Option(None, "--to-year"),
    out: str = typer.Option("fixtures/akn", "--out"),
    index_file: str = typer.Option(".dv-index.json", "--index-file", help="Issue index cache"),
    load_after: bool = typer.Option(True, "--load/--no-load"),
    types: str = typer.Option("zakon,kodeks", "--types"),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Skip already-scraped fixtures"),
    sleep: float = typer.Option(0.8, "--sleep", help="Seconds between requests"),
) -> None:
    """Scrape all laws from a year range and load into DB."""
    import datetime as _dt
    from pathlib import Path

    from open_legis.scraper.dv_client import get_issue_materials, get_material_text
    from open_legis.scraper.dv_to_akn import detect_act_type, convert_material, LEGISLATIVE_TYPES
    from open_legis.scraper.dv_index import crawl_year, crawl_years, save_index, load_index

    allowed_types = {t.strip() for t in types.split(",")} if types else LEGISLATIVE_TYPES
    out_root = Path(out)
    idx_path = Path(index_file)

    # Resolve year range
    if year:
        y_from, y_to = year, year
    elif from_year and to_year:
        y_from, y_to = from_year, to_year
    elif from_year:
        y_from, y_to = from_year, _dt.date.today().year
    else:
        typer.echo("Provide --year or --from-year", err=True)
        raise typer.Exit(1)

    # Build or load issue index
    if idx_path.exists():
        all_issues = load_index(idx_path)
        # Filter to requested range
        issues = [i for i in all_issues if y_from <= i.year <= y_to]
        if not issues:
            typer.echo(f"No cached issues for {y_from}-{y_to}, crawling...")
            issues = crawl_years(y_from, y_to, sleep=sleep, progress_cb=typer.echo)
            # Merge into cache
            existing_idObjs = {i.idObj for i in all_issues}
            new_issues = [i for i in issues if i.idObj not in existing_idObjs]
            all_issues.extend(new_issues)
            save_index(all_issues, idx_path)
    else:
        typer.echo(f"Building issue index for {y_from}-{y_to}...")
        issues = crawl_years(y_from, y_to, sleep=sleep, progress_cb=typer.echo)
        save_index(issues, idx_path)

    typer.echo(f"Found {len(issues)} issues for {y_from}-{y_to}")

    saved_total = 0
    skipped_total = 0

    for issue in issues:
        typer.echo(f"Issue broy={issue.broy}/{issue.year} ({issue.date}) idObj={issue.idObj}")
        try:
            materials = get_issue_materials(issue.idObj, sleep=sleep)
        except Exception as e:
            typer.echo(f"  ERROR fetching materials: {e}", err=True)
            continue

        for mat in materials:
            try:
                title, body = get_material_text(mat.idMat, sleep=sleep)
            except Exception as e:
                typer.echo(f"  ERROR fetching idMat={mat.idMat}: {e}", err=True)
                continue

            if not title:
                continue
            act_type = detect_act_type(title)
            if act_type not in allowed_types:
                continue

            slug, xml = convert_material(
                title=title, body=body, idMat=mat.idMat,
                issue=issue, position=mat.page,
            )
            expr_dir = out_root / act_type / str(issue.year) / slug / "expressions"
            akn_path = expr_dir / f"{issue.date}.bul.xml"

            if resume and akn_path.exists():
                skipped_total += 1
                continue

            expr_dir.mkdir(parents=True, exist_ok=True)
            akn_path.write_text(xml, encoding="utf-8")
            typer.echo(f"  + {act_type}: {title[:65]}")
            saved_total += 1

    typer.echo(f"Done: {saved_total} saved, {skipped_total} skipped")

    if load_after and saved_total > 0:
        from open_legis.loader.cli import load_directory
        from open_legis.model.db import make_engine
        from open_legis.settings import Settings

        engine = make_engine(Settings().database_url)
        load_directory(out_root, engine=engine)
        typer.echo("Loaded into DB")


if __name__ == "__main__":
    app()
