import os
import tempfile
from pathlib import Path

os.environ["ENVIRONMENT"] = "local"
os.environ["HUB_RECRUITER_TOKEN"] = "dev-recruiter-token"
os.environ["HUB_ENGINEER_TOKEN"] = "dev-engineer-token"
os.environ["DATABASE_URL"] = "postgresql+psycopg://hub:hub@localhost:15432/hub_test"
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="hub-storage-")
os.environ["PROCESSING_VERSION"] = "1"
os.environ["EXTRACTOR_PROVIDER"] = "none"
os.environ["EMBEDDING_PROVIDER"] = "none"
os.environ["REQUIREMENT_PROVIDER"] = "deterministic"

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import reset_settings
from app.db import make_session_factory
from app.models import Base

reset_settings()

ADMIN_URL = "postgresql+psycopg://hub:hub@localhost:15432/hub"
TEST_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[None]:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.execute(text("SELECT 1 FROM pg_database WHERE datname = 'hub_test'")).scalar()
        if not exists:
            connection.execute(text("CREATE DATABASE hub_test"))
    admin.dispose()

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    os.environ["DATABASE_URL"] = TEST_URL
    command.upgrade(config, "head")
    yield
    command.downgrade(config, "base")


@pytest.fixture()
def session(migrated_database) -> Iterator[Session]:
    factory = make_session_factory(create_engine(TEST_URL, pool_pre_ping=True))
    db = factory()
    try:
        yield db
    finally:
        db.close()
        cleanup = factory()
        names = ", ".join(f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables))
        cleanup.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        cleanup.commit()
        cleanup.close()
