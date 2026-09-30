"""Write a local backup. AWS backups are not run from here."""

from __future__ import annotations

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.services.backup import create_backup


def main() -> None:
    settings = get_settings()
    factory = make_session_factory(make_engine())
    session = factory()
    try:
        manifest = create_backup(
            session,
            storage_dir=settings.storage_dir,
            destination=settings.backup_dir,
        )
    finally:
        session.close()
    print(f"local_demo tables={len(manifest['tables'])} aws_backup_implemented=false")


if __name__ == "__main__":
    main()
