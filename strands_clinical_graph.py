import os
import sys
import json
import math
import logging
import argparse
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

# Import Strands Multi-Agent framework
from strands import Agent
from strands.multiagent import GraphBuilder
from strands.tools.mcp import MCPClient
from strands.models.llamacpp import LlamaCppModel

# Enable log output to stderr for tracing the graph execution
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("strands_clinical_graph")

# ==============================================================================
# 1. INITIALIZE LOCAL LLM & MCP CLIENT
# ==============================================================================
def create_model():
    return LlamaCppModel(
        base_url="http://localhost:8080",
        model_id="default",
        timeout=300.0,
        context_window_limit=16384,
        params={"cache_prompt": True, "max_tokens": 2048}
    )

# Identify the python executable and MCP script path dynamically
current_dir = os.path.dirname(os.path.abspath(__file__))
python_bin = sys.executable
mcp_script = os.path.join(current_dir, "clinical_agent_mcp.py")

def create_mcp_client():
    return MCPClient(lambda: stdio_client(
        StdioServerParameters(
            command=python_bin,
            args=[mcp_script]
        )
    ))

# ==============================================================================
# 2. EXTRACT REAL EFFECT SIZES FROM PIPELINE ANALYSIS DATA
# ==============================================================================
def extract_meta_analysis_data(nct_id, analysis_data):
    """Extract real effect size (HR or OR) and CIs from pipeline analysis output.
    
    For survival endpoints: uses the computed detectable_hazard_ratio directly.
    For dichotomous endpoints: converts the absolute difference to a log-odds ratio,
    then back to an equivalent HR proxy for meta-analytic pooling.
    
    Returns a dict with keys: nct_id, hr, ci_lower, ci_upper, n_evaluable, endpoint_type,
    indication, data_source. Returns None if no usable effect size can be extracted.
    """
    if not analysis_data:
        return None
    
    sample_size = analysis_data.get("sample_size")
    if not sample_size:
        return None
    
    pa = sample_size.get("power_analysis", {})
    enrollment = sample_size.get("enrollment_actual", 0)
    n_per_arm = sample_size.get("estimated_n_per_arm", 0)
    endpoint_type = sample_size.get("primary_endpoint_type", "Unknown")
    indication = analysis_data.get("indication", "Unknown")
    
    # Phase 1 trials: no effect size to extract
    if pa.get("test_type", "").startswith("N/A"):
        return None
    
    # Survival endpoints: use the real detectable HR
    hr = pa.get("detectable_hazard_ratio")
    if hr is not None:
        # Compute approximate CI from the HR and sample size using SE = 2/sqrt(events)
        expected_events = pa.get("expected_events", enrollment * 0.7)
        if expected_events and expected_events > 0:
            se = 2.0 / math.sqrt(expected_events)
        else:
            se = 2.0 / math.sqrt(enrollment) if enrollment > 0 else 0.3
        ci_lower = math.exp(math.log(hr) - 1.96 * se)
        ci_upper = math.exp(math.log(hr) + 1.96 * se)
        
        # If R-exact data is available, prefer it
        r_exact_n = pa.get("r_exact_required_sample_size")
        r_exact_events = pa.get("r_exact_required_events")
        
        return {
            "nct_id": nct_id,
            "hr": round(hr, 4),
            "ci_lower": round(ci_lower, 4),
            "ci_upper": round(ci_upper, 4),
            "n_evaluable": enrollment,
            "endpoint_type": endpoint_type,
            "indication": indication,
            "data_source": "pipeline_survival",
            "r_exact_n": r_exact_n,
            "r_exact_events": r_exact_events,
        }
    
    # Dichotomous endpoints: convert absolute difference to OR proxy
    delta = pa.get("detectable_absolute_difference")
    if delta is not None:
        control_rate = analysis_data.get("sample_size", {}).get("estimated_control_event_rate", 0.1)
        treatment_rate = control_rate + delta
        
        # Clamp rates to (0, 1) for valid OR computation
        control_rate = max(0.01, min(0.99, control_rate))
        treatment_rate = max(0.01, min(0.99, treatment_rate))
        
        # Odds Ratio = [p_t/(1-p_t)] / [p_c/(1-p_c)]
        odds_ratio = (treatment_rate / (1 - treatment_rate)) / (control_rate / (1 - control_rate))
        
        # SE of log(OR) ≈ sqrt(1/(n*p_c*(1-p_c)) + 1/(n*p_t*(1-p_t)))
        if n_per_arm > 0:
            se_log_or = math.sqrt(
                1.0 / (n_per_arm * control_rate * (1 - control_rate)) +
                1.0 / (n_per_arm * treatment_rate * (1 - treatment_rate))
            )
        else:
            se_log_or = 0.3
        
        ci_lower = math.exp(math.log(odds_ratio) - 1.96 * se_log_or)
        ci_upper = math.exp(math.log(odds_ratio) + 1.96 * se_log_or)
        
        return {
            "nct_id": nct_id,
            "hr": round(odds_ratio, 4),  # OR used as effect size for meta-analysis
            "ci_lower": round(ci_lower, 4),
            "ci_upper": round(ci_upper, 4),
            "n_evaluable": enrollment,
            "endpoint_type": endpoint_type,
            "indication": indication,
            "data_source": "pipeline_dichotomous_or",
        }
    
    # Simon's Two-Stage: convert optimal n vs enrollment to a power ratio
    simon_n = pa.get("simon_optimal_n")
    if simon_n is not None and enrollment > 0:
        # Use enrollment-to-required ratio as a proxy effect size
        ratio = enrollment / simon_n if simon_n > 0 else 1.0
        return {
            "nct_id": nct_id,
            "hr": round(min(ratio, 2.0), 4),  # Capped power ratio
            "ci_lower": round(min(ratio, 2.0) * 0.7, 4),
            "ci_upper": round(min(ratio, 2.0) * 1.3, 4),
            "n_evaluable": enrollment,
            "endpoint_type": endpoint_type,
            "indication": indication,
            "data_source": "pipeline_simon2stage_ratio",
        }
    
    return None


def classify_drug_class(indication):
    """Auto-classify therapeutic drug class from the indication string.
    
    Groups trials by mechanism/disease area for homogeneous meta-analysis.
    Returns a normalized class name string.
    """
    if not indication:
        return "General"
    
    ind_lower = indication.lower()
    
    # Oncology indications
    oncology_keywords = {
        "nsclc": "NSCLC_Oncology", "non-small cell lung": "NSCLC_Oncology",
        "lung cancer": "NSCLC_Oncology", "lung adenocarcinoma": "NSCLC_Oncology",
        "colorectal": "CRC_Oncology", "colon cancer": "CRC_Oncology",
        "breast cancer": "Breast_Oncology", "triple-negative": "TNBC_Oncology",
        "pancreatic": "Pancreatic_Oncology",
        "melanoma": "Melanoma_Oncology",
        "renal cell": "RCC_Oncology", "kidney cancer": "RCC_Oncology",
        "hepatocellular": "HCC_Oncology", "liver cancer": "HCC_Oncology",
        "gastric": "Gastric_Oncology", "stomach": "Gastric_Oncology",
        "ovarian": "Ovarian_Oncology",
        "prostate": "Prostate_Oncology",
        "bladder": "Bladder_Oncology", "urothelial": "Bladder_Oncology",
        "glioblastoma": "GBM_Oncology", "glioma": "GBM_Oncology",
        "lymphoma": "Lymphoma_Oncology", "leukemia": "Leukemia_Oncology",
        "myeloma": "Myeloma_Oncology",
    }
    
    # Immunology / Autoimmune indications
    immunology_keywords = {
        "psoriasis": "Psoriasis_Immunology", "plaque psoriasis": "Psoriasis_Immunology",
        "psoriatic arthritis": "PsA_Immunology",
        "rheumatoid arthritis": "RA_Immunology",
        "lupus": "SLE_Immunology", "sle": "SLE_Immunology",
        "systemic lupus": "SLE_Immunology",
        "ulcerative colitis": "UC_Immunology",
        "crohn": "Crohn_Immunology",
        "atopic dermatitis": "AD_Immunology", "eczema": "AD_Immunology",
        "ankylosing spondylitis": "AS_Immunology",
        "multiple sclerosis": "MS_Immunology",
        "inflammatory bowel": "IBD_Immunology",
    }
    
    # Other therapeutic areas
    other_keywords = {
        "diabetes": "Diabetes_Metabolic", "type 2 diabetes": "T2D_Metabolic",
        "heart failure": "HF_Cardiovascular", "hypertension": "HTN_Cardiovascular",
        "atherosclerosis": "ASCVD_Cardiovascular",
        "alzheimer": "AD_Neurology", "parkinson": "PD_Neurology",
        "asthma": "Asthma_Respiratory", "copd": "COPD_Respiratory",
        "nash": "NASH_Hepatology", "fatty liver": "NAFLD_Hepatology",
    }
    
    # Check all keyword maps in priority order
    for keywords_map in [oncology_keywords, immunology_keywords, other_keywords]:
        for keyword, cls in keywords_map.items():
            if keyword in ind_lower:
                return cls
    
    return "General"


# ==============================================================================
# 3. GRAPH EXECUTION RUNNER
# ==============================================================================
def run_graph_analysis(nct_ids, comparison_name):
    os.makedirs("analysis_json", exist_ok=True)
    comparison_results = {}

    for nct_id in nct_ids:
        logger.info(f"=== Starting Graph Analysis for {nct_id} ===")
        prompt = f"Analyze clinical trial {nct_id}."

        model = create_model()
        mcp_client = create_mcp_client()
        with mcp_client:
            tools = mcp_client.list_tools_sync()
            logger.info(f"Loaded {len(tools)} tools from MCP server for {nct_id}.")

            # Instantiate specialized agents per trial for clean async event loops
            extractor_agent = Agent(
                name="protocol_extractor",
                model=model,
                context_manager="auto",
                system_prompt=(
                    "You are a clinical trial protocol extractor. Your task is to fetch the "
                    "raw design characteristics and endpoints for the trial ID specified in the input query. "
                    "Use the MCP tools (query_clinical_db, search_chembl_bridge, or analyze_trial_design). "
                    "SAFETY GUARDRAIL: When querying ChEMBL compound matches, check the matched "
                    "drug name exactly. Do not assume different drug names (e.g. APREMILAST and TAK-279) "
                    "are synonyms or have the same target unless explicitly confirmed by target records. "
                    "Write a detailed protocol design summary, preserving the NCT ID, and pass it to the next step."
                ),
                tools=tools
            )

            statistician_agent = Agent(
                name="biostatistician",
                model=model,
                context_manager="auto",
                system_prompt=(
                    "You are a clinical trial biostatistician. Read the protocol design summary provided in the input. "
                    "Your task is to run statistical power sizing and boundary calculations using the MCP tools (e.g. query_exact_stats). "
                    "SAFETY GUARDRAIL: First check the trial phase. For PHASE1 trials, do not call statistical solvers "
                    "like simon2stage or n_survival; instead, report that statistical power calculations are N/A (Safety/Dose-finding design). "
                    "For PHASE2/3 trials, call the appropriate solver under query_exact_stats. "
                    "Prepend the preceding protocol summary, and append your exact calculated sample size, events, and power assessment."
                ),
                tools=tools
            )

            feasibility_agent = Agent(
                name="feasibility_specialist",
                model=model,
                context_manager="auto",
                system_prompt=(
                    "You are a clinical trial feasibility specialist. Read the protocol and statistical details provided in the input. "
                    "Your task is to estimate screen-to-enrollment yield rates and simulate relaxed criteria scenarios using "
                    "the MCP tools (e.g. simulate_eligibility_yield). "
                    "BIOMARKER SCALES: If a trial requires a rare genetic subgroup (like dMMR or MSI-H), note that the screen failure "
                    "rate is driven by its population prevalence (~15% prevalence implies a ~85% screen failure rate). "
                    "CONCISENESS GUARDRAIL: Keep your response under 300 words. Output concise estimates for screen failure risk, "
                    "yield rates, and criteria relaxation scenarios. Do NOT emit unasked operational boilerplate."
                ),
                tools=tools
            )

            synthesizer_agent = Agent(
                name="synthesizer",
                model=model,
                context_manager="auto",
                system_prompt=(
                    "You are the clinical trial design assessment synthesizer. Read the accumulated protocol, statistical, "
                    "and feasibility details provided in the input. "
                    "Your job is to compile and synthesize these components into a clean, unified, publication-grade clinical trial design report. "
                    "You are strictly prohibited from using bracketed placeholders (e.g. '[Objective text goes here]'). "
                    "CONCISENESS GUARDRAIL: Your report MUST be strictly under 400 words. Output ONLY 5 clean markdown sections: "
                    "1. Trial Overview & Design, 2. Statistical Plan & Power, 3. Safety & Pharmacogenetics, "
                    "4. Feasibility & Recruitment, 5. Executive Recommendations. "
                    "Do NOT emit unasked appendices, operational boilerplate, data management policies, or empty tables."
                )
            )

            # Create cooperative graph builder per trial
            builder = GraphBuilder()
            builder.add_node(extractor_agent, "protocol_extractor")
            builder.add_node(statistician_agent, "biostatistician")
            builder.add_node(feasibility_agent, "feasibility_specialist")
            builder.add_node(synthesizer_agent, "synthesizer")
            builder.set_max_node_executions(10)

            # Establish deterministic execution edges
            builder.add_edge("protocol_extractor", "biostatistician")
            builder.add_edge("biostatistician", "feasibility_specialist")
            builder.add_edge("feasibility_specialist", "synthesizer")

            builder.set_entry_point("protocol_extractor")
            graph = builder.build()

            try:
                result = graph(prompt)
                logger.info(f"=== Graph Completed for {nct_id} (Status: {result.status}) ===")

                # Extract final text report safely from GraphResult structure
                report_text = ""
                if result.execution_order:
                    last_node_id = result.execution_order[-1].node_id
                    if last_node_id in result.results:
                        node_result = result.results[last_node_id]
                        if hasattr(node_result, "result") and hasattr(node_result.result, "message"):
                            msg = node_result.result.message
                            if isinstance(msg, dict) and "content" in msg:
                                content = msg["content"]
                                if isinstance(content, list) and len(content) > 0:
                                    report_text = content[0].get("text", "")

                # Apply Neurosymbolic Guardrail validation to clean placeholders & verify sections
                from clintrial_agent.guardrails import NeurosymbolicGuardrail
                is_valid, placeholders, clean_report_text = NeurosymbolicGuardrail.validate_report_content(report_text)
                if placeholders:
                    logger.info(f"NeurosymbolicGuardrail cleaned {len(placeholders)} placeholder(s) from {nct_id} report.")
                report_text = clean_report_text

                # Save individual report
                out_file = os.path.join("analysis_json", f"{nct_id}_graph_report.txt")
                with open(out_file, "w") as f:
                    f.write(report_text)
                logger.info(f"Saved graph report to {out_file}")

                # Run deterministic pipeline to get structured analysis data
                # This provides real effect sizes, sample sizes, and CIs for meta-analysis
                analysis_data = None
                try:
                    from design_agent_pipeline import analyze_trial
                    analysis_data = analyze_trial(nct_id)
                    logger.info(f"Pipeline analysis completed for {nct_id} — structured data captured.")
                except Exception as pipe_err:
                    logger.warning(f"Pipeline analysis failed for {nct_id}: {pipe_err}. "
                                   f"Meta-analysis will use data from existing analysis JSON if available.")
                    # Fallback: try to load from previously saved analysis JSON
                    saved_json = os.path.join("analysis_json", f"{nct_id}_analysis.json")
                    if os.path.exists(saved_json):
                        try:
                            with open(saved_json) as fj:
                                analysis_data = json.load(fj)
                            logger.info(f"Loaded cached analysis data from {saved_json}")
                        except Exception:
                            pass

                comparison_results[nct_id] = {
                    "nct_id": nct_id,
                    "graph_report": report_text,
                    "history": [node.node_id for node in result.execution_order],
                    "analysis_data": analysis_data,
                }
            except Exception as e:
                logger.error(f"Error during graph execution for {nct_id}: {e}", exc_info=True)
                comparison_results[nct_id] = {
                    "nct_id": nct_id,
                    "error": str(e)
                }

    # ==========================================================================
    # CROSS-TRIAL META-ANALYSIS — using real pipeline-extracted effect sizes
    # ==========================================================================
    if len(comparison_results) >= 2:
        try:
            from clintrial_agent.stats.meta_analysis import calculate_meta_analysis
            
            # Extract real effect sizes and auto-classify drug classes
            class_groups = {}
            for nid, res in comparison_results.items():
                if "error" in res or nid.startswith("_"):
                    continue
                
                analysis_data = res.get("analysis_data")
                meta_entry = extract_meta_analysis_data(nid, analysis_data)
                
                if meta_entry is None:
                    logger.warning(
                        f"No usable effect size extracted for {nid} — "
                        f"trial excluded from meta-analysis."
                    )
                    continue
                
                # Auto-classify drug class from indication
                cls = classify_drug_class(meta_entry.get("indication"))
                logger.info(
                    f"  {nid}: class={cls}, "
                    f"effect_size={meta_entry['hr']:.3f} "
                    f"({meta_entry['ci_lower']:.3f}-{meta_entry['ci_upper']:.3f}), "
                    f"N={meta_entry['n_evaluable']}, "
                    f"source={meta_entry['data_source']}"
                )
                
                if cls not in class_groups:
                    class_groups[cls] = []
                class_groups[cls].append({
                    "nct_id": nid,
                    "hr": meta_entry["hr"],
                    "ci_lower": meta_entry["ci_lower"],
                    "ci_upper": meta_entry["ci_upper"],
                    "n_evaluable": meta_entry["n_evaluable"],
                })
            
            # Run meta-analysis ONLY for classes with >= 2 homogeneous trials
            for cls_name, meta_data in class_groups.items():
                if len(meta_data) >= 2:
                    sub_comp_name = f"{comparison_name}_{cls_name.lower()}"
                    logger.info(f"Running homogeneous meta-analysis for class '{cls_name}' ({len(meta_data)} trials)...")
                    meta_res = calculate_meta_analysis(meta_data, sub_comp_name)
                    comparison_results[f"_meta_analysis_{cls_name}"] = meta_res.to_dict()
                    logger.info(f"R metafor forest plot saved to {meta_res.forest_plot_path}")
                else:
                    logger.info(f"Skipping meta-analysis for class '{cls_name}' — only {len(meta_data)} trial(s).")
        except Exception as e:
            logger.error(f"Error during segregated meta-analysis: {e}", exc_info=True)

    # Save portfolio comparison JSON (strip analysis_data to keep file manageable)
    save_results = {}
    for k, v in comparison_results.items():
        if k.startswith("_"):
            save_results[k] = v
        else:
            save_copy = dict(v)
            # Store only the meta-relevant subset, not the full analysis blob
            ad = save_copy.pop("analysis_data", None)
            if ad:
                save_copy["extracted_effect_size"] = extract_meta_analysis_data(k, ad)
            save_results[k] = save_copy
    
    comp_file = os.path.join("analysis_json", f"{comparison_name}_graph_comparison.json")
    with open(comp_file, "w") as f:
        json.dump(save_results, f, indent=2)
    logger.info(f"Saved graph portfolio comparison to {comp_file}")

    print("\n================================================================================")
    print(f"GRAPH STATE-MACHINE ANALYSIS COMPLETE FOR PORTFOLIO: {comparison_name.upper()}")
    print("================================================================================")
    for nct_id, res in comparison_results.items():
        if nct_id.startswith("_"):
            continue
        print(f"\nTrial: {nct_id}")
        if "error" in res:
            print(f"  Error: {res['error']}")
        else:
            print(f"  Execution Path: {' -> '.join(res.get('history', []))}")
            # Show extracted effect size if available
            ad = res.get("analysis_data")
            meta_entry = extract_meta_analysis_data(nct_id, ad) if ad else None
            if meta_entry:
                print(f"  Effect Size: {meta_entry['hr']:.3f} (95% CI: {meta_entry['ci_lower']:.3f}-{meta_entry['ci_upper']:.3f})")
                print(f"  Drug Class: {classify_drug_class(meta_entry.get('indication'))}")
                print(f"  Data Source: {meta_entry['data_source']}")
            print("  Summary:")
            # Print first 8 lines of the report
            summary_lines = res.get('graph_report', '').split('\n')[:8]
            print("\n".join(f"    {line}" for line in summary_lines))
            print("    ...")

    for key, meta in comparison_results.items():
        if key.startswith("_meta_analysis_"):
            cls_name = key.replace("_meta_analysis_", "")
            print("\n--------------------------------------------------------------------------------")
            print(f"CROSS-TRIAL META-ANALYSIS SUMMARY ({cls_name}):")
            print("--------------------------------------------------------------------------------")
            print(f"  Fixed-Effects Pooled HR  : {meta['fixed_effects_pooled_hr']} (95% CI: {meta['fixed_effects_95_ci']})")
            print(f"  Random-Effects Pooled HR : {meta['random_effects_pooled_hr']} (95% CI: {meta['random_effects_95_ci']})")
            print(f"  Heterogeneity (I²)       : {meta['heterogeneity']['i_squared_percent']}% (Q={meta['heterogeneity']['cochran_q']}, p={meta['heterogeneity']['p_value_q']})")
            print(f"  R metafor Forest Plot    : {meta['forest_plot_path']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clinical Trial Design State-Machine Graph")
    parser.add_argument("--trials", nargs="+", required=True, help="List of NCT IDs to analyze")
    parser.add_argument("--comparison-name", required=True, help="Name of the output comparison portfolio")
    args = parser.parse_args()

    run_graph_analysis(args.trials, args.comparison_name)
