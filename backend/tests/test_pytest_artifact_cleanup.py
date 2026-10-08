from pathlib import Path

import conftest


class _Engine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


def test_cleanup_removes_only_artifacts_for_new_default_paths(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "wms_pytest_run_worker.sqlite"
    data_dir = tmp_path / "wms_pytest_data_run_worker"
    neighbor_db = tmp_path / "wms_pytest_other_worker.sqlite"
    neighbor_data = tmp_path / "wms_pytest_data_other_worker"
    for suffix in conftest._TEST_DB_SIDECARS:
        Path(f"{db_path}{suffix}").write_text("test db")
    data_dir.mkdir()
    (data_dir / "artifact.json").write_text("{}")
    neighbor_db.write_text("keep")
    neighbor_data.mkdir()
    (neighbor_data / "artifact.json").write_text("keep")
    engine = _Engine()
    monkeypatch.setattr(conftest, "_TEST_DB_PATH", db_path)
    monkeypatch.setattr(conftest, "_TEST_DATA_DIR", data_dir)
    monkeypatch.setattr(conftest, "_AUTO_TEST_DB_CLEANUP", True)
    monkeypatch.setattr(conftest, "_AUTO_TEST_DATA_CLEANUP", True)
    monkeypatch.setattr(conftest, "engine", engine)

    conftest._cleanup_generated_test_artifacts()

    assert engine.disposed
    assert not any(Path(f"{db_path}{suffix}").exists() for suffix in conftest._TEST_DB_SIDECARS)
    assert not data_dir.exists()
    assert neighbor_db.read_text() == "keep"
    assert (neighbor_data / "artifact.json").read_text() == "keep"


def test_cleanup_preserves_explicit_or_preexisting_paths(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "wms_pytest_existing.sqlite"
    data_dir = tmp_path / "wms_pytest_data_existing"
    db_path.write_text("keep")
    data_dir.mkdir()
    (data_dir / "artifact.json").write_text("keep")
    engine = _Engine()
    monkeypatch.setattr(conftest, "_TEST_DB_PATH", db_path)
    monkeypatch.setattr(conftest, "_TEST_DATA_DIR", data_dir)
    monkeypatch.setattr(conftest, "_AUTO_TEST_DB_CLEANUP", False)
    monkeypatch.setattr(conftest, "_AUTO_TEST_DATA_CLEANUP", False)
    monkeypatch.setattr(conftest, "engine", engine)

    conftest._cleanup_generated_test_artifacts()

    assert not engine.disposed
    assert db_path.read_text() == "keep"
    assert (data_dir / "artifact.json").read_text() == "keep"


def test_cleanup_failure_warns_and_preserves_artifacts(monkeypatch, tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "wms_pytest_run_worker.sqlite"
    data_dir = tmp_path / "wms_pytest_data_run_worker"
    db_path.write_text("keep")
    data_dir.mkdir()
    (data_dir / "artifact.json").write_text("keep")

    class FailedEngine:
        async def dispose(self) -> None:
            raise RuntimeError("close failed")

    monkeypatch.setattr(conftest, "_TEST_DB_PATH", db_path)
    monkeypatch.setattr(conftest, "_TEST_DATA_DIR", data_dir)
    monkeypatch.setattr(conftest, "_AUTO_TEST_DB_CLEANUP", True)
    monkeypatch.setattr(conftest, "_AUTO_TEST_DATA_CLEANUP", True)
    monkeypatch.setattr(conftest, "engine", FailedEngine())

    conftest._cleanup_generated_test_artifacts()

    assert db_path.read_text() == "keep"
    assert (data_dir / "artifact.json").read_text() == "keep"
    assert "could not dispose database engine" in capsys.readouterr().err
