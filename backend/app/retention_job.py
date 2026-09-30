"""Archive documents older than the retention period. Rows are kept."""

from __future__ import annotations

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.services.retention import apply_retention


def main() -> None:
    settings = get_settings()
    factory = make_session_factory(make_engine())
    session = factory()
    try:
        count = apply_retention(session)
        session.commit()
    finally:
        session.close()
    print(f"archived={count} retention_days={settings.retention_days}")


if __name__ == "__main__":
    main()
