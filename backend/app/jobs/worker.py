"""Background worker. It claims jobs; it does not decide merges or shares."""

from __future__ import annotations

import os
import socket
import time

from app.db import make_engine, make_session_factory
from app.jobs.queue import run_once
from app.services.pipeline import run_extract
from app.services.retention import apply_retention


def main() -> None:
    factory = make_session_factory(make_engine())
    session = factory()
    try:
        apply_retention(session)
        session.commit()
    finally:
        session.close()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    while True:
        session = factory()
        try:
            worked = run_once(session, worker_id=worker_id, handler=run_extract)
        finally:
            session.close()
        if not worked:
            time.sleep(1)


if __name__ == "__main__":
    main()
