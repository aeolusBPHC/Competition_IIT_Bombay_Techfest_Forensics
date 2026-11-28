"""Keep trusted custody state in each test's own temporary directory."""
import pytest


@pytest.fixture(autouse=True)
def isolated_custody_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DRONE_FORENSICS_TRUST_DIR", str(tmp_path / "trusted-checkpoints"))
