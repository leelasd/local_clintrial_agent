# Multi-Agent Architectures in Strands: Comparative Evaluation

For clinical trial design audits and biostatistical simulations, selecting the correct agent topology is critical. Below is a comparative assessment of the three primary architectures supported by Strands: **Cooperative Swarm**, **Sequential Workflow**, and **State-Machine Graph (DAG)**.

---

## 🗺️ Architecture Overview

```mermaid
graph TD
    subgraph 1. Cooperative Swarm (Flexible / Dynamic)
        CoordinatorSwarm[Swarm Coordinator] <--> ExtractorSwarm[Protocol Extractor]
        CoordinatorSwarm <--> StatsSwarm[Biostatistician]
        StatsSwarm <--> FeasibilitySwarm[Feasibility Specialist]
        ExtractorSwarm <--> StatsSwarm
        FeasibilitySwarm <--> CoordinatorSwarm
    end

    subgraph 2. Sequential Workflow (Linear / Rigid)
        StartWF[Input Trial] --> ExtractorWF[Protocol Extractor]
        ExtractorWF --> StatsWF[Biostatistician]
        StatsWF --> FeasibilityWF[Feasibility Specialist]
        FeasibilityWF --> SynthWF[Synthesizer / Coordinator]
    end

    subgraph 3. State-Machine DAG (Structured / Looping)
        StartDAG[NCT ID] --> ExtractorDAG[Protocol Extractor]
        ExtractorDAG --> PhaseCheck{Check Phase?}
        PhaseCheck -- Phase 1 --> FeasibilityDAG[Feasibility Specialist]
        PhaseCheck -- Phase 2/3 --> StatsDAG[Biostatistician]
        StatsDAG --> PowerCheck{Underpowered?}
        PowerCheck -- Yes --> FeasibilityRelax[Feasibility Specialist: Criteria Relaxation]
        FeasibilityRelax --> StatsDAG
        PowerCheck -- No --> FeasibilityDAG
        FeasibilityDAG --> SynthDAG[Coordinator Synthesis]
    end
```

---

## 📊 Comparative Analysis Matrix

| Feature | 🤖 Cooperative Swarm (Current) | ⛓️ Sequential Workflow | 🕸️ State-Machine Graph (DAG) |
| :--- | :--- | :--- | :--- |
| **Execution Pattern** | Autonomous peer handoffs (`handoff_to_agent`). | Linear, deterministic chain. | Structured transition loops based on state/variables. |
| **Flexibility** | **Very High** (Agents choose when and who to message). | **Low** (Fixed path, no loops or feedback). | **Balanced** (Paths are pre-defined but support looping/conditions). |
| **Reliability / Auditability** | **Medium-Low** (LLM routing can skip steps or terminate early). | **High** (Deterministic, step-by-step execution guaranteed). | **Very High** (Transitions are enforced programmatically). |
| **Iterative Loops** | Possible but hard to control (risk of infinite loops/ping-ponging). | Impossible. | **Robust** (Deterministic criteria relaxation loop). |
| **Complexity** | Simple setup (Define list of agents and let them self-route). | Very simple. | Moderate (Requires defining nodes, states, and condition routers). |

---

## 🏛️ Critique of Current Swarm Architecture

The current implementation in [`strands_clinical_swarm.py`](file:///Users/leelasdodda/Documents/Codes/local_clintrial_agent/strands_clinical_swarm.py) is a **Cooperative Swarm**. 

### **Limitations in the Swarm Pattern:**
1.  **Non-Deterministic Routing:** The LLM coordinator has to decide who to hand off to. In the first run, it skipped the biostatistician entirely for `NCT06625320` and went straight from feasibility to extractor, concluding the run without sizing calculations.
2.  **State Contamination:** Because all agents share a single flat conversation thread context, context window usage grows quickly, and instructions can get mixed up (e.g. the biostatistician attempting to run Simon's 2-stage on a Phase 1 study because of instructions in a previous turn).
3.  **Vulnerability to Hallucinated Failures:** If a tool fails (such as our RBridge multithreading context error), the agents spent multiple handoffs reporting the failure to each other rather than falling back programmatically.

---

## 🏆 Recommendation: State-Machine Graph (DAG) for Production

For a production-grade clinical trial design auditor, the **State-Machine Graph** is the gold-standard architecture. 

### **Why Graphs are Best for Clinical/Bio-Pharma Audits:**
1.  **Enforced Quality Checklists:** You can programmatically guarantee that the `Protocol Extractor` is run first, followed by the `Biostatistician`, and then the `Feasibility Specialist`. No specialist can be bypassed.
2.  **Intellectual Division of Labor:** You can clear/filter context variables when entering nodes, keeping the Biostatistician's context clean of raw HTML/text protocol logs, which minimizes model hallucinations and context tokens.
3.  **Scientific Optimization Loops:** A graph enables a clean, programmable optimization loop:
    *   *Step 1:* Extractor parses trial details.
    *   *Step 2:* Statistician calculates power based on current cohort sizes (e.g., Power = 68%).
    *   *Step 3:* Feasibility Specialist simulates screen-to-enrollment yields.
    *   *Step 4 (Loop Router):* If Power < 80%, transition to Feasibility Specialist to simulate *relaxed* criteria (e.g. ECOG $\le$ 2 instead of $\le$ 1). Pass relaxed enrollment estimate back to the Statistician to recalculate power.
    *   *Step 5:* Terminate only once Power $\ge$ 80% or relaxation bounds are exhausted.
