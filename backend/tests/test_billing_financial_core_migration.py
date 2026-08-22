from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_billing_financial_core_is_in_the_single_alembic_lineage() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["20260822_0095"]
    assert script.get_revision("20260822_0094") is not None
