import sys
import json
import logging
from clintrial_agent.data import fetch_trial
from clintrial_agent.stats import analyze_sample_size
from clintrial_agent.eligibility import parse_constraints, generate_synthetic_cohort, simulate_relaxation
from clinical_agent_mcp import analyze_trial_design, simulate_eligibility_yield, query_exact_stats, search_chembl_bridge, query_clinical_db

# Suppress debug logs during test run
logging.getLogger("clintrial_agent").setLevel(logging.WARNING)
logging.getLogger("clinical-agent-mcp").setLevel(logging.WARNING)

def run_tests():
    print("=" * 80)
    print("RUNNING PIPELINE INTEGRATION & VALIDATION CHECKS")
    print("=" * 80)
    
    # Test 1: Local DB Fetching
    print("\n[Test 1] Testing local AACT PostgreSQL DB fetching...")
    nct_id = "NCT00526643"
    try:
        protocol = fetch_trial(nct_id)
        title = protocol['identificationModule']['briefTitle']
        print(f"  ✓ Success! Fetched {nct_id}: '{title[:50]}...'")
    except Exception as e:
        print(f"  ✗ Failed Test 1: {e}")
        return False
        
    # Test 2: Eligibility Parser & Yield Simulation
    print("\n[Test 2] Testing eligibility constraint parser and yield simulation...")
    try:
        eligibility_text = protocol['eligibilityModule']['eligibilityCriteria']
        constraints = parse_constraints(eligibility_text)
        print(f"  ✓ Parsed {len(constraints)} numeric constraints:")
        for c in constraints:
            print(f"    • {c.variable} {c.operator} {c.value}")
        cohort_df = generate_synthetic_cohort(size=1000)
        yield_res = simulate_relaxation(cohort_df, constraints)
        print(f"  ✓ Baseline screen yield: {yield_res['baseline_yield']:.1%}")
        print(f"  ✓ Scenarios simulated: {len(yield_res['relaxations'])}")
    except Exception as e:
        print(f"  ✗ Failed Test 2: {e}")
        return False

    # Test 3: RBridge Exact Calculations (R-exact)
    print("\n[Test 3] Testing RBridge exact survival calculations...")
    try:
        # Enable R-exact mode programmatically
        from clintrial_agent.config import CONFIG
        CONFIG['calculation_mode'] = 'R-exact'
        
        endpoints = [
            {'text': 'overall survival', 'endpoint_type': 'Clinical', 'timeframe': '1 year', 'is_primary': True}
        ]
        sample_size = analyze_sample_size(protocol, endpoints, indication_params={'median_os_months': 12.0, 'event_rate': 0.80})
        pa = sample_size['power_analysis']
        print(f"  ✓ R-exact sample size calculated: {pa.get('r_exact_required_sample_size')}")
        print(f"  ✓ R-exact events calculated: {pa.get('r_exact_required_events')}")
    except Exception as e:
        print(f"  ✗ Failed Test 3: {e}")
        return False

    # Test 4: MCP Tool Invocation & Security Guardrails
    print("\n[Test 4] Testing MCP tool interfaces...")
    try:
        # Test search_chembl_bridge
        chembl_res = search_chembl_bridge(nct_id)
        print(f"  ✓ ChEMBL tool success (response length: {len(chembl_res)} characters)")
        
        # Test query_exact_stats for gsdesign2_nph and graphical_mcp
        nph_res = query_exact_stats("gsdesign2_nph", {"hr": 0.7, "control_median": 6.0})
        nph_dict = json.loads(nph_res)
        print(f"  ✓ RBridge gsDesign2 NPH success (Sample Size: {nph_dict['n']:.1f}, Events: {nph_dict['events']:.1f})")
        
        mcp_res = query_exact_stats("graphical_mcp", {"p_values": [0.01, 0.03]})
        mcp_dict = json.loads(mcp_res)
        print(f"  ✓ RBridge graphicalMCP success (H1 Rejected: {mcp_dict['rejected']['H1']}, H2 Rejected: {mcp_dict['rejected']['H2']})")
        
        # Test query_clinical_db (read-only verification)
        sql_res = query_clinical_db("SELECT count(*) FROM ctgov.studies WHERE phase = 'PHASE3'")
        res_dict = json.loads(sql_res)
        print(f"  ✓ SQL Tool success! Total Phase 3 trials in DB: {res_dict['results'][0]['count']}")
        
        # Test query_clinical_db mutation check
        security_res = query_clinical_db("DROP TABLE ctgov.studies")
        if "Security Violation" in security_res:
            print("  ✓ SQL Tool security guardrail active (blocked DROP query).")
        else:
            print("  ✗ SQL Tool security guardrail failed!")
            return False
    except Exception as e:
        print(f"  ✗ Failed Test 4: {e}")
        return False

    print("\n" + "=" * 80)
    print("ALL PIPELINE MODIFICATIONS ARE WORKING SMOOTHLY!")
    print("=" * 80)
    return True

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
