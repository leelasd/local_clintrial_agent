import pytest
from clintrial_agent.config import CONFIG, INDICATION_PARAMS, DEFAULT_INDICATION_PARAMS, load_config

def test_config_keys_present():
    """Verify core configuration keys exist."""
    assert "alpha" in CONFIG
    assert "power_target" in CONFIG
    assert "calculation_mode" in CONFIG
    assert CONFIG["alpha"] == 0.05
    assert CONFIG["power_target"] == 0.80

def test_default_indication_params():
    """Verify default indication parameters structure."""
    assert "control_rate_dichotomous" in DEFAULT_INDICATION_PARAMS
    assert "event_rate" in DEFAULT_INDICATION_PARAMS
    assert DEFAULT_INDICATION_PARAMS["control_rate_dichotomous"] == 0.10

def test_load_config_fallback(tmp_path):
    """Verify load_config falls back gracefully when file does not exist."""
    cfg = load_config(config_path=tmp_path / "nonexistent.yaml")
    assert cfg["alpha"] == 0.05
    assert cfg["power_target"] == 0.80
