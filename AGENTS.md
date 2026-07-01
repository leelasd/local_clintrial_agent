# Clinical Trial Analysis Workspace

## Setup
```bash
uv venv .venv --python 3.12 && source .venv/bin/activate && uv sync
```
Requires local Ollama running with `gemma2:2b-instruct-q4_K_M`. The `gemma3:1b-it-qat` model is legacy-only.

## Running
```bash
source .venv/bin/activate
python design_agent_pipeline.py                          # default trials from config
python design_agent_pipeline.py --trials NCT001 NCT002   # specific trials
python design_agent_pipeline.py --comparison-name myco   # custom comparison name
python -c "from design_agent_pipeline import analyze_trial; analyze_trial('NCT_ID')"  # single trial
clinical-agent                                            # same as default (pyproject entry point)
python power_visualization.py                            # generate power curve images
```

## Architecture
Single-file pipeline (`design_agent_pipeline.py`) driven by `pipeline_config.yaml`. No tests, no linting, no typechecking.

- **Config**: `pipeline_config.yaml` — all tunable constants (alpha, power targets, thresholds, keyword dicts, LLM params, default trials). Loaded at import via `_load_config()`. Each value annotated with textbook rationale or "oncology heuristic, not textbook-standard"
- **Design, population, randomization, endpoints, adaptive, safety** — all algorithmic (no LLM), parsed from ClinicalTrials.gov v2 API structured data
- **Eligibility criteria classification** — LLM (Ollama gemma2), batch size from config (`llm.batch_size`, default 20)
- **Power analysis** — dispatches by endpoint type (dichotomous / survival / Phase 1 N/A), uses indication-specific parameters from config `indication_params` / `default_indication_params`
- `agent_prompt.txt` — LLM prompt schema (Safety / Statistical Power / Feasibility categories + trial design fields)

## Key Gotchas
- `pipeline_config.yaml` must be in the same directory as `design_agent_pipeline.py`; `_load_config()` resolves it via `Path(__file__).parent`
- Masking is **normalized per textbook**: QUADRUPLE/TRIPLE → Double-blind, not "quadruple-blind" (configurable via `masking_map` in config)
- `infer_indication()` returns `None` for unknown indications; power analysis falls back to `default_indication_params`
- LLM output normalization handles known typos: `justigation` → `justification`, variant field names, category synonyms like `operational` → `Feasibility`
- `__main__` no longer hardcodes trials — uses argparse `--trials` flag, falling back to `default_trials` in config
- API URL configurable via `api_base_url` in config (default: `https://clinicaltrials.gov/api/v2/studies`)
- Assessment thresholds (survival HR, dichotomous delta) are oncology-specific heuristics, not textbook-standard — documented in config comments

## Output
- `analysis_json/{NCT_ID}_analysis.json` — per-trial full analysis
- `analysis_json/{portfolio}_comparison.json` — multi-trial comparisons (name from `--comparison-name` or config `default_comparison_name`)
- `images/` — power curve PNGs

## Gitignored (do not read/write)
- `textbook/` — PDF and markdown of reference textbook
- `legacy_tests/` — old scripts
- `session-*.md` — session logs
