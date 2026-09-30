"""A local backup copies rows and leaves them in the database. AWS is not called."""

import json

from sqlalchemy import func, select

from app.models import Candidate
from app.services.backup import AWS_BACKUP_PLAN, create_backup


def test_local_backup_copies_rows_without_deleting_them(session, tmp_path):
    candidate = Candidate(source="upload", display_name="Ada Lovelace")
    session.add(candidate)
    session.commit()
    stored = session.scalar(select(func.count()).select_from(Candidate))
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "cv.bin").write_bytes(b"synthetic")
    manifest = create_backup(session, storage_dir=storage, destination=tmp_path / "backups")
    assert manifest["kind"] == "local_demo"
    assert manifest["aws_backup_implemented"] is False
    assert manifest["tables"]["candidates"] == stored
    assert manifest["storage_files"] == 1
    assert session.get(Candidate, candidate.id) is not None
    folder = next((tmp_path / "backups").iterdir())
    saved = json.loads((folder / "candidates.json").read_text(encoding="utf-8"))
    assert saved[0]["id"] == str(candidate.id)
    assert (folder / "storage" / "cv.bin").read_bytes() == b"synthetic"


def test_aws_backup_plan_is_not_implemented():
    assert AWS_BACKUP_PLAN["implemented"] is False
    assert "rds_automated_backups" in AWS_BACKUP_PLAN["services"]
    assert "s3_versioning" in AWS_BACKUP_PLAN["services"]
