# Clinical Trial Analysis Workspace

## Project Overview
Clinical trial analysis using LLM agents to classify eligibility criteria from ClinicalTrials.gov and compare TYK2 inhibitor drugs.

## Environment
- Python 3.12 in `.venv` (managed by `uv`)
- Requires local Ollama with models: `gemma2:2b-instruct-q4_K_M`, `gemma3:1b-it-qat`
- Dependencies not tracked (no requirements.txt) - uses: `requests`, `ollama`

## Key Files
- `agent_prompt.txt` - LLM prompt defining classification schema (Safety/Statistical Power/Feasibility)
- `llm_agent_pipeline.py` - Main analysis pipeline for single trials
- `compare_models.py` - Compares LLM model performance across TYK2 trials
- `search_tyk2_trials.py` - Queries ClinicalTrials.gov API for TYK2 trials

## Running Scripts
```bash
# Activate environment
source .venv/bin/activate

# Analyze single trial
python llm_agent_pipeline.py

# Compare TYK2 trials across models
python compare_models.py

# Search for TYK2 trials
python search_tyk2_trials.py
```

## Data Flow
1. Fetch trial data from `https://clinicaltrials.gov/api/v2/studies/{NCT_ID}`
2. Extract `eligibilityModule.eligibilityCriteria` text
3. Batch prompt LLM with criteria list (first 20 for speed)
4. Parse JSON response with error recovery
5. Output `{NCT_ID}_analysis.json`

## Output Files
- `{NCT_ID}_llm_analysis.json` - Single trial analysis
- `model_comparison.json` - Multi-model comparison results
- `tyk2_trials.json` - Search results

## TYK2 Trials Analyzed
- `NCT04167462` - Deucravacitinib (approved)
- `NCT06220604` - JNJ-77242113
- `NCT06088043` - Zasocitinib
