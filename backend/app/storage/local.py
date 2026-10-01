"""Local filesystem storage. Keys are content hashes, not original filenames."""

from __future__ import annotations

from pathlib import Path


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, sha256: str, data: bytes) -> str:
        key = f"{sha256[:2]}/{sha256}"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_suffix(".partial")
            temporary.write_bytes(data)
            temporary.replace(path)
        return key

    def read(self, key: str) -> bytes:
        path = self.root / key
        if not path.is_file():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def delete(self, key: str) -> None:
        """Remove a stored object and its now-empty shard directory. Keys come from the
        database, so refuse anything that would escape the storage root."""
        path = (self.root / key).resolve()
        if path == self.root.resolve() or self.root.resolve() not in path.parents:
            return
        try:
            path.unlink()
        except FileNotFoundError:
            return
        parent = path.parent
        if parent != self.root.resolve() and not any(parent.iterdir()):
            parent.rmdir()
