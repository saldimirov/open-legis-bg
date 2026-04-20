from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = Field(..., alias="DATABASE_URL")
    fixtures_dir: Path = Field(
        default=Path("fixtures/akn"),
        alias="OPEN_LEGIS_FIXTURES_DIR",
    )
