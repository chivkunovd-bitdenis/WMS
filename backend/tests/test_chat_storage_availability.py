"""WMS-397/399 metadata-only attachment checks; no remote account/network."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from app.services.object_storage_service import LocalObjectStorage, S3ObjectStorage


def test_local_stat_and_missing_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend = LocalObjectStorage(str(tmp_path))
    backend.put_bytes("chat/file", b"isolated", content_type="text/plain")
    with monkeypatch.context() as patch:
        read = Mock(side_effect=AssertionError("metadata check must not read bytes"))
        patch.setattr(Path, "read_bytes", read)
        assert backend.object_exists("chat/file")
        assert not backend.object_exists("chat/absent")
        read.assert_not_called()
    backend.delete_object("chat/file")
    backend.delete_object("chat/file")
    assert not backend.object_exists("chat/file")
    with pytest.raises(ValueError, match="invalid_storage_key"):
        backend.object_exists("../outside")
    denied = Mock(
        stat=Mock(side_effect=PermissionError("isolated")),
        unlink=Mock(side_effect=PermissionError("isolated")),
    )
    monkeypatch.setattr(backend, "_resolve", lambda key: denied)
    with pytest.raises(PermissionError):
        backend.object_exists("chat/file")
    with pytest.raises(PermissionError):
        backend.delete_object("chat/file")


@pytest.mark.parametrize("code", [None, "404", "NoSuchKey", "NotFound", "403", "SlowDown", "500"])
def test_s3_head_and_idempotent_delete(code: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    monkeypatch.setattr(S3ObjectStorage, "_build_client", staticmethod(lambda **kwargs: client))
    backend = S3ObjectStorage(
        bucket="isolated",
        region="isolated",
        prefix="prefix",
        endpoint_url=None,
        access_key_id=None,
        secret_access_key=None,
    )
    if code:
        client.head_object.side_effect = ClientError({"Error": {"Code": code}}, "HeadObject")
        client.delete_object.side_effect = ClientError({"Error": {"Code": code}}, "DeleteObject")
    if code in {"403", "SlowDown", "500"}:
        with pytest.raises(ClientError):
            backend.object_exists("chat/file")
        with pytest.raises(ClientError):
            backend.delete_object("chat/file")
    else:
        assert backend.object_exists("chat/file") is (code is None)
        backend.delete_object("chat/file")
    client.head_object.assert_called_once_with(Bucket="isolated", Key="prefix/chat/file")
    client.get_object.assert_not_called()
