from sqlalchemy import create_engine, inspect

from app.models import Base


def test_billing_ff_profile_index_is_partial_on_sqlite() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    indexes = inspect(engine).get_indexes("billing_profiles")
    ff_index = next(index for index in indexes if index["name"] == "uq_billing_profiles_tenant_ff")

    assert ff_index["unique"] == 1
    assert "seller_id IS NULL" in str(ff_index["dialect_options"].get("sqlite_where"))
