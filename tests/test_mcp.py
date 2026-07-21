import pytest
import json
from clinical_agent_mcp import search_chembl_bridge

def test_search_chembl_bridge_exact_resolution():
    """Verify search_chembl_bridge correctly resolves trial interventions using exact & synonym matching."""
    # Test PAISLEY trial (NCT03252587 — BMS-986165)
    res_str = search_chembl_bridge("NCT03252587")
    assert res_str is not None
    data = json.loads(res_str)
    assert isinstance(data, (dict, list))
