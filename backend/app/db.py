from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

IS_SQLITE = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    # SQLite: allow use from the background audit tasks. PostgreSQL: fail fast instead of
    # hanging forever when the database server is down.
    connect_args={"check_same_thread": False} if IS_SQLITE else {"connect_timeout": 5},
    # Replace connections the database closed while idle (e.g. after a PostgreSQL restart).
    pool_pre_ping=not IS_SQLITE,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def describe_database() -> str:
    """The database location with any password hidden, safe to print in logs."""
    return engine.url.render_as_string(hide_password=True)
