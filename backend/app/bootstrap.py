"""Create the local recruiter and engineer users. Tokens stay in the environment."""

from __future__ import annotations

from sqlalchemy import select

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.models import User


def provision(session) -> None:
    settings = get_settings()
    rows = (
        (settings.recruiter_email, "Cadence Recruiter", "recruiter"),
        (settings.engineer_email, "Cadence Engineer", "engineer"),
    )
    for email, full_name, role in rows:
        existing = session.scalar(select(User).where(User.email == email))
        if existing is None:
            session.add(User(email=email, full_name=full_name, role=role))
    session.commit()


def main() -> None:
    factory = make_session_factory(make_engine())
    session = factory()
    try:
        provision(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
