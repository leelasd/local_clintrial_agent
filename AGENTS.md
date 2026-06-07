# Clinical Trial Analysis Workspace

## Project Overview
Clinical trial analysis using LLM agents to classify eligibility criteria from ClinicalTrials.gov and compare TYK2 inhibitor drugs.

## Environment
- Python 3.12 in `.venv` (managed by `uv`)
- Requires local Ollama with models: `gemma2:2b-instruct-q4_K_M`, `gemma3:1b-it-qat`
- Dependencies not tracked (no requirements.txt) - uses: `requests`, `ollama`

## Key Files
- `agent_prompt.txt` - LLM prompt defining classification schema (Safety/Statistical Power/Feasibility) and trial design fields
- `design_agent_pipeline.py` - **Current pipeline**: extracts design from API (design_type, control_type, superiority_type), normalizes masking to textbook terms, classifies eligibility via Gemma2
- `llm_agent_pipeline.py` - Original single-trial pipeline (Gemma3)
- `compare_models.py` - Compares LLM model performance across TYK2 trials
- `search_tyk2_trials.py` - Queries ClinicalTrials.gov API for TYK2 trials

## Running Scripts
```bash
source .venv/bin/activate

# Current: analyze trial with design classification + eligibility
python design_agent_pipeline.py

# Legacy: original single-trial pipeline
python llm_agent_pipeline.py

# Compare TYK2 trials across models
python compare_models.py

# Search for TYK2 trials
python search_tyk2_trials.py
```

## Data Flow
1. Fetch trial data from `https://clinicaltrials.gov/api/v2/studies/{NCT_ID}`
2. **Step 1**: Classify trial design from structured API data (allocation, intervention model, arm types)
3. **Step 2**: Extract `eligibilityModule.eligibilityCriteria` text
4. **Step 3**: Batch prompt LLM with criteria list + design context, classify into Safety/Statistical Power/Feasibility
5. Normalize LLM output (handle typos, variant field names, category synonyms)
6. Normalize masking to conventional terms (QUADRUPLE → Double-blind)
7. Output `{NCT_ID}_analysis.json`

## Output Files
- `{NCT_ID}_analysis.json` - Single trial analysis with trial_design, trial_integrity, eligibility classification
- `model_comparison.json` - Multi-model comparison results
- `tyk2_trials.json` - Search results

## Trial Design Classification (from API)
- **design_type**: Parallel RCT, Crossover, Factorial, Single-Arm, Adaptive Design, etc.
- **control_type**: Placebo, Active Comparator, No Treatment, Standard of Care, None (Single-Arm)
- **superiority_type**: Superiority, Noninferiority, Equivalence, Unclear
- **masking**: Double-blind, Single-blind, Open-label (normalized from API values)

## TYK2 Trials Analyzed
- `NCT04167462` - Deucravacitinib (approved)
- `NCT06220604` - JNJ-77242113
- `NCT06088043` - Zasocitinib
