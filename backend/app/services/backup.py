"""Local backup copies. AWS backup is described here and is not deployed."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

# Production plan only. create_backup never calls AWS.
AWS_BACKUP_PLAN = {
    "implemented": False,
    "services": ["rds_automated_backups", "s3_versioning"],
    "notes": (
        "RDS automated backups with point-in-time recovery, encrypted, at least 7 days. "
        "CV files in S3 with versioning. This plan is not deployed."
    ),
}


def create_backup(session: Session, *, storage_dir: Path, destination: Path) -> dict:
    """Copy table rows and stored files into a new folder. Source rows stay in place."""
    folder = destination / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True)
    tables: dict[str, int] = {}
    names = sorted(inspect(session.get_bind()).get_table_names())
    for name in names:
        rows = session.execute(text(f'SELECT * FROM "{name}"')).mappings().all()
        payload = [_plain(dict(row)) for row in rows]
        (folder / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
        tables[name] = len(payload)
    storage_files = _copy_storage(storage_dir, folder / "storage")
    manifest = {
        "kind": "local_demo",
        "aws_backup_implemented": False,
        "tables": tables,
        "storage_files": storage_files,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def _copy_storage(source: Path, destination: Path) -> int:
    if not source.exists():
        return 0
    count = 0
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        count += 1
    return count


def _plain(row: dict) -> dict:
    return {key: _value(value) for key, value in row.items()}


def _value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, UUID, Decimal)):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return {"omitted_bytes": len(bytes(value))}
    if isinstance(value, list):
        return [_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _value(item) for key, item in value.items()}
    return str(value)
