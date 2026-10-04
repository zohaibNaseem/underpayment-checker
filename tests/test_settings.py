from __future__ import annotations

from pathlib import Path

import pytest

from underpayment_checker.settings import PROJECT_ROOT, Settings


def test_defaults_point_at_project_root() -> None:
    settings = Settings()
    assert settings.root == PROJECT_ROOT
    assert settings.reference_dir == PROJECT_ROOT / "reference"
    assert settings.bronze_rates_path.parent == PROJECT_ROOT / "data" / "bronze"


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UPC_ROOT", str(tmp_path))
    monkeypatch.setenv("UPC_GAP_PCT", "0.05")
    monkeypatch.setenv("UPC_GAP_USD", "100")
    settings = Settings.from_env()
    assert (settings.root, settings.gap_pct_threshold, settings.gap_usd_threshold) == (
        tmp_path,
        0.05,
        100.0,
    )


def test_settings_are_immutable() -> None:
    with pytest.raises(AttributeError):
        Settings().gap_usd_threshold = 1.0  # type: ignore[misc]
