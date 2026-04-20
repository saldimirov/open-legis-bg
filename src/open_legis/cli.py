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
def dump(out: str = typer.Option("dumps/latest.tar.gz", help="Output tarball path")) -> None:
    """Build a deterministic snapshot tarball."""
    typer.echo(f"stub: would dump to {out}")


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


if __name__ == "__main__":
    app()
