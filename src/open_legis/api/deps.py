from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from open_legis.model.db import make_engine
from open_legis.settings import Settings


@lru_cache
def _engine() -> Engine:
    return make_engine(Settings().database_url)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with _session_factory()() as s:
        yield s


def reset_for_tests() -> None:
    _engine.cache_clear()
    _session_factory.cache_clear()
