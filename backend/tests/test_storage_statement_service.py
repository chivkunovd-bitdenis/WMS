import pytest

from app.services.storage_statement_service import StorageStatementError, _billing_models


def test_shared_billing_models_are_required() -> None:
    with pytest.raises(StorageStatementError, match="billing_models_unavailable"):
        _billing_models()
