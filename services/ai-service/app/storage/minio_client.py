import io

from minio import Minio
from minio.error import S3Error
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.storage.base import ObjectStorage


class MinioObjectStorage(ObjectStorage):
    """minio-py is a synchronous client; every call goes through run_in_threadpool so it never
    blocks the asyncio event loop (the same pattern FastAPI's own docs recommend for blocking I/O)."""

    def __init__(self, settings: Settings):
        self._bucket = settings.minio_bucket
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,  # local/dev MinIO is plain HTTP; front it with TLS in production via a proxy
        )

    async def ensure_bucket(self) -> None:
        await run_in_threadpool(self._ensure_bucket_sync)

    def _ensure_bucket_sync(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    async def upload(self, key: str, data: bytes, content_type: str) -> None:
        await run_in_threadpool(self._upload_sync, key, data, content_type)

    def _upload_sync(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(self._bucket, key, io.BytesIO(data), length=len(data), content_type=content_type)

    async def get(self, key: str) -> bytes:
        return await run_in_threadpool(self._get_sync, key)

    def _get_sync(self, key: str) -> bytes:
        response = self._client.get_object(self._bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    async def delete(self, key: str) -> None:
        try:
            await run_in_threadpool(self._client.remove_object, self._bucket, key)
        except S3Error as exc:
            if exc.code != "NoSuchKey":
                raise
