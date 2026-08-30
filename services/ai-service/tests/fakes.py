from app.storage.base import ObjectStorage


class FakeObjectStorage(ObjectStorage):
    """In-memory stand-in for MinIO — offline tests exercise the upload/parse/chunk/list/delete
    flow without a real object store."""

    def __init__(self):
        self._objects: dict[str, bytes] = {}

    async def ensure_bucket(self) -> None:
        pass

    async def upload(self, key: str, data: bytes, content_type: str) -> None:
        self._objects[key] = data

    async def get(self, key: str) -> bytes:
        return self._objects[key]

    async def delete(self, key: str) -> None:
        self._objects.pop(key, None)
