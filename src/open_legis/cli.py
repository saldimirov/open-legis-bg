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
        try:
            with engine.connect() as conn:
                count = conn.execute(text("SELECT COUNT(*) FROM work")).scalar()
            if count:
                typer.echo(f"skipping load — {count} works already in DB")
                return
        except Exception:
            typer.echo("--if-empty: DB not ready (run migrations first)", err=True)
            raise typer.Exit(1)

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
        act_type, _ = detect_act_type(title)
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
    types: str = typer.Option("zakon,zid,byudjet,kodeks,ratifikatsiya", "--types"),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Skip already-scraped fixtures"),
    sleep: float = typer.Option(0.8, "--sleep", help="Seconds between requests"),
    local_dir: Optional[str] = typer.Option(None, "--local-dir", help="Local DV mirror directory; use local files instead of HTTP when available"),
    workers: int = typer.Option(4, "--workers", help="Parallel workers for local-mirror mode (1 = sequential)"),
) -> None:
    """Scrape all laws from a year range and load into DB."""
    import datetime as _dt
    from pathlib import Path

    from open_legis.scraper.dv_client import get_issue_materials, get_material_text
    from open_legis.scraper.dv_to_akn import detect_act_type, convert_material, LEGISLATIVE_TYPES
    from open_legis.scraper.dv_index import crawl_year, crawl_years, save_index, load_index
    from open_legis.scraper.dv_mirror import issue_path as local_issue_path
    from open_legis.scraper.rtf_parser import parse_local_issue

    allowed_types = {t.strip() for t in types.split(",")} if types else LEGISLATIVE_TYPES
    out_root = Path(out)
    idx_path = Path(index_file)
    local_root = Path(local_dir) if local_dir else None

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
        issues = [i for i in all_issues if y_from <= i.year <= y_to]
        if not issues:
            typer.echo(f"No cached issues for {y_from}-{y_to}, crawling...")
            issues = crawl_years(y_from, y_to, sleep=sleep, progress_cb=typer.echo)
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

    # Split issues into local-mirror candidates and HTTP fallbacks
    local_tasks: list[tuple] = []
    http_issues = []

    for issue in issues:
        lp = local_issue_path(issue, local_root) if local_root else None
        if lp and lp.exists():
            local_tasks.append((
                (issue.idObj, issue.broy, issue.year, issue.date),
                str(lp),
                allowed_types,
                str(out_root),
                resume,
            ))
        else:
            http_issues.append(issue)

    # ── Local mirror — parallel ────────────────────────────────────────────────
    if local_tasks:
        from open_legis.scraper.batch import process_issue_local

        if workers > 1:
            from concurrent.futures import ProcessPoolExecutor, as_completed
            typer.echo(f"Processing {len(local_tasks)} local issues with {workers} workers")
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futs = {pool.submit(process_issue_local, *task): task for task in local_tasks}
                for fut in as_completed(futs):
                    try:
                        s, sk, logs = fut.result()
                    except Exception as exc:
                        typer.echo(f"  WORKER ERROR: {exc}", err=True)
                        continue
                    saved_total += s
                    skipped_total += sk
                    for line in logs:
                        typer.echo(line)
        else:
            for task in local_tasks:
                s, sk, logs = process_issue_local(*task)
                saved_total += s
                skipped_total += sk
                for line in logs:
                    typer.echo(line)

    # ── HTTP fallback — sequential ─────────────────────────────────────────────
    for issue in http_issues:
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
            act_type, _ = detect_act_type(title)
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


@app.command("repair-bodies")
def repair_bodies(
    fixtures: str = typer.Option("fixtures/akn", "--fixtures", help="AKN fixtures root"),
    mirror: str = typer.Option("local_dv", "--mirror", help="Local DV mirror directory"),
    index_file: str = typer.Option(".dv-index.json", "--index-file", help="DV issue index"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would be fixed without writing"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Re-parse empty-body fixtures from the local DV mirror, preserving existing slugs."""
    import re as _re
    from pathlib import Path

    from lxml import etree

    from open_legis.scraper.dv_index import load_index
    from open_legis.scraper.dv_mirror import issue_path as local_issue_path
    from open_legis.scraper.rtf_parser import parse_local_issue
    from open_legis.scraper.dv_to_akn import convert_material
    from open_legis.scraper.dv_client import DvIssue

    _AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
    _NS = {"akn": _AKN_NS}
    _SLUG_RE = _re.compile(r"^dv-(?P<broy>\d+)-\d+-(?P<pos>\d+)$")

    fixtures_root = Path(fixtures)
    mirror_root = Path(mirror)
    idx_path = Path(index_file)

    if not idx_path.exists():
        typer.echo(f"Index not found: {index_file}", err=True)
        raise typer.Exit(1)

    all_issues = load_index(idx_path)
    index: dict[tuple[int, int], DvIssue] = {(i.broy, i.year): i for i in all_issues}

    # Find all empty-body fixtures
    empty_fixtures: list[Path] = []
    for f in sorted(fixtures_root.rglob("*.bul.xml")):
        try:
            tree = etree.parse(f)
            body = tree.find(".//akn:body", _NS)
            if body is None or len(body) == 0:
                empty_fixtures.append(f)
        except etree.XMLSyntaxError:
            pass

    typer.echo(f"Found {len(empty_fixtures)} empty-body fixtures")

    # Cache parsed local files — one parse per DV issue
    _parsed_cache: dict[Path, list[tuple[str, str]]] = {}

    fixed = skipped = failed = 0

    for f in empty_fixtures:
        parts = f.relative_to(fixtures_root).parts
        if len(parts) < 4:
            continue
        act_type, year_str, slug = parts[0], parts[1], parts[2]

        m = _SLUG_RE.match(slug)
        if not m:
            if verbose:
                typer.echo(f"  skip non-standard slug: {slug}")
            skipped += 1
            continue

        broy = int(m.group("broy"))
        position = int(m.group("pos"))
        year = int(year_str)

        issue = index.get((broy, year))
        if not issue:
            if verbose:
                typer.echo(f"  no index entry for broy={broy} year={year}: {f.name}")
            skipped += 1
            continue

        local_path = local_issue_path(issue, mirror_root)
        if not local_path or not local_path.exists():
            if verbose:
                typer.echo(f"  no local file for {slug}")
            skipped += 1
            continue

        if local_path not in _parsed_cache:
            try:
                _parsed_cache[local_path] = parse_local_issue(local_path)
            except Exception as e:
                typer.echo(f"  ERROR parsing {local_path.name}: {e}", err=True)
                _parsed_cache[local_path] = []

        materials = _parsed_cache[local_path]
        if not materials:
            skipped += 1
            continue

        # Get original title from fixture
        try:
            tree = etree.parse(f)
            alias = tree.find(".//akn:FRBRalias[@name='short']", _NS)
            orig_title = alias.get("value", "") if alias is not None else ""
        except Exception:
            skipped += 1
            continue

        if not orig_title:
            skipped += 1
            continue

        # Find best matching material by title prefix
        best_body = ""
        best_score = 0
        orig_prefix = orig_title.lower()[:60]
        for mat_title, mat_body in materials:
            mat_prefix = mat_title.lower()[:60]
            # Score: length of common prefix
            common = sum(1 for a, b in zip(orig_prefix, mat_prefix) if a == b)
            if common > best_score and common >= 15 and mat_body:
                best_score = common
                best_body = mat_body

        if not best_body:
            if verbose:
                typer.echo(f"  no match for: {orig_title[:60]}")
            skipped += 1
            continue

        if dry_run:
            typer.echo(f"  would fix: {f.relative_to(fixtures_root)} (score={best_score})")
            fixed += 1
            continue

        try:
            _, xml = convert_material(
                title=orig_title,
                body=best_body,
                idMat=0,
                issue=issue,
                position=position,
            )
            f.write_text(xml, encoding="utf-8")
            if verbose:
                typer.echo(f"  fixed: {f.relative_to(fixtures_root)}")
            fixed += 1
        except Exception as e:
            typer.echo(f"  ERROR converting {slug}: {e}", err=True)
            failed += 1

    action = "would fix" if dry_run else "fixed"
    typer.echo(f"Done: {fixed} {action}, {skipped} skipped, {failed} failed")


@app.command("match-amendments")
def match_amendments(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print matches without writing to DB"),
    min_score: float = typer.Option(0.45, "--min-score", help="Minimum Jaccard score to accept a match"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print all matches"),
) -> None:
    """Match ZIDs to their target base laws and populate the amendment table."""
    from open_legis.loader.amendment_matcher import match_all, populate_amendments
    from open_legis.model.db import make_engine
    from open_legis.settings import Settings
    from sqlalchemy.orm import Session

    engine = make_engine(Settings().database_url)
    with Session(engine) as session:
        matches = match_all(session, min_score=min_score)
        typer.echo(f"Found {len(matches)} matches (min_score={min_score})")

        if verbose or dry_run:
            for r in matches:
                mark = f"[{r.score:.2f}]"
                typer.echo(f"  {mark} {r.zid.title[:60]}")
                typer.echo(f"        → {r.target.title[:60]}")

        if dry_run:
            typer.echo("Dry run — nothing written.")
            return

        count = populate_amendments(session, matches)
        typer.echo(f"Inserted {count} amendment links.")


@app.command("cache-dv")
def cache_dv(
    out: str = typer.Option("local_dv", "--out", help="Directory to store RTF files"),
    index_file: str = typer.Option(".dv-index.json", "--index-file"),
    year: Optional[int] = typer.Option(None, "--year"),
    from_year: Optional[int] = typer.Option(None, "--from-year"),
    to_year: Optional[int] = typer.Option(None, "--to-year"),
    workers: int = typer.Option(4, "--workers", help="Parallel download workers"),
    sleep: float = typer.Option(0.5, "--sleep", help="Seconds between requests per worker"),
) -> None:
    """Download DV issues as RTF files to a local mirror."""
    from pathlib import Path

    from open_legis.scraper.dv_index import load_index
    from open_legis.scraper.dv_mirror import mirror_issues

    idx_path = Path(index_file)
    if not idx_path.exists():
        typer.echo(f"Index file not found: {index_file}", err=True)
        raise typer.Exit(1)

    all_issues = load_index(idx_path)

    if year:
        issues = [i for i in all_issues if i.year == year]
    elif from_year and to_year:
        issues = [i for i in all_issues if from_year <= i.year <= to_year]
    elif from_year:
        issues = [i for i in all_issues if i.year >= from_year]
    else:
        issues = all_issues

    typer.echo(f"Mirroring {len(issues)} issues → {out}  (workers={workers})")

    saved, skipped, failed = mirror_issues(
        issues,
        out_dir=Path(out),
        workers=workers,
        sleep=sleep,
        progress_cb=typer.echo,
    )
    typer.echo(f"Done: {saved} downloaded, {skipped} skipped, {failed} failed")


@app.command("validate")
def validate(
    fixtures: str = typer.Option("fixtures/akn", "--fixtures", help="AKN fixtures root"),
    mirror: str = typer.Option("local_dv", "--mirror", help="Local DV mirror directory"),
    index_file: str = typer.Option(".dv-index.json", "--index-file", help="DV issue index"),
    layer: Optional[str] = typer.Option(
        None, "--layer",
        help="Run only one layer: mirror|fixtures|classify|db|eli (default: all)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show all issues"),
    json_out: Optional[str] = typer.Option(None, "--json", help="Write JSON report to file"),
) -> None:
    """Validate the data pipeline: mirror → fixtures → DB."""
    from pathlib import Path

    from open_legis.validate.mirror import check_mirror
    from open_legis.validate.fixtures import check_fixtures
    from open_legis.validate.classify import check_classification
    from open_legis.validate.eli import check_eli
    from open_legis.validate.report import print_report, write_json_report

    fixtures_path = Path(fixtures)
    mirror_path = Path(mirror)
    index_path = Path(index_file)

    results = []

    def _run(name: str, fn, *args):
        if layer is None or layer == name:
            results.append(fn(*args))

    _run("mirror", check_mirror, index_path, mirror_path)
    _run("fixtures", check_fixtures, fixtures_path)
    _run("classify", check_classification, fixtures_path)

    if layer is None or layer == "db":
        from open_legis.validate.db import check_db
        from open_legis.model.db import make_engine
        from open_legis.settings import Settings
        from sqlalchemy.orm import Session

        engine = make_engine(Settings().database_url)
        with Session(engine) as session:
            results.append(check_db(fixtures_path, session))

    _run("eli", check_eli, fixtures_path)

    if json_out:
        write_json_report(results, json_out)

    error_count = print_report(results, verbose=verbose)
    raise typer.Exit(code=1 if error_count > 0 else 0)


@app.command("parse-zid-ops")
def parse_zid_ops(
    limit: Optional[int] = typer.Option(None, "--limit", help="Max ZIDs to process (for testing)"),
    sleep: float = typer.Option(0.2, "--sleep", help="Seconds between API calls"),
) -> None:
    """Parse ZID § paragraphs with LLM and populate consolidation_op table."""
    from sqlalchemy.orm import Session

    from open_legis.consolidation.populate import populate_ops
    from open_legis.model.db import make_engine
    from open_legis.settings import Settings

    settings = Settings()
    if not settings.anthropic_api_key:
        typer.echo("ANTHROPIC_API_KEY not set", err=True)
        raise typer.Exit(1)

    engine = make_engine(settings.database_url)
    with Session(engine) as session:
        inserted, skipped, failed = populate_ops(
            session,
            api_key=settings.anthropic_api_key,
            limit=limit,
            sleep=sleep,
            progress_cb=typer.echo,
        )
    typer.echo(f"Done: {inserted} ops inserted, {skipped} amendments skipped, {failed} failed")


if __name__ == "__main__":
    app()
