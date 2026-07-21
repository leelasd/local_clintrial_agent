import pytest
from clintrial_agent.eligibility.constraints import parse_constraints, Constraint

def test_parse_constraints_age():
    """Test age range and threshold parsing."""
    text = "Inclusion:\n- Age between 18 and 75 years\n- Patients must be aged 18 years or older"
    constraints = parse_constraints(text)
    assert len(constraints) >= 2
    variables = [c.variable for c in constraints]
    assert "age_min" in variables

def test_parse_constraints_hemoglobin_conversion():
    """Test Hemoglobin unit standardization (g/L -> g/dL)."""
    text = "Laboratory criteria:\n- Hemoglobin >= 9.0 g/dL\n- Hb >= 90 g/L"
    constraints = parse_constraints(text)
    hb_constraints = [c for c in constraints if c.variable == "hb_min"]
    assert len(hb_constraints) == 2
    # Both should be standardized to 9.0 g/dL
    assert hb_constraints[0].value == 9.0
    assert hb_constraints[1].value == 9.0
    assert hb_constraints[0].unit == "g/dL"
    assert hb_constraints[1].unit == "g/dL"

def test_parse_constraints_platelets():
    """Test Platelet count unit standardization (x10^9/L -> /mm3)."""
    text = "- Platelets >= 100 x 10^9/L\n- Platelet count >= 100,000 / uL"
    constraints = parse_constraints(text)
    plt_constraints = [c for c in constraints if c.variable == "platelets_min"]
    assert len(plt_constraints) == 2
    assert plt_constraints[0].value == 100000.0
    assert plt_constraints[1].value == 100000.0

def test_parse_constraints_ecog():
    """Test ECOG performance status parsing."""
    text = "- ECOG performance status 0 or 1\n- ECOG <= 2"
    constraints = parse_constraints(text)
    ecog_constraints = [c for c in constraints if c.variable == "ecog_max"]
    assert len(ecog_constraints) == 2
    assert ecog_constraints[0].value == 1.0
    assert ecog_constraints[1].value == 2.0
