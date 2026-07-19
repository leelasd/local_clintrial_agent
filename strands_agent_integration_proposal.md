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

## 💻 Concrete Code Blueprint: `strands_clinical_swarm.py`

Below is a blueprint of how this multi-agent swarm is initialized, equipped with tools from our `clintrial_agent` package, and orchestrated:

```python
from strands import Agent
from strands.multiagent import Swarm
from clintrial_agent.data import fetch_trial
from clintrial_agent.stats import RBridge
from clintrial_agent.eligibility import parse_constraints, generate_synthetic_cohort, simulate_relaxation

# ==============================================================================
# 1. DEFINE DOMAIN TOOLS
# ==============================================================================
def get_trial_protocol(nct_id: str) -> dict:
    """Fetch the full clinical trial protocol from the database."""
    return fetch_trial(nct_id)

def calculate_statistical_power(solver: str, params: dict) -> dict:
    """Run exact statistical boundary calculations using RBridge solvers."""
    bridge = RBridge()
    # Wraps our existing R exact calculations
    return bridge.query_exact_stats(solver, params)

def run_cohort_yield_simulation(nct_id: str) -> dict:
    """Simulate eligibility criteria yield and relaxation scenarios on a synthetic cohort."""
    protocol = fetch_trial(nct_id)
    criteria = protocol.get('eligibilityModule', {}).get('eligibilityCriteria', '')
    constraints = parse_constraints(criteria)
    cohort = generate_synthetic_cohort(size=10000)
    return simulate_relaxation(cohort, constraints)

# ==============================================================================
# 2. INITIALIZE SPECIALIZED STRANDS AGENTS
# ==============================================================================
extractor_agent = Agent(
    name="protocol_extractor",
    system_prompt=(
        "You are a clinical trial data extraction expert. Your job is to fetch "
        "and clean trial metadata, intervention arms, and primary/secondary endpoints."
    ),
    tools=[get_trial_protocol]
)

statistician_agent = Agent(
    name="biostatistician",
    system_prompt=(
        "You are an expert biostatistician. Your job is to perform statistical "
        "power analysis. If a trial is underpowered, request the feasibility agent "
        "to check if any criteria can be relaxed to boost enrollment."
    ),
    tools=[calculate_statistical_power]
)

feasibility_agent = Agent(
    name="feasibility_specialist",
    system_prompt=(
        "You are a clinical trial recruitment and operations analyst. Your job "
        "is to evaluate eligibility criteria restrictiveness and run simulations "
        "to estimate cohort yields and relaxation multiplier benefits."
    ),
    tools=[run_cohort_yield_simulation]
)

coordinator_agent = Agent(
    name="swarm_coordinator",
    system_prompt=(
        "You are the clinical trial design coordinator. You receive NCT IDs from "
        "the user, delegate protocol extraction, biostatistics power sizing, and "
        "eligibility yield simulations to the respective specialists, and synthesize "
        "the final structured comparison report."
    )
)

# ==============================================================================
# 3. CREATE THE COOPERATIVE SWARM
# ==============================================================================
clinical_swarm = Swarm(
    agents=[coordinator_agent, extractor_agent, statistician_agent, feasibility_agent],
    entry_point=coordinator_agent
)

def analyze_trial_swarm(nct_id: str) -> str:
    """Run the multi-agent analysis via the Strands swarm."""
    prompt = (
        f"Perform a comprehensive design, power, and yield analysis for trial {nct_id}. "
        "Consult the protocol extractor first, run statistical sizing, check eligibility "
        "recruitment yield, and compile a verified report."
    )
    # The swarm handles the handoffs and returns the final coordinated output
    return clinical_swarm(prompt)

if __name__ == "__main__":
    report = analyze_trial_swarm("NCT00526643")
    print(report)
```

---

## 📈 Why This Upgrades Us to Production-Grade

1.  **Stateful, Context-Sharing Memory:** Strands Agents manage a unified thread context. When the `biostatistician` takes over from the `protocol_extractor`, it doesn't need to re-fetch the protocol; it reads the shared conversation history.
2.  **Emergent Correction Loop (No Hardcoding):** If the LLM Coordinator notices that the biostatistician's exact calculation requires 400 patients, but the extractor reported only 50 enrolled, the LLM can dynamically decide to query the feasibility agent for relaxation recommendations without hardcoded `if/else` checks.
3.  **Observability & Guardrails:** Strands includes hooks for tool pre-execution checks, audit logs, and integration with tracking backends like Langfuse, which provides a transparent trace of how every clinical design judgment was derived.
