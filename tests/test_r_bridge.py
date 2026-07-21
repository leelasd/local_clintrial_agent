import pytest
from clintrial_agent.stats.r_bridge import RBridge, _sanitize_id

def test_sanitize_id_valid():
    """Verify valid parameter strings pass through _sanitize_id."""
    assert _sanitize_id("asOF", "spending_function") == "asOF"
    assert _sanitize_id("sfLDOF", "spending_upper") == "sfLDOF"
    assert _sanitize_id("2x2", "design") == "2x2"
    assert _sanitize_id("PHASE2", "phase") == "PHASE2"

def test_sanitize_id_injection_attempt():
    """Verify malicious R injection strings raise ValueError."""
    with pytest.raises(ValueError, match="Invalid characters"):
        _sanitize_id('asOF"; system("rm -rf /"); "', "spending_function")

    with pytest.raises(ValueError, match="Invalid characters"):
        _sanitize_id("2x2; print('hacked')", "design")

def test_rbridge_simon2stage():
    """Test RBridge Simon 2-stage solver execution."""
    bridge = RBridge()
    res = bridge.clinfun_simon2stage(pu=0.10, pa=0.30, ep1=0.05, ep2=0.20)
    assert "optimal" in res
    assert "minimax" in res
    assert res["optimal"]["n"] > 0
    assert res["minimax"]["n"] > 0

def test_rbridge_powertost():
    """Test RBridge Bioequivalence TOST sample size solver."""
    bridge = RBridge()
    res = bridge.powertost_sample_size(alpha=0.05, target_power=0.8, cv=0.2)
    assert "sample_size" in res
    assert res["sample_size"] > 0
    assert res["achieved_power"] >= 0.8
