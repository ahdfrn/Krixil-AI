from app.core.config import get_settings
from app.storage.base import ObjectStorage
from app.storage.minio_client import MinioObjectStorage

_instance: ObjectStorage | None = None


def get_storage() -> ObjectStorage:
    global _instance
    if _instance is None:
        _instance = MinioObjectStorage(get_settings())
    return _instance
