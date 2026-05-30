from __future__ import annotations

from pathlib import Path

import pytest


def test_calibrated_mask_used_in_low_memory_mode(monkeypatch):
    monkeypatch.setenv("HVAC_LOW_MEMORY_MODE", "true")
    from importlib import reload

    import app.core.config as config_mod
    import app.processing.pipeline as pipeline_mod

    reload(config_mod)
    reload(pipeline_mod)

    assert config_mod.settings.low_memory_mode is True
    assert config_mod.settings.demo_mode is True

    repo_root = Path(__file__).resolve().parents[2]
    expected = repo_root / "Sample annotation.png"
    if not expected.is_file():
        pytest.skip("Sample annotation.png not present")

    monkeypatch.setattr(
        pipeline_mod.settings,
        "expected_annotation_png",
        expected,
    )
    monkeypatch.setattr(pipeline_mod.settings, "refine_expected_png_target_page", 1)

    assert pipeline_mod._should_use_calibrated_mask(0) is True
    assert pipeline_mod._should_use_calibrated_mask(1) is False

    monkeypatch.delenv("HVAC_LOW_MEMORY_MODE", raising=False)
    reload(config_mod)
    reload(pipeline_mod)
