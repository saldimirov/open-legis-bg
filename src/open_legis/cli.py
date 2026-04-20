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
) -> None:
    """Scaffold a new AKN fixture skeleton."""
    typer.echo(f"stub: would scaffold {type_}/{year}/{slug} @ {date}")


if __name__ == "__main__":
    app()
