import argparse
import json
import logging
import os
import sys
from mcp import stdio_client, StdioServerParameters
from strands import Agent
from strands.multiagent import Swarm
from strands.tools.mcp import MCPClient
from strands.models.llamacpp import LlamaCppModel

# Enable log output to stderr for tracing the agent coordination
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("strands_clinical_swarm")

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
# 2. EXECUTION RUNNER
# ==============================================================================
def run_swarm_analysis(nct_ids, comparison_name):
    os.makedirs("analysis_json", exist_ok=True)
    comparison_results = {}

    for nct_id in nct_ids:
        logger.info(f"=== Starting Swarm Analysis for {nct_id} ===")
        prompt = (
            f"Analyze trial {nct_id}. Handoff to the extractor to get protocol details, "
            "then to the biostatistician for power calculations, and finally to the "
            "feasibility specialist for recruitment yield and criteria simulation. "
            "Synthesize everything into a clean final report."
        )

        model = create_model()
        mcp_client = create_mcp_client()
        with mcp_client:
            tools = mcp_client.list_tools_sync()
            logger.info(f"Loaded {len(tools)} tools from MCP server for {nct_id}.")

            extractor_agent = Agent(
                name="protocol_extractor",
                model=model,
                system_prompt=(
                    "You are a clinical trial protocol extractor. Your task is to fetch the "
                    "raw design characteristics and endpoints for a study using the MCP tools "
                    "(query_clinical_db, search_chembl_bridge, or analyze_trial_design). "
                    "SAFETY GUARDRAIL: When querying ChEMBL compound matches, check the matched "
                    "drug name exactly. Do not assume different drug names (e.g. APREMILAST and TAK-279) "
                    "are synonyms or have the same mechanism unless explicitly confirmed by target records. "
                    "Output the concrete design details (no placeholders) and hand off to the biostatistician."
                ),
                tools=tools
            )

            statistician_agent = Agent(
                name="biostatistician",
                model=model,
                system_prompt=(
                    "You are a clinical trial biostatistician. Your task is to run statistical power "
                    "sizing and boundary calculations using the MCP tools (e.g., query_exact_stats). "
                    "SAFETY GUARDRAIL: First check the trial phase. For PHASE1 trials, do not call "
                    "statistical solvers like simon2stage or n_survival; instead, report that "
                    "statistical power calculations are N/A (Safety/Dose-finding design). For PHASE2/3 "
                    "trials, use the appropriate solver under query_exact_stats. "
                    "Report the exact calculated sample size, events, and power assessment, and hand off "
                    "to the feasibility specialist."
                ),
                tools=tools
            )

            feasibility_agent = Agent(
                name="feasibility_specialist",
                model=model,
                system_prompt=(
                    "You are a clinical trial feasibility specialist. Your task is to estimate "
                    "screen-to-enrollment yield rates and simulate relaxed criteria scenarios using "
                    "the MCP tools (e.g. simulate_eligibility_yield). "
                    "BIOMARKER SCALES: If a trial requires a rare genetic subgroup (like dMMR or MSI-H), "
                    "note that the screen failure rate is driven by its population prevalence (~15% prevalence "
                    "implies a ~85% screen failure rate). Report the baseline yield and relaxation "
                    "scenarios, then hand off back to the swarm coordinator."
                ),
                tools=tools
            )

            coordinator_agent = Agent(
                name="swarm_coordinator",
                model=model,
                system_prompt=(
                    "You are the clinical trial design swarm coordinator. Your job is to orchestrate "
                    "an analysis of an NCT ID. You MUST follow this sequential path: "
                    "1. Hand off to protocol_extractor to gather raw data and check drug structures. "
                    "2. Hand off to biostatistician to run power calculations. "
                    "3. Hand off to feasibility_specialist to run yield simulations. "
                    "You are strictly prohibited from compiling the report until ALL three specialists "
                    "have completed their tasks and returned concrete data. Do not include any bracketed "
                    "placeholder text (e.g. '[Objective text goes here]'). Synthesize their findings "
                    "into a clean, unified trial design assessment."
                ),
                tools=tools
            )

            swarm = Swarm(
                [coordinator_agent, extractor_agent, statistician_agent, feasibility_agent],
                entry_point=coordinator_agent,
                max_handoffs=10,
                max_iterations=15,
                execution_timeout=300.0
            )

            try:
                result = swarm(prompt)
                logger.info(f"=== Swarm Completed for {nct_id} (Status: {result.status}) ===")

                # Extract final text report safely from SwarmResult structure
                report_text = ""
                if result.node_history:
                    last_node_id = result.node_history[-1].node_id
                    if last_node_id in result.results:
                        node_result = result.results[last_node_id]
                        if hasattr(node_result, "result") and hasattr(node_result.result, "message"):
                            msg = node_result.result.message
                            if isinstance(msg, dict) and "content" in msg:
                                content = msg["content"]
                                if isinstance(content, list) and len(content) > 0:
                                    report_text = content[0].get("text", "")

                # Fallback if content extraction returned empty
                if not report_text:
                    report_text = f"Swarm completed with status {result.status} but returned no text. Node history: {[n.node_id for n in result.node_history]}"
                
                # Save individual report
                out_file = os.path.join("analysis_json", f"{nct_id}_swarm_report.txt")
                with open(out_file, "w") as f:
                    f.write(report_text)
                logger.info(f"Saved swarm report to {out_file}")

                comparison_results[nct_id] = {
                    "nct_id": nct_id,
                    "swarm_report": report_text,
                    "history": [node.node_id for node in result.node_history]
                }
            except Exception as e:
                logger.error(f"Error during swarm execution for {nct_id}: {e}", exc_info=True)
                comparison_results[nct_id] = {
                    "nct_id": nct_id,
                    "error": str(e)
                }

    # Save portfolio comparison JSON
    comp_file = os.path.join("analysis_json", f"{comparison_name}_swarm_comparison.json")
    with open(comp_file, "w") as f:
        json.dump(comparison_results, f, indent=2)
    logger.info(f"Saved swarm portfolio comparison to {comp_file}")

    print("\n================================================================================")
    print(f"SWARM ANALYSIS COMPLETE FOR PORTFOLIO: {comparison_name.upper()}")
    print("================================================================================")
    for nct_id, res in comparison_results.items():
        print(f"\nTrial: {nct_id}")
        if "error" in res:
            print(f"  Error: {res['error']}")
        else:
            print(f"  Handoff Path: {' -> '.join(res['history'])}")
            print("  Summary:")
            # Print first 8 lines of the report
            summary_lines = res['swarm_report'].split('\n')[:8]
            print("\n".join(f"    {line}" for line in summary_lines))
            print("    ...")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clinical Trial Design Multi-Agent Swarm")
    parser.add_argument("--trials", nargs="+", required=True, help="List of NCT IDs to analyze")
    parser.add_argument("--comparison-name", required=True, help="Name of the output comparison portfolio")
    args = parser.parse_args()

    run_swarm_analysis(args.trials, args.comparison_name)
