from abc import ABC, abstractmethod


class ObjectStorage(ABC):
    """Abstraction over the object store so document upload/parse code doesn't depend on MinIO
    specifically, and tests can swap in an in-memory fake instead of a real server."""

    @abstractmethod
    async def ensure_bucket(self) -> None: ...

    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    async def get(self, key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...
