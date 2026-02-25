"""
StorageBackend abstract interface.
Swap local disk for S3 by changing STORAGE_BACKEND env var — no code changes.
"""

import abc
from pathlib import Path


class StorageBackend(abc.ABC):
    @abc.abstractmethod
    def save(self, data: bytes, filename: str, subfolder: str = "") -> str:
        """Persist data and return the storage path/key."""

    @abc.abstractmethod
    def load(self, path: str) -> bytes:
        """Load and return raw bytes from storage path/key."""

    @abc.abstractmethod
    def exists(self, path: str) -> bool:
        """Return True if the path/key exists in storage."""


class LocalDiskStorage(StorageBackend):
    """
    Stores files on the local filesystem (Render Disk mount in production).
    Root is set from settings.local_storage_path.
    """

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, filename: str, subfolder: str = "") -> str:
        target_dir = self.root / subfolder if subfolder else self.root
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filename
        target_path.write_bytes(data)
        # Return relative path string (portable across mounts)
        return str(target_path.relative_to(self.root))

    def load(self, path: str) -> bytes:
        return (self.root / path).read_bytes()

    def exists(self, path: str) -> bool:
        return (self.root / path).exists()


def get_storage() -> StorageBackend:
    """Factory — returns the configured storage backend."""
    from app.settings import settings

    if settings.storage_backend == "local":
        return LocalDiskStorage(settings.local_storage_path)
    elif settings.storage_backend == "s3":
        # S3 backend wired in v2 — import here to avoid hard dependency in v1
        raise NotImplementedError(
            "S3 storage backend is not yet implemented. "
            "Set STORAGE_BACKEND=local for v1."
        )
    else:
        raise ValueError(f"Unknown storage backend: {settings.storage_backend!r}")
