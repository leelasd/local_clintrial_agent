# Clinical Trial Analysis Agent

An automated, local-first clinical trial analysis and audit system powered by **AWS Strands Agents SDK**, **FastMCP**, local **PostgreSQL (AACT + ChEMBL 37)**, and an **rpy2 R Statistical Kernel**. Protocol classifications are guided by **Friedman, Furberg & DeMets, *Fundamentals of Clinical Trials* (4th ed.)**.

---

## 🏗️ Architecture Overview

```mermaid
flowchart TD
    subgraph Orchestration Layer (Strands Framework)
        Graph[strands_clinical_graph.py - 4-Node DAG]
        Swarm[strands_clinical_swarm.py - Swarm Orchestrator]
    end

    subgraph Specialized Agents (Multi-Agent DAG / Swarm)
        PE[1. Protocol Extractor Agent]
        BS[2. Biostatistician Agent]
        FS[3. Feasibility Specialist Agent]
        SY[4. Synthesizer Agent]
    end

    subgraph Local Open-Weight LLM Backend
        LlamaServer[llama-server :8080\nGemma-4 Q8 - Apple Silicon Metal GPU]
    end

    subgraph FastMCP Gateway (clinical_agent_mcp.py)
        MCPStdio[FastMCP Stdio Server JSON-RPC]
        Tool1[analyze_trial_design]
        Tool2[simulate_eligibility_yield]
        Tool3[query_exact_stats]
        Tool4[search_chembl_bridge]
        Tool5[query_clinical_db]
        Tool6[run_cross_trial_meta_analysis]
    end

    subgraph Data & Statistical Kernels
        DB[(Local PostgreSQL chembl_37\nAACT ctgov.* + ChEMBL public.*)]
        RBridge[rpy2 RBridge ABI Mode]
        REngine[R Engine 4.6.1\nrpact / gsDesign / clinfun / metafor]
    end

    Graph --> PE --> BS --> FS --> SY
    PE & BS & FS & SY <-->|HTTP /v1/chat/completions| LlamaServer
    PE & BS & FS <-->|Stdio Transport| MCPStdio
    MCPStdio --> Tool1 & Tool2 & Tool3 & Tool4 & Tool5 & Tool6
    Tool1 & Tool5 & Tool4 --> DB
    Tool3 & Tool6 --> RBridge --> REngine
```

---

## 🌟 Core Features

1. **🕸️ Deterministic State-Machine Graph (`strands_clinical_graph.py`):**
   * Executes a strict 4-stage DAG pipeline: `protocol_extractor` $\rightarrow$ `biostatistician` $\rightarrow$ `feasibility_specialist` $\rightarrow$ `synthesizer`.
   * **State-channel isolation** prevents context window bloat, keeping prompts focused per node.

2. **🔌 FastMCP Stdio Tool Server (`clinical_agent_mcp.py`):**
   * Exposes 6 tools over stdio (`analyze_trial_design`, `simulate_eligibility_yield`, `query_exact_stats`, `search_chembl_bridge`, `query_clinical_db`, `run_cross_trial_meta_analysis`).
   * Wrapped with `@redirect_stdout_to_stderr` to guarantee zero stdio stream corruption over JSON-RPC.

3. **📊 RBridge Statistical Kernel (`clintrial_agent/stats/r_bridge.py`):**
   * Direct `rpy2` bindings for textbook-standard statistical packages:
     * `gsDesign` & `gsDesign2`: Fixed-sample and non-proportional hazards log-rank boundary calculations.
     * `rpact`: Group-sequential designs & alpha spending functions.
     * `clinfun`: Simon's optimal/minimax Phase II 2-stage designs.
     * `PowerTOST`: Bioequivalence and crossover trial power.
     * `dfcrm`: Continual Reassessment Method (CRM) for Phase 1 dose-finding.
     * `metafor`: Fixed and random-effects cross-trial meta-analyses and publication-grade forest plots.
     * `graphicalMCP`: Maurer-Bretz multi-endpoint alpha recycling.

4. **🗄️ Local PostgreSQL Database Integration:**
   * Direct queries against local AACT tables and ChEMBL 37 drug target mapping bridges with automatic ClinicalTrials.gov API fallback.

5. **🧮 Synthetic Cohort & Eligibility Yield Simulator (`clintrial_agent/eligibility/`):**
   * Deterministic criteria constraint parser generating $N=10,000$ synthetic patient populations to simulate screen-to-enrollment yields and criteria relaxation multipliers.

6. **⚡ GPU-Accelerated Open-Weight LLM (`llama-server`):**
   * Powered by `llama-server` running `gemma-4-E2B-it-Q8_0.gguf` on port 8080 with **Metal GPU offloading (`-ngl 99`)**, delivering sub-second token generation latency ($0.87\text{s}$).

---

## 🛠️ Critical Gotchas & Solved Patterns

### 1. **Threaded RBridge Conversion Context Exception**
* **Issue:** `Error executing solver 'simon2stage' via RBridge: Conversion rules for rpy2.robjects appear to be missing...`
* **Cause:** `rpy2` tracks conversion rules via `contextvars.ContextVar`, which does not automatically propagate to worker threads in FastMCP stdio server loops.
* **Fix:** All R code executions and package loads inside `clintrial_agent/stats/r_bridge.py` are wrapped inside the explicit `localconverter(ro.default_converter)` context manager:
  ```python
  from rpy2.robjects.conversion import localconverter
  with localconverter(ro.default_converter):
      self._loaded_packages[pkg_name] = importr(pkg_name, on_conflict="warn")
  ```

---

### 2. **Per-Trial Event Loop & Session Isolation**
* **Issue:** `Trial 2: Error: Event loop is closed`
* **Cause:** In the Strands framework, `LlamaCppModel` (holding an `httpx.AsyncClient`) and `MCPClient` bind internal async session states. Completing `asyncio.run()` on Trial 1 closed their event loop before Trial 2 could execute.
* **Fix:** Factory functions `create_model()` and `create_mcp_client()` are called **inside the `for nct_id in nct_ids:` loop** in both `strands_clinical_graph.py` and `strands_clinical_swarm.py`:
  ```python
  for nct_id in nct_ids:
      model = create_model()
      mcp_client = create_mcp_client()
      with mcp_client:
          tools = mcp_client.list_tools_sync()
          extractor_agent = Agent(model=model, tools=tools, context_manager="auto", ...)
          # Execute graph with fresh event loop, HTTP client, and stdio transport per trial
  ```

---

### 3. **Simon's Two-Stage Parameter & Boundary Constraints**
* **Issue:** `R error: Error in ph2simon(pu = 0.2, pa = 0.05, ep1 = 0.01, ep2 = 0.01) : No feasible solution found. Current nmax value = 100.`
* **Cause:**
  1. `ph2simon` requires baseline response rate $p_0$ (`pu`) to be strictly less than target rate $p_1$ (`pa`).
  2. Under strict error bounds ($\alpha=0.01, \beta=0.01$), required sample size ($N=113$) exceeds R's default ceiling (`nmax=100`).
* **Fix:** `clinfun_simon2stage()` in `r_bridge.py` automatically checks and orders $pu < pa$, and sets `nmax = 500` by default.

---

### 4. **Token Context Window & Response Limits**
* **Issue:** `MaxTokensReachedException` or `context_window_limit not set on model`
* **Fix:**
  1. `create_model()` passes `context_window_limit=16384` and `params={"cache_prompt": True, "max_tokens": 2048}`.
  2. `Agent(...)` sets `context_manager="auto"` to automatically offload and summarize large tool payload responses.

---

## 🏃 Execution & Quickstart

### Step 1: Start GPU-Accelerated `llama-server` (Gemma 4 Q8)
In a dedicated terminal, launch `llama-server` on port 8080 with Metal GPU offloading (`-ngl 99`):
```bash
/opt/homebrew/bin/llama-server \
  -m ~/.cache/huggingface/hub/models--ggml-org--gemma-4-E2B-it-GGUF/snapshots/a1dac71d3ab220618f5a7573a52acdc4baf3ae3b/gemma-4-E2B-it-Q8_0.gguf \
  -c 16384 --port 8080 -ngl 99
```

### Step 2: Run Multi-Agent State-Machine Graph
Run the full 4-stage multi-agent graph pipeline across target trials:
```bash
uv run python strands_clinical_graph.py \
  --trials NCT03252587 NCT05617677 NCT05620407 \
  --comparison-name sle_tyk2_portfolio
```

### Step 3: Run Multi-Agent Swarm Orchestrator (Reference Example)
Run the cooperative Swarm orchestrator with dynamic handoffs:
```bash
uv run python examples/strands_clinical_swarm.py \
  --trials NCT03252587 NCT05617677 NCT05620407 \
  --comparison-name sle_tyk2_swarm
```

### Step 4: Run FastMCP Server Gateway
Inspect or execute FastMCP tools directly:
```bash
uv run clinical_agent_mcp.py
```

### Step 5: Run Self-Testing Integration Suite
Verify PostgreSQL database connections, RBridge solvers, and SQL security guardrails:
```bash
uv run python validate_pipeline.py
```

---

## 📂 Output Directory Reference

* `analysis_json/{NCT_ID}_analysis.json` — Detailed per-trial statistical, design, and feasibility JSON output.
* `analysis_json/{NCT_ID}_graph_report.txt` — Individual publication-grade multi-agent assessment reports.
* `analysis_json/{comparison_name}_graph_comparison.json` — Structured portfolio-level multi-trial comparisons.
* `images/forest_plot_{comparison_name}_{class}.png` — R `metafor` cross-trial forest plots.
* `images/power_curves.png` — Power curve PNG visualizations generated by `power_visualization.py`.

---

## 📚 Technical Documentation Index (`docs/`)

* **📊 Reports:**
  * [`docs/reports/sle_clinical_trial_landscape_case.md`](docs/reports/sle_clinical_trial_landscape_case.md) — Strategic case report on contemporary Systemic Lupus Erythematosus (SLE) trial landscape & Afimetoran-based protocol specification.
* **⚡ Benchmarks:**
  * [`docs/benchmarks/MODEL_BENCHMARK.md`](docs/benchmarks/MODEL_BENCHMARK.md) — Benchmark comparison of Gemma 4 Q8 vs Qwythos 9B local LLM backends.
* **🕸️ Architecture:**
  * [`docs/architecture/strands_architectures_comparison.md`](docs/architecture/strands_architectures_comparison.md) — Comparative topology analysis (State-Machine DAG vs Swarm).
  * [`docs/architecture/cran_task_view_mapping.md`](docs/architecture/cran_task_view_mapping.md) — R CRAN task view mapping for biostatistical RBridge packages.
* **💡 Proposals & Research:**
  * [`docs/proposals/roadmap_local_clinical_agent.md`](docs/proposals/roadmap_local_clinical_agent.md) — Project development roadmap & milestone planning.
  * [`docs/proposals/strands_agent_integration_proposal.md`](docs/proposals/strands_agent_integration_proposal.md) — Multi-agent integration architecture proposal.
  * [`docs/research/research.md`](docs/research/research.md) — Systemic lupus background research notes.

---

## 📜 License & Citation

Licensed under MIT. Clinical classifications strictly derived from:
> Friedman, L. M., Furberg, C. D., DeMets, D. L., Reboussin, D. M., & Granger, C. B. (2015). *Fundamentals of Clinical Trials* (4th ed.). Springer.
