# Clinical Trial Analysis Agent

An automated clinical trial analysis pipeline that classifies protocol characteristics from [ClinicalTrials.gov](https://clinicaltrials.gov/) API data, guided by **Friedman, Furberg & DeMets, *Fundamentals of Clinical Trials* (4th ed.)**.

## Overview

This agent fetches trial data via the ClinicalTrials.gov v2 API and runs a multi-step analytical pipeline. Each step corresponds to a chapter from the textbook. The LLM (Gemma2 via Ollama) is used exclusively for **eligibility criteria classification**; all other analysis is algorithmic using the structured API data.

### Pipeline Steps

| Step | Textbook Chapter | Function | What It Does |
|------|-----------------|----------|-------------|
| 1 | **Ch 5 — Study Design** | `classify_design_from_api()` | Design type (Parallel RCT, Crossover, etc.), control type, superiority type — all from API allocation/intervention model/arm types |
| 2 | **Ch 3 — Endpoints** | `classify_endpoint_type()` | Primary/secondary outcomes classified as Surrogate, Clinical, Composite, Patient-Reported, Safety, or Biomarker |
| 3 | **Ch 4 — Study Population** | `analyze_study_population()` | Sex, age range, competing risk exclusions, recruitment yield estimate |
| 4 | **Ch 8 — Sample Size / Power** | `analyze_sample_size()` | Per-arm enrollment, detectable effect size at 80% power (α=0.05 two-sided) using normal approximation with `scipy.stats.norm.ppf`. Assessment: Adequately Powered / Borderline / Underpowered |
| 5 | **Ch 6 — Randomization** | `analyze_randomization()` | Randomization type (Simple/Blocked/Stratified/Adaptive), allocation ratio, stratification factors — keyword detection from protocol text |
| 6 | **Ch 7 — Blindness** | (in `trial_integrity`) | API masking normalized: QUADRUPLE/TRIPLE/DOUBLE → Double-blind, SINGLE → Single-blind, NONE → Open-label |
| 7 | **Ch 19 — Adaptive Designs** | `analyze_adaptive_design()` | Detects Group Sequential, Sample Size Re-estimation, Response-Adaptive Randomization, Basket/Umbrella/Platform, Dose-Finding, Seamless Phase 2/3 |
| 8 | **Ch 12 — Safety / AEs** | `analyze_safety_adverse_events()` | Extracts AE terms from protocol text, classifies reporting method (MedDRA/CTCAE), detects DSMB and SAE stopping rules |
| 9 | **LLM Classification** | Ollama `gemma2:2b-instruct-q4_K_M` | Eligibility criteria classified into Safety / Statistical Power / Feasibility with justifications |

## Requirements

- Python 3.12
- [Ollama](https://ollama.ai/) with models:
  - `gemma2:2b-instruct-q4_K_M` (current pipeline)
  - `gemma3:1b-it-qat` (legacy)
- Dependencies: `requests`, `ollama`, `scipy`

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install requests ollama scipy
```

## Usage

```bash
source .venv/bin/activate
python design_agent_pipeline.py
```

This analyzes all 3 TYK2 trials and saves per-trial JSON and a combined comparison.

## Output

### Per-trial: `{NCT_ID}_analysis.json`

```json
{
  "nct_id": "NCT06088043",
  "title": "A Study About How Well TAK-279 Works...",
  "phase": "PHASE3",
  "eligibility": [
    {
      "text": "Plaque psoriasis for at least 6 months",
      "reasoning_category": "Statistical Power",
      "justification": "...",
      "competing_risk": false
    }
  ],
  "population": {
    "sex": "ALL",
    "age_range": "18 Years+",
    "age_restrictiveness": "Moderate",
    "has_competing_risk_exclusions": false,
    "recruitment_yield_estimate": "Moderate (5-20% screen-to-enroll)",
    "enrollment_count": 693,
    "enrollment_type": "ACTUAL"
  },
  "sample_size": {
    "enrollment_actual": 693,
    "estimated_n_per_arm": 231,
    "num_arms": 3,
    "primary_endpoint_type": "Dichotomous (Proportion)",
    "power_analysis": {
      "alpha": 0.05,
      "power_target": 0.80,
      "detectable_absolute_difference": 0.10,
      "estimated_power_for_20pct_improvement": 1.0,
      "assessment": "Adequately Powered"
    }
  },
  "endpoints": [
    {
      "text": "PASI-75 at Week 16",
      "endpoint_type": "Surrogate",
      "timeframe": "Week 16",
      "is_primary": true
    }
  ],
  "trial_integrity": {
    "masking_level": "Double-blind",
    "blinding_validation_method": "...",
    "concomitant_therapy_controls": "Standardized background care"
  },
  "trial_design": {
    "design_type": "Parallel RCT",
    "control_type": "Placebo",
    "superiority_type": "Superiority"
  },
  "randomization": {
    "randomization_type": "Blocked",
    "allocation_ratio": "1:1:1",
    "stratification_factors": ["Baseline", "Pasi"],
    "randomization_description": "Stratified by Baseline, Pasi. Blocked randomization."
  },
  "adaptive_designs": {
    "has_adaptive_features": false,
    "adaptive_types": [],
    "interim_analysis_mentioned": false,
    "stopping_rules": "Not mentioned",
    "description": "Standard fixed-design trial. No adaptive features detected."
  },
  "safety_adverse_events": {
    "ae_reporting_method": "Not explicitly specified",
    "ae_ascertainment": "Not explicitly described...",
    "ae_types_detected": [],
    "class_effects_known": ["AST elevation", "Infections (general)"],
    "safety_endpoints": ["Number of Participants with TEAEs and AESIs"],
    "sae_stopping_rules": "Not specified in protocol text",
    "safety_monitoring": "Investigator-reported with sponsor oversight"
  },
  "summary": {
    "Statistical Power": 3,
    "Feasibility": 2,
    "Safety": 2
  }
}
```

### Combined: `tyk2_comparison.json`

Full per-trial output keyed by NCT ID, plus a terminal power comparison table:

```
Drug                           Enroll   Arms   N/Arm  Detect Δ   Power@20%  Assessment
Zasocitinib (TAK-279)          693      3      231    10%        100%       Adequately Powered
Deucravacitinib (BMS-986165)   220      2      110    15%        96%        Borderline
JNJ-77242113                   731      3      243    9%         100%       Adequately Powered
```

### Visualization

`power_visualization.py` generates:
- `power_analysis.png` — Power curves for each trial
- `power_vs_effect.png` — Detectable effect vs sample size comparison

## TYK2 Trials Analyzed

| NCT ID | Drug | Phase | Design | Arms | Enrollment |
|--------|------|-------|--------|------|-----------|
| NCT06088043 | Zasocitinib (TAK-279) | Phase 3 | Parallel RCT, placebo + active comparator | 3 | 693 |
| NCT04167462 | Deucravacitinib (BMS-986165) | Phase 3 | Parallel RCT, placebo | 2 | 220 |
| NCT06220604 | JNJ-77242113 | Phase 3 | Parallel RCT, placebo + active comparator | 3 | 731 |

## Key Design Decisions

- **Design classification** from structured API data (not LLM) — allocation, intervention model, arm types are deterministic
- **Power analysis** via scipy math (not LLM) — sample size is a numerical calculation
- **Randomization analysis** via keyword heuristics from protocol text (not LLM)
- **LLM role** limited to eligibility criteria classification into Safety/Statistical Power/Feasibility, informed by design context
- **Masking normalized** per textbook convention: Ch 7 defines double-blind as participant + investigator blinded, so QUADRUPLE/TRIPLE → Double-blind

## Files

| File | Purpose |
|------|---------|
| `design_agent_pipeline.py` | Main pipeline — orchestrates all analysis steps |
| `agent_prompt.txt` | LLM prompt with JSON schema |
| `power_visualization.py` | Power curve plots |
| `llm_agent_pipeline.py` | Legacy: single-trial pipeline (Gemma3) |
| `search_tyk2_trials.py` | Search ClinicalTrials.gov for TYK2 trials |
| `compare_models.py` | Compare LLM model performance |
