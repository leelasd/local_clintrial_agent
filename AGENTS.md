# Clinical Trial Agent

Multi-entrypoint clinical trial design analysis system. Local-first: local LLM, local PostgreSQL (AACT + ChEMBL 37), local R statistical kernel. Protocol classifications guided by Friedman, Furberg & DeMets, *Fundamentals of Clinical Trials* (4th ed.).

## Setup
```bash
uv venv .venv --python 3.12 && source .venv/bin/activate && uv sync
```
Requires **three** local services running (see Entrypoints for which need what):
1. **PostgreSQL** on `localhost:5432` with `chembl_37` database (AAACT `ctgov.*` schema + ChEMBL 37 `public.*` + `bridge.chembl_clinical_trials`). No `db:` section in `pipeline_config.yaml` — `get_db_connection()` defaults to `chembl_37`/`localhost`/user=None.
2. **llama-server** for Strands agents: `/opt/homebrew/bin/llama-server -m ~/.cache/huggingface/hub/models--ggml-org--gemma-4-E2B-it-GGUF/snapshots/a1dac71d3ab220618f5a7573a52acdc4baf3ae3b/gemma-4-E2B-it-Q8_0.gguf -c 16384 --port 8080`
3. **Ollama** for legacy pipeline eligibility classification: pull `gemma4:latest` (config key `llm.model`). The old `gemma2:2b-instruct-q4_K_M` is stale.

R engine ≥4.2 with packages: `rpact`, `gsDesign`, `gsDesign2`, `graphicalMCP` (core, loaded by `RBridge.__init__`), `clinfun`, `PowerTOST`, `dfcrm`, `blockrand`, `metafor`, `jsonlite` (lazy-loaded per-method). Install via `Rscript -e 'install.packages("pkg")'`.

## Entrypoints
| Command | File | LLM | Needs DB | Needs R |
|---|---|---|---|---|
| `python strands_clinical_graph.py --trials NCT1 NCT2 --comparison-name foo` | `strands_clinical_graph.py` | llama-server :8080 | yes | yes (metafor) |
| `python strands_clinical_swarm.py --trials NCT1 NCT2 --comparison-name foo` | `strands_clinical_swarm.py` | llama-server :8080 | yes | yes |
| `uv run clinical_agent_mcp.py` | `clinical_agent_mcp.py` | none (server only) | yes | yes |
| `python design_agent_pipeline.py [--trials NCT1 ...] [--comparison-name foo]` | `design_agent_pipeline.py` | Ollama | optional* | optional* |
| `python validate_pipeline.py` | `validate_pipeline.py` | none | yes | yes |
| `python power_visualization.py` | `power_visualization.py` | none | no | no |
| `clinical-agent` | → `design_agent_pipeline.py:main` | Ollama | optional* | optional* |

*Legacy pipeline degrades gracefully: `fetch_trial` falls back to ClinicalTrials.gov v2 API if DB unreachable; `analyze_sample_size` falls back to Python approximations if R/rpy2 fails (when `calculation_mode: Python-approx`).

**Strands graph/swarm require BOTH `--trials` AND `--comparison-name` (both `required=True` in argparse).**

## Architecture
- **`strands_clinical_graph.py`** (main): deterministic 4-node DAG `protocol_extractor → biostatistician → feasibility_specialist → synthesizer`. State-channel isolation keeps prompts <2K tokens per node. Calls MCP tools via stdio `MCPClient` to `clinical_agent_mcp.py`. After per-trial analysis, runs cross-trial meta-analysis (R metafor) **only within homogeneous drug classes** with ≥2 trials — class mapping is a hardcoded `trial_class_map` dict near line 185.
- **`clinical_agent_mcp.py`**: FastMCP stdio server, 6 tools. Every tool wrapped with `@redirect_stdout_to_stderr` to prevent JSON-RPC stream corruption (do NOT remove this wrapper). `query_clinical_db` enforces read-only via regex and caps at 100 rows.
- **`design_agent_pipeline.py`**: legacy single-file pipeline (1073+ lines). Algorithmic trial design/population/randomization/endpoints/adaptive/safety analysis from ClinicalTrials.gov structured data. `analyze_trial(nct_id)` is the core function, called by MCP `analyze_trial_design` tool. Now imports from `clintrial_agent/` package.
- **`clintrial_agent/`** package (shared modules):
  - `config.py` — loads `pipeline_config.yaml` at import via `Path(__file__).parent.parent` (must be at project root). Exports `CONFIG`, `INDICATION_PARAMS`, `DEFAULT_INDICATION_PARAMS`.
  - `data/` — `parser.py:fetch_trial(nct_id)` tries local DB first (`db.py:fetch_trial_from_db`), falls back to API. DB adapter reconstructs API-shaped JSON so downstream code is source-agnostic.
  - `eligibility/` — `constraints.py:parse_constraints` (regex extraction of Age/ECOG/Hb/Platelets/ANC/Bilirubin/transaminases), `yield_simulator.py:generate_synthetic_cohort` (N=10000 default), `simulate_relaxation`.
  - `llm/client.py` — `infer_indication`, `classify_eligibility_criteria` (Ollama, batch size from `llm.batch_size`). Loads `agent_prompt.txt` via `Path(__file__).parent.parent.parent / 'agent_prompt.txt'` (3 levels up — file must be at project root).
  - `stats/r_bridge.py` — **production `RBridge` class** (rpy2 → R). `stats/power.py:analyze_sample_size` dispatches by endpoint type; checks `calculation_mode` config (`R-exact` default, `Python-approx` fallback). `stats/meta_analysis.py:calculate_meta_analysis` (R metafor, generates forest plot PNG).
  - `reporting/visualization.py` — `generate_power_plots`.
- **`examples/rpy2_bridge.py`**: reference/standalone `RBridge` demo (not imported by pipeline). Production version is `clintrial_agent/stats/r_bridge.py`.

## R + rpy2 Gotchas
- `R_HOME` must be set before importing rpy2. `r_bridge.py` auto-resolves via `R RHOME` subprocess, falls back to `/opt/homebrew/Cellar/r/4.6.1/lib/R` then `/opt/homebrew/lib/R`.
- rpy2 runs in **ABI mode** (not API mode) — prebuilt `_rinterface_cffi_api.abi3.so` has hardcoded rpath to non-existent R 4.5 framework. Works, but: use `ro.r('expr')` with `eval(parse(text=...))` for multi-line R code, NOT `.rx2()` accessor API. The `_eval_to_json` method in `RBridge` handles this pattern.
- All R code blocks use `.result <- list(...)` pattern; `jsonlite::toJSON` marshals to Python dict/list.
- R-exact dispatch in `power.py`: CROSSOVER → `powertost_sample_size`, single-arm Phase 2 dichotomous → `clinfun_simon2stage`, survival → `gsdesign_fixed_survival`. Each wrapped in try/except with Python fallback.
- gsDesign is GPL-3; rpact is LGPL-3. rpy2 in-process linking to rpact is license-clean; gsDesign via rpy2 has copyleft implications (not yet addressed — see issue #15 phase 4).

## Config
- `pipeline_config.yaml` (project root, 609 lines): `calculation_mode`, alpha/power targets, thresholds, keyword dicts, `indication_params`/`default_indication_params`, `llm.model`/`batch_size`/`temperature`/`num_predict`, `default_trials`, `default_comparison_name`, `api_base_url`, `gwas_api_base_url`, `pharmacogenetic_drugs`, `masking_map`. Each value annotated with textbook rationale or "oncology heuristic".
- `agent_prompt.txt` (project root): LLM prompt schema for eligibility classification (Safety / Statistical Power / Feasibility categories).

## Key Gotchas
- **Two LLM backends**: Strands graph/swarm use `llama-server` (port 8080, gemma-4 Q8, 16K context). Legacy pipeline (`design_agent_pipeline.py` → `clintrial_agent/llm/client.py`) uses Ollama with `gemma4:latest`. Starting the wrong one = silent failures.
- `validate_pipeline.py` imports from `clinical_agent_mcp` (top-level module), NOT `clintrial_agent` package. Must run from project root.
- Masking normalized per textbook: QUADRUPLE/TRIPLE → Double-blind (configurable via `masking_map`).
- `infer_indication()` returns `None` for unknown indications; power analysis falls back to `default_indication_params`.
- LLM output normalization handles known typos: `justigation` → `justification`, variant field names, category synonyms like `operational` → `Feasibility`.
- `strands_clinical_graph.py` meta-analysis: `trial_class_map` dict near line 185 is hardcoded — add new NCT IDs there or they default to `General` class with placeholder HR=0.80.
- No tests, no linting, no typechecking, no CI. `validate_pipeline.py` is an integration smoke test (4 tests: DB fetch, eligibility sim, R-exact calc, MCP tools + SQL security guardrail), not a unit test suite.

## Output
- `analysis_json/{NCT_ID}_analysis.json` — per-trial full analysis (legacy pipeline)
- `analysis_json/{NCT_ID}_graph_report.txt` — per-trial graph reports (Strands graph)
- `analysis_json/{comparison_name}_graph_comparison.json` — portfolio comparisons (graph)
- `analysis_json/{comparison_name}_comparison.json` — portfolio comparisons (legacy)
- `images/` — power curve PNGs + forest plots (`{comparison}_{class}.png`)

## Gitignored (do not read/write)
- `textbook/` — reference textbook PDF/markdown
- `legacy_tests/` — old scripts
- `session-*.md` — session logs
