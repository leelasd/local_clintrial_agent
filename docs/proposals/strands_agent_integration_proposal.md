# Production-Grade Redesign: Multi-Agent Clinical Trials with AWS Strands Agents

This proposal outlines how we can transform the current procedural and linear clinical trial analysis pipeline (design_agent_pipeline.py) into a production-grade, model-driven, and cooperative multi-agent system using the **AWS Strands Agents SDK**.

---

## 🚫 Limitations of the Current Pipeline

Our current pipeline is highly structured and runs smoothly, but relies on a procedural execution flow:
1.  **Linear, Non-Iterative Flow:** It runs sequentially (Endpoints -> Population -> Stats -> Safety). In real clinical operations, design is highly iterative. For example, if a trial is assessed as `Underpowered`, a human team would immediately query eligibility criteria to see what can be relaxed to boost enrollment.
2.  **Hardcoded LLM Prompts:** Classification calls are handled via procedural string manipulation in `clintrial_agent/llm/client.py` rather than letting an agent dynamically plan, execute, and verify.
3.  **No Collaborative Negotiation:** The code treats safety, statistics, and feasibility as separate silos. There is no negotiation loop where agents exchange feedback (e.g., a Safety Agent warning a Feasibility Agent about widening a patient age limit).

---

## 🤝 The Strands Multi-Agent Paradigm

The **Strands Agents SDK** enables us to model this workflow as a **Swarm of Collaborative Specialists**. Each agent has a focused system prompt, a specific toolbelt, and the ability to autonomously transfer control to another agent using the built-in `handoff_to_agent` mechanism.

```
       User [User / Caller] 
                 │
                 ▼
       Coordinator Agent ◄──────────┐
         │            │             │
         ▼ Handoff    ▼ Handoff     │ Handoff
     ┌───┴────────────┴───┐         │
     │ Protocol Extractor │         │
     │ Biostatistician   ◄┼─────────┘
     │ Safety Specialist  │
     │ Feasibility Agent  │
     └────────────────────┘
```

---

## 📋 The Agent Team & Toolbelts

We can organize our codebase as a set of specialized tools for the following Strands Agents:

| Agent Name | Role / System Prompt | Assigned Tools |
| :--- | :--- | :--- |
| **Coordinator** | Orchestrates the analysis. Accepts target NCT IDs, allocates tasks to specialists, synthesizes the final clinical report, and runs verification checks. | `search_chembl_bridge`, `design_report` |
| **Protocol Extractor** | Parses raw protocol metadata, maps treatment arms, normalizes masking levels, and extracts hierarchical clinical/surrogate endpoints. | `fetch_trial`, `query_clinical_db` |
| **Biostatistician** | Evaluates statistical power. Calculates Schoenfeld survival estimates or dispatches exact bounds to RBridge for adaptive or crossover designs. | `query_exact_stats` (Simon, gsDesign, PowerTOST) |
| **Safety Specialist** | Identifies adverse event profiles, cross-references target mechanisms in ChEMBL, and checks GWAS genetic safety associations. | `query_clinical_db` (events tables), `search_chembl_bridge` |
| **Feasibility Specialist** | Evaluates patient recruitment yields. Parses inclusion/exclusion rules, simulates cohort runs, and calculates yield multipliers under relaxation. | `simulate_eligibility_yield` |

---

## 🔗 Decoupled Architecture via Model Context Protocol (MCP)

To achieve enterprise-grade isolation, security, and scalability, Strands Agents do not import Python modules or access local databases directly. Instead, they interact with the **Clinical Trial Agent MCP Server** (`clinical_agent_mcp.py`) that we constructed in Phase 4.

This decoupled architecture provides significant advantages:
1. **Infrastructure Sandbox:** The R kernel (`rpy2`), PostgreSQL database pools, and CPU-intensive cohort simulations run inside an isolated execution environment (e.g. an ECS container or local daemon). The Strands Agents run in a serverless context (e.g. AWS Lambda) and consume them purely as stateless, stdio-connected MCP tools.
2. **Standardized Tool Contracts:** The LLM agents use the tools exactly as registered on the MCP server: `analyze_trial_design`, `simulate_eligibility_yield`, `query_exact_stats`, `search_chembl_bridge`, and `query_clinical_db`.

---

## 💻 Concrete Code Blueprint: `strands_clinical_swarm.py`

Below is a blueprint of how this multi-agent swarm is initialized, equipped with tools directly from our Phase 4 MCP server, and orchestrated:

```python
import logging
from mcp import stdio_client, StdioServerParameters
from strands import Agent
from strands.multiagent import Swarm
from strands.tools.mcp import MCPClient
from strands.models.ollama import OllamaModel
from strands.models.llamacpp import LlamaCppModel

# Enable debug logs for the multiagent swarm
logging.getLogger("strands.multiagent").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

# --- CONFIG OPTION A: Local Ollama Server ---
# ollama_model = OllamaModel(
#     host="http://localhost:11434",
#     model_id="gemma2:2b-instruct-q4_K_M"
# )

# --- CONFIG OPTION B: llama.cpp Server (Recommended for Gemma-4 8B Q8) ---
# Start server: llama-server -m ~/.cache/huggingface/hub/models--ggml-org--gemma-4-E2B-it-GUF/snapshots/a1dac71d3ab220618f5a7573a52acdc4baf3ae3b/gemma-4-E2B-it-Q8_0.gguf -c 8192 --port 8080
active_model = LlamaCppModel(
    base_url="http://localhost:8080",
    model_id="gemma-4"
)

# Initialize the stdio-based MCP Client pointing to our Phase 4 clinical MCP server
mcp_client = MCPClient(lambda: stdio_client(
    StdioServerParameters(
        command="/Users/leelasdodda/Documents/Codes/local_clintrial_agent/.venv/bin/python",
        args=["/Users/leelasdodda/Documents/Codes/local_clintrial_agent/clinical_agent_mcp.py"]
    )
))

# ==============================================================================
# INITIALIZE SPECIALIZED STRANDS AGENTS (Equipped via MCP)
# ==============================================================================
extractor_agent = Agent(
    name="protocol_extractor",
    model=active_model,
    system_prompt=(
        "You are a clinical trial data extraction expert. Your job is to fetch "
        "and clean trial metadata, intervention arms, and primary/secondary endpoints "
        "by querying the database via MCP tools."
    ),
    # Equips the agent with the MCP client (connecting on demand)
    tools=[mcp_client]
)

statistician_agent = Agent(
    name="biostatistician",
    model=active_model,
    system_prompt=(
        "You are an expert biostatistician. Your job is to perform statistical "
        "power analysis. Call the RBridge statistical solver via MCP. "
        "If a trial is underpowered, request the feasibility agent to check if "
        "any criteria can be relaxed to boost enrollment."
    ),
    tools=[mcp_client]
)

feasibility_agent = Agent(
    name="feasibility_specialist",
    model=active_model,
    system_prompt=(
        "You are a clinical trial recruitment and operations analyst. Your job "
        "is to evaluate eligibility criteria restrictiveness and run simulations "
        "to estimate cohort yields and relaxation multiplier benefits."
    ),
    tools=[mcp_client]
)

coordinator_agent = Agent(
    name="swarm_coordinator",
    model=active_model,
    system_prompt=(
        "You are the clinical trial design coordinator. You receive NCT IDs from "
        "the user, delegate protocol extraction, biostatistics power sizing, and "
        "eligibility yield simulations to the respective specialists, and synthesize "
        "the final structured comparison report."
    ),
    tools=[mcp_client]
)

# ==============================================================================
# CREATE THE COOPERATIVE SWARM & EXECUTE
# ==============================================================================
clinical_swarm = Swarm(
    [coordinator_agent, extractor_agent, statistician_agent, feasibility_agent],
    entry_point=coordinator_agent,
    max_handoffs=20,
    max_iterations=20,
    execution_timeout=900.0
)

def analyze_trial_swarm(nct_id: str) -> str:
    """Run the multi-agent analysis via the Strands swarm."""
    prompt = (
        f"Perform a comprehensive design, power, and yield analysis for trial {nct_id}. "
        "Consult the protocol extractor first, run statistical sizing, check eligibility "
        "recruitment yield, and compile a verified report."
    )
    # The swarm handles the handoffs and returns the final coordinated output
    result = clinical_swarm(prompt)
    return result.status

if __name__ == "__main__":
    status = analyze_trial_swarm("NCT00526643")
    print(f"Swarm run status: {status}")
```

---

## 📈 Why This Upgrades Us to Production-Grade

1.  **Stateful, Context-Sharing Memory:** Strands Agents manage a unified thread context. When the `biostatistician` takes over from the `protocol_extractor`, it doesn't need to re-fetch the protocol; it reads the shared conversation history.
2.  **Emergent Correction Loop (No Hardcoding):** If the LLM Coordinator notices that the biostatistician's exact calculation requires 400 patients, but the extractor reported only 50 enrolled, the LLM can dynamically decide to query the feasibility agent for relaxation recommendations without hardcoded `if/else` checks.
3.  **Observability & Guardrails:** Strands includes hooks for tool pre-execution checks, audit logs, and integration with tracking backends like Langfuse, which provides a transparent trace of how every clinical design judgment was derived.
