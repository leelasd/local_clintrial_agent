import pytest
from strands_clinical_graph import extract_meta_analysis_data, classify_drug_class

def test_classify_drug_class():
    """Verify therapeutic drug class auto-classification logic."""
    assert classify_drug_class("non-small cell lung cancer") == "NSCLC_Oncology"
    assert classify_drug_class("Plaque Psoriasis") == "Psoriasis_Immunology"
    assert classify_drug_class("Systemic Lupus Erythematosus") == "SLE_Immunology"
    assert classify_drug_class("Psoriatic Arthritis") == "PsA_Immunology"
    assert classify_drug_class("Type 2 Diabetes") == "T2D_Metabolic"
    assert classify_drug_class(None) == "General"
    assert classify_drug_class("Unknown Rare Condition") == "General"

def test_extract_meta_analysis_data_survival():
    """Verify survival endpoint HR extraction."""
    mock_analysis = {
        "indication": "non-small cell lung cancer",
        "sample_size": {
            "enrollment_actual": 345,
            "estimated_n_per_arm": 172,
            "primary_endpoint_type": "OS (Overall Survival)",
            "power_analysis": {
                "test_type": "Two-sided (log-rank)",
                "detectable_hazard_ratio": 0.714,
                "expected_events": 240,
                "power_target": 0.8
            }
        }
    }
    extracted = extract_meta_analysis_data("NCT04303780", mock_analysis)
    assert extracted is not None
    assert extracted["nct_id"] == "NCT04303780"
    assert extracted["hr"] == 0.714
    assert extracted["ci_lower"] < 0.714
    assert extracted["ci_upper"] > 0.714
    assert extracted["data_source"] == "pipeline_survival"

def test_extract_meta_analysis_data_dichotomous():
    """Verify dichotomous endpoint Odds Ratio conversion."""
    mock_analysis = {
        "indication": "plaque psoriasis",
        "sample_size": {
            "enrollment_actual": 693,
            "estimated_n_per_arm": 231,
            "estimated_control_event_rate": 0.10,
            "primary_endpoint_type": "Dichotomous (Proportion)",
            "power_analysis": {
                "test_type": "Two-sided",
                "detectable_absolute_difference": 0.10,
                "power_target": 0.8
            }
        }
    }
    extracted = extract_meta_analysis_data("NCT06088043", mock_analysis)
    assert extracted is not None
    assert extracted["nct_id"] == "NCT06088043"
    assert extracted["hr"] > 1.0  # Converted OR should be > 1 for positive delta
    assert extracted["data_source"] == "pipeline_dichotomous_or"

def test_extract_meta_analysis_data_phase1_excluded():
    """Verify Phase 1 trials are excluded from meta-analysis extraction."""
    mock_analysis = {
        "indication": "solid tumors",
        "sample_size": {
            "enrollment_actual": 30,
            "estimated_n_per_arm": 30,
            "primary_endpoint_type": "Safety / Dose-Finding",
            "power_analysis": {
                "test_type": "N/A (Phase 1 dose-escalation)"
            }
        }
    }
    extracted = extract_meta_analysis_data("NCT03634982", mock_analysis)
    assert extracted is None
