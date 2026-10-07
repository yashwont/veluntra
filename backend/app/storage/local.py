import asyncio
import uuid
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings


class LocalFileStorage:
    """Stores uploaded files on local disk under a root directory.

    Callers never choose a path. A key is generated here (`<workspace>/<random>`),
    so user-supplied filenames never touch the filesystem, and `_path` refuses any
    key that would resolve outside the root.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def new_key(self, workspace_id: uuid.UUID) -> str:
        return f"{workspace_id}/{uuid.uuid4().hex}"

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("storage key escapes the storage root")
        return path

    async def save(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self._save, key, data)

    def _save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def read(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    def path_of(self, key: str) -> Path:
        return self._path(key)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, True)  # missing_ok


@lru_cache
def get_file_storage() -> LocalFileStorage:
    return LocalFileStorage(Path(get_settings().document_storage_dir))
