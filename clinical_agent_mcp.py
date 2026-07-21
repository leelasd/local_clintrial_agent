import json
import logging
import re
import sys
import contextlib
from functools import wraps
from typing import Dict, List, Any
from mcp.server.fastmcp import FastMCP

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clinical-agent-mcp")

# Initialize FastMCP server
mcp = FastMCP("clinical-trial-agent")

def redirect_stdout_to_stderr(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with contextlib.redirect_stdout(sys.stderr):
            return func(*args, **kwargs)
    return wrapper

@mcp.tool()
@redirect_stdout_to_stderr
def analyze_trial_design(nct_id: str) -> str:
    """
    Run the full multi-agent clinical trial analysis pipeline for a target NCT ID.
    Fetches the protocol details from local PostgreSQL (or API fallback),
    classifies trial designs, computes statistical power/sample sizes,
    analyzes safety/adverse events, checks pharmacogenetics (GWAS),
    and runs LLM eligibility criteria classification.
    
    Args:
        nct_id: The NCT identifier of the clinical trial (e.g. 'NCT06088043').
    """
    try:
        from design_agent_pipeline import analyze_trial
        result = analyze_trial(nct_id)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error running analyze_trial_design for {nct_id}: {e}")
        return f"Error executing pipeline for {nct_id}: {str(e)}"

@mcp.tool()
@redirect_stdout_to_stderr
def simulate_eligibility_yield(nct_id: str, cohort_size: int = 10000) -> str:
    """
    Deterministically extract numerical eligibility constraints (Age, ECOG, Hb,
    Platelets, ANC, Bilirubin, Transaminases) from a trial's criteria text
    and simulate cohort screen-to-enroll yields and relaxation scenarios.
    
    Args:
        nct_id: The NCT ID of the trial.
        cohort_size: The number of synthetic patients to generate for the simulation (default: 10000).
    """
    try:
        from clintrial_agent.data import fetch_trial
        from clintrial_agent.eligibility import parse_constraints, generate_synthetic_cohort, simulate_relaxation
        
        protocol = fetch_trial(nct_id)
        eligibility_text = protocol.get('eligibilityModule', {}).get('eligibilityCriteria', '')
        if not eligibility_text:
            return f"No eligibility criteria text found for {nct_id}."
            
        constraints = parse_constraints(eligibility_text)
        cohort_df = generate_synthetic_cohort(size=cohort_size)
        yield_results = simulate_relaxation(cohort_df, constraints)
        return json.dumps(yield_results, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error running simulate_eligibility_yield for {nct_id}: {e}")
        return f"Error running eligibility simulation for {nct_id}: {str(e)}"

# Initialize global DebounceHook for MCP tool calls
from clintrial_agent.guardrails import DebounceHook, NeurosymbolicGuardrail, MemoryPointer
global_debounce = DebounceHook(max_repeats=2)

@mcp.tool()
@redirect_stdout_to_stderr
def query_exact_stats(solver: str, params: dict) -> str:
    """
    Query the in-process RBridge statistical kernel via rpy2 for exact sequential designs,
    log-rank survival sizing, bioequivalence crossover sizing, CRM dose monitoring,
    non-proportional hazards sizing, or graphical multiplicity adjustments.
    """
    # 1. Check Debounce Guardrail to prevent tool call reasoning loops
    allowed, debounce_msg = global_debounce.check_call("query_exact_stats", {"solver": solver, "params": params})
    if not allowed:
        return debounce_msg

    try:
        from clintrial_agent.stats import RBridge
        bridge = RBridge()
        
        if solver == 'simon2stage':
            raw_pu = float(params.get('pu', 0.1))
            raw_pa = float(params.get('pa', 0.3))
            # 2. Enforce Neurosymbolic Guardrail on Simon's Two-Stage parameter ordering
            pu, pa, warning = NeurosymbolicGuardrail.validate_simon2stage_params(raw_pu, raw_pa)
            
            res = bridge.clinfun_simon2stage(
                pu=pu,
                pa=pa,
                ep1=float(params.get('ep1', 0.05)),
                ep2=float(params.get('ep2', 0.2)),
                nmax=int(params.get('nmax', 500))
            )
            if warning:
                res["neurosymbolic_guardrail_notice"] = warning
        elif solver == 'n_survival':
            res = bridge.gsdesign_fixed_survival(
                lambda1=float(params.get('lambda1', 0.0461)),
                lambda2=float(params.get('lambda2', 0.0307)),
                ratio=float(params.get('ratio', 1.0)),
                alpha=float(params.get('alpha', 0.025)),
                beta=float(params.get('beta', 0.1)),
                sided=int(params.get('sided', 1))
            )
        elif solver == 'powertost':
            res = bridge.powertost_sample_size(
                alpha=float(params.get('alpha', 0.05)),
                target_power=float(params.get('target_power', 0.8)),
                cv=float(params.get('cv', 0.2)),
                theta0=float(params.get('theta0', 0.95)),
                theta1=float(params.get('theta1', 0.8)),
                theta2=float(params.get('theta2', 1.25)),
                design=params.get('design', '2x2')
            )
        elif solver == 'group_sequential':
            res = bridge.rpact_group_sequential(
                alpha=float(params.get('alpha', 0.025)),
                beta=float(params.get('beta', 0.2)),
                sided=int(params.get('sided', 1)),
                information_rates=params.get('information_rates'),
                spending_function=params.get('spending_function', 'asOF')
            )
        elif solver == 'crm':
            res = bridge.dfcrm_crm(
                prior=params.get('prior', []),
                target=float(params.get('target', 0.25)),
                tox=params.get('tox', []),
                level=params.get('level', [])
            )
        elif solver == 'gsdesign2_nph':
            res = bridge.gsdesign2_nph_survival(
                hr=float(params.get('hr', 0.7)),
                control_median=float(params.get('control_median', 6.0)),
                test=params.get('test', 'maxcombo'),
                alpha=float(params.get('alpha', 0.025)),
                power=float(params.get('power', 0.9)),
                enrollment_rate=float(params.get('enrollment_rate', 10.0)),
                enrollment_duration=float(params.get('enrollment_duration', 12.0)),
                follow_up_duration=float(params.get('follow_up_duration', 12.0))
            )
        elif solver == 'graphical_mcp':
            res = bridge.graphical_mcp(
                num_hypotheses=int(params.get('num_hypotheses', 2)),
                alpha=float(params.get('alpha', 0.025)),
                weights=params.get('weights'),
                transition_matrix=params.get('transition_matrix'),
                p_values=params.get('p_values')
            )
        else:
            return f"Unsupported solver: '{solver}'. Choose from: 'simon2stage', 'n_survival', 'powertost', 'group_sequential', 'crm', 'gsdesign2_nph', 'graphical_mcp'."
            
        return json.dumps(res, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error running query_exact_stats for {solver}: {e}")
        return f"Error executing solver '{solver}' via RBridge: {str(e)}"

@mcp.tool()
@redirect_stdout_to_stderr
def search_chembl_bridge(nct_id: str) -> str:
    """
    Query the local PostgreSQL ChEMBL drug bridge to find compound mechanisms,
    targets, clinical indications, and approval phases linked to a trial's NCT ID.
    
    Args:
        nct_id: The NCT ID of the clinical trial.
    """
    try:
        from clintrial_agent.data.db import get_db_connection
        from psycopg2.extras import DictCursor
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Query ChEMBL clinical trial bridge table
        cur.execute(
            "SELECT DISTINCT pref_name, chembl_id, max_phase_for_ind, mesh_heading "
            "FROM bridge.chembl_clinical_trials "
            "WHERE nct_id = %s",
            (nct_id,)
        )
        trials = [dict(row) for row in cur.fetchall()]
        
        if not trials:
            # Fallback: Query interventions table and try to fuzzy match in ChEMBL dictionary
            cur.execute(
                "SELECT name FROM ctgov.interventions WHERE nct_id = %s AND intervention_type = 'DRUG'",
                (nct_id,)
            )
            interventions = [row['name'] for row in cur.fetchall()]
            if interventions:
                matched_drugs = []
                for name in interventions:
                    cur.execute(
                        "SELECT pref_name, chembl_id, max_phase, withdrawn_flag "
                        "FROM public.molecule_dictionary "
                        "WHERE pref_name ILIKE %s OR chembl_id ILIKE %s LIMIT 1",
                        (f"%{name}%", name)
                    )
                    row = cur.fetchone()
                    if row:
                        matched_drugs.append(dict(row))
                return json.dumps({
                    "nct_id": nct_id,
                    "message": "No direct FDW bridge record found. Matched by fuzzy-matching intervention drug names.",
                    "fuzzy_matches": matched_drugs
                }, indent=2)
                
            return f"No ChEMBL compounds mapped to {nct_id}."
            
        # Get mechanism information for each matched compound
        for t in trials:
            cur.execute(
                "SELECT dm.mechanism_of_action, dm.action_type, td.pref_name as target_name "
                "FROM public.drug_mechanism dm "
                "JOIN public.molecule_dictionary md ON dm.molregno = md.molregno "
                "LEFT JOIN public.target_dictionary td ON dm.tid = td.tid "
                "WHERE md.chembl_id = %s",
                (t['chembl_id'],)
            )
            t['mechanisms'] = [dict(row) for row in cur.fetchall()]
            
        cur.close()
        conn.close()
        return json.dumps(trials, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error running search_chembl_bridge for {nct_id}: {e}")
        return f"Error querying ChEMBL database for {nct_id}: {str(e)}"

@mcp.tool()
@redirect_stdout_to_stderr
def query_clinical_db(sql: str) -> str:
    """
    Execute a read-only SQL SELECT query directly against the local PostgreSQL
    database instance (containing ChEMBL 37 and AACT schema). Returns a maximum of 100 rows.
    
    Args:
        sql: A read-only SELECT query (e.g. 'SELECT count(*) FROM ctgov.studies WHERE phase = \'PHASE3\'').
    """
    sql_stripped = sql.strip().lower()
    
    # Defense-in-depth Layer 1: Regex keyword filter (soft guard)
    # NOTE: This is NOT sufficient by itself — regex is trivially bypassable.
    # The real security is Layer 2 (database-level read-only user below).
    if not sql_stripped.startswith("select"):
        return "Security Violation: Only SELECT queries are permitted."
        
    forbidden_keywords = ["insert", "update", "delete", "drop", "alter", "create", "truncate", "grant", "revoke", "replace"]
    for kw in forbidden_keywords:
        if re.search(r'\b' + kw + r'\b', sql_stripped):
            return f"Security Violation: Mutating keyword '{kw}' is prohibited."
            
    try:
        # Defense-in-depth Layer 2: Connect as clintrial_readonly (GRANT SELECT ONLY)
        # Even if a SQL injection bypasses the regex filter, the DB will reject mutations.
        from clintrial_agent.data.db import get_readonly_db_connection
        from psycopg2.extras import DictCursor
        
        conn = get_readonly_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Execute query
        cur.execute(sql)
        rows = cur.fetchall()
        
        # Convert to dicts and cap at 100
        results = [dict(row) for row in rows[:100]]
        
        cur.close()
        conn.close()
        
        response = {
            "row_count": len(results),
            "truncated": len(rows) > 100,
            "results": results
        }
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error running query_clinical_db: {e}")
        return f"Database Error: {str(e)}"

@mcp.tool()
@redirect_stdout_to_stderr
def run_cross_trial_meta_analysis(trial_data_json: str, comparison_name: str) -> str:
    """
    Performs cross-trial meta-analysis (Inverse-Variance Fixed-Effects and DerSimonian-Laird Random-Effects),
    computes heterogeneity metrics (Cochran's Q, p-value, I^2 %, tau^2), and generates a publication-grade
    Forest Plot PNG saved to the images/ directory.
    
    Args:
        trial_data_json: JSON string containing a list of trial dicts with 'nct_id', 'hr' (or 'or'), 'ci_lower', 'ci_upper', 'n_evaluable'.
                         Example: '[{"nct_id": "NCT06625320", "hr": 0.762, "ci_lower": 0.61, "ci_upper": 0.95}]'
        comparison_name: Name of the portfolio comparison (e.g. 'oncology_kras_portfolio').
    """
    try:
        from clintrial_agent.stats.meta_analysis import calculate_meta_analysis
        data = json.loads(trial_data_json)
        res = calculate_meta_analysis(data, comparison_name)
        return json.dumps(res.to_dict(), indent=2)
    except Exception as e:
        logger.error(f"Error running run_cross_trial_meta_analysis: {e}")
        return f"Error executing meta-analysis: {str(e)}"

if __name__ == "__main__":
    # Start the stdio MCP server
    mcp.run()

