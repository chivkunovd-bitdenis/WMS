from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol, cast

from app.core.settings import settings

logger = logging.getLogger(__name__)


class ObjectStorageBackend(Protocol):
    def put_bytes(self, key: str, content: bytes, *, content_type: str) -> None: ...

    def get_bytes(self, key: str) -> bytes: ...

    def delete_object(self, key: str) -> None: ...


class LocalObjectStorage:
    def __init__(self, root_dir: str) -> None:
        self._root = Path(root_dir).resolve()

    def _resolve(self, key: str) -> Path:
        root = self._root
        path = (root / key).resolve()
        if path != root and root not in path.parents:
            raise ValueError("invalid_storage_key")
        return path

    def put_bytes(self, key: str, content: bytes, *, content_type: str) -> None:
        del content_type
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def get_bytes(self, key: str) -> bytes:
        target = self._resolve(key)
        if not target.is_file():
            raise FileNotFoundError(key)
        return target.read_bytes()

    def delete_object(self, key: str) -> None:
        target = self._resolve(key)
        if target.is_file():
            target.unlink()


class S3ObjectStorage:
    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        prefix: str,
        endpoint_url: str | None,
        access_key_id: str | None,
        secret_access_key: str | None,
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._client: Any = self._build_client(
            region=region,
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        )

    @staticmethod
    def _build_client(
        *,
        region: str,
        endpoint_url: str | None,
        access_key_id: str | None,
        secret_access_key: str | None,
    ) -> object:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("s3_support_unavailable") from exc

        session_kwargs: dict[str, str] = {"region_name": region}
        if access_key_id and secret_access_key:
            session_kwargs["aws_access_key_id"] = access_key_id
            session_kwargs["aws_secret_access_key"] = secret_access_key
        session = boto3.session.Session(**session_kwargs)
        return cast(Any, session.client("s3", endpoint_url=endpoint_url))

    def _full_key(self, key: str) -> str:
        normalized = key.lstrip("/")
        if self._prefix:
            return f"{self._prefix}/{normalized}"
        return normalized

    def put_bytes(self, key: str, content: bytes, *, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=self._full_key(key),
            Body=content,
            ContentType=content_type,
        )

    def get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=self._full_key(key))
        body = response["Body"].read()
        return bytes(body)

    def delete_object(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=self._full_key(key))


def get_object_storage_backend() -> ObjectStorageBackend | None:
    if settings.wms_s3_bucket:
        return S3ObjectStorage(
            bucket=settings.wms_s3_bucket,
            region=settings.wms_s3_region,
            prefix=settings.wms_s3_prefix,
            endpoint_url=settings.wms_s3_endpoint_url,
            access_key_id=settings.wms_s3_access_key_id,
            secret_access_key=settings.wms_s3_secret_access_key,
        )
    if settings.wms_marking_import_local_storage_enabled:
        return LocalObjectStorage(settings.wms_data_dir)
    return None
