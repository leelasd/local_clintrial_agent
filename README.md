# Clinical Trial Analysis Agent

An automated clinical trial analysis pipeline that classifies protocol characteristics from [ClinicalTrials.gov](https://clinicaltrials.gov/) API data, guided by **Friedman, Furberg & DeMets, *Fundamentals of Clinical Trials* (4th ed.)**.

## Overview

This agent fetches trial data via the ClinicalTrials.gov v2 API and runs a multi-step analytical pipeline. Each step corresponds to a chapter from the textbook. The LLM (Gemma2 via Ollama) is used exclusively for **eligibility criteria classification**; all other analysis is algorithmic using the structured API data.

### Pipeline Steps

| Step | Textbook Chapter | Function | What It Does |
|------|-----------------|----------|-------------|
| 1 | **Ch 5 — Study Design** | `classify_design_from_api()` | Design type (Parallel RCT, Crossover, Adaptive Design, Single-Arm, etc.), control type, superiority type — all from API allocation/intervention model/arm types. Handles Phase 1/2 oncology dose-escalation (Single-Arm, Adaptive Design) vs Phase 3 confirmatory (Parallel RCT) |
| 2 | **Ch 3 — Endpoints** | `classify_endpoint_type()` | Primary/secondary outcomes classified as Surrogate, Clinical, Composite, Patient-Reported, Safety, or Biomarker. Includes oncology-specific terms: DLT/MTD → Safety, RECIST/ORR/PFS/OS → Surrogate/Clinical, PK/AUC/Cmax → Biomarker |
| 3 | **Ch 4 — Study Population** | `analyze_study_population()` | Sex, age range, competing risk exclusions, recruitment yield estimate |
| 4 | **Ch 8 — Sample Size / Power** | `analyze_sample_size()` | **Three dispatch modes**: (a) **Dichotomous** — detectable absolute difference via normal approximation for proportion-based endpoints (e.g., PASI-75, ORR). (b) **Survival** — detectable hazard ratio via Schoenfeld event-count formula for PFS/OS endpoints. (c) **Phase 1** — returns N/A with explanation. Assessment: Adequately Powered / Borderline / Underpowered / Severely Underpowered |
| 5 | **Ch 6 — Randomization** | `analyze_randomization()` | Randomization type (Simple/Blocked/Stratified/Adaptive), allocation ratio, stratification factors — keyword detection from protocol text |
| 6 | **Ch 7 — Blindness** | (in `trial_integrity`) | API masking normalized: QUADRUPLE/TRIPLE/DOUBLE → Double-blind, SINGLE → Single-blind, NONE → Open-label |
| 7 | **Ch 19 — Adaptive Designs** | `analyze_adaptive_design()` | Detects Group Sequential, Sample Size Re-estimation, Response-Adaptive Randomization, Basket/Umbrella/Platform, Dose-Finding, Seamless Phase 2/3. Also detects dose-escalation method (3+3, CRM, Bayesian) |
| 8 | **Ch 12 — Safety / AEs** | `analyze_safety_adverse_events()` | Extracts AE terms from protocol text, classifies reporting method (MedDRA/CTCAE grading), detects DSMB and SAE stopping rules |
| 9 | **LLM Classification** | Ollama `gemma2:2b-instruct-q4_K_M` | Eligibility criteria classified into Safety / Statistical Power / Feasibility with justifications |

## Requirements

- Python 3.12
- [Ollama](https://ollama.ai/) with models:
  - `gemma2:2b-instruct-q4_K_M` (current pipeline)
  - `gemma3:1b-it-qat` (legacy)
- Dependencies: `requests`, `ollama`, `scipy`, `matplotlib`, `numpy`

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install requests ollama scipy matplotlib numpy
```

## Usage

```bash
source .venv/bin/activate
python design_agent_pipeline.py
```

By default, this analyzes all 3 TYK2 psoriasis trials. To analyze other trials, modify the `__main__` block or import the pipeline functions directly.

## Output

### Per-trial: `{NCT_ID}_analysis.json`

Full JSON with all analysis sections:

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
  "population": { ... },
  "sample_size": {
    "enrollment_actual": 345,
    "estimated_n_per_arm": 172,
    "num_arms": 2,
    "primary_endpoint_type": "PFS (Progression-Free Survival)",
    "power_analysis": {
      "alpha": 0.05,
      "power_target": 0.80,
      "test_type": "Two-sided (log-rank)",
      "detectable_hazard_ratio": 0.721,
      "hr_reduction": "28%",
      "expected_events": 293,
      "control_median_months": 3.5,
      "implied_treatment_median_months": 4.9,
      "median_improvement_months": 1.4,
      "assessment": "Borderline"
    }
  },
  "endpoints": [ ... ],
  "trial_integrity": { ... },
  "trial_design": {
    "design_type": "Parallel RCT",
    "control_type": "Active Comparator",
    "superiority_type": "Superiority"
  },
  "randomization": { ... },
  "adaptive_designs": {
    "has_adaptive_features": false,
    "adaptive_types": [],
    "dose_escalation_method": null,
    "description": "Standard fixed-design trial..."
  },
  "safety_adverse_events": { ... },
  "summary": { ... }
}
```

### Combined Comparison Files

- `tyk2_comparison.json` — TYK2 psoriasis trials
- `wrn_comparison.json` — WRN inhibitor oncology trials
- `rme_comparison.json` — Revolution Medicines KRAS trials

### Visualization

- `sotorasib_vs_rmc6236_power.png` — Power curve comparison between two KRAS-targeting Phase 3 trials
- `power_analysis.png`, `power_vs_effect.png` — Power curves for TYK2 trials

## Power Analysis

The pipeline supports three types of power analysis depending on endpoint:

### 1. Dichotomous (Proportion-based)
For endpoints like PASI-75, ORR. Uses normal approximation to compute detectable absolute difference at 80% power.

### 2. Survival (Time-to-event)
For endpoints like PFS, OS. Uses **Schoenfeld event-count formula** from Ch 8:
```
D = (Zα + Zβ)² / [p(1-p) × ln(HR)²]
```
Outputs detectable HR, implied median improvement in months, and expected number of events.

### 3. Phase 1 Safety / Dose-Finding
Returns `N/A — Phase 1 trial, not powered for efficacy`.

## Trials Analyzed

### TYK2 Inhibitors (Psoriasis)

| NCT ID | Drug | Phase | Design | Arms | Enrollment |
|--------|------|-------|--------|------|-----------|
| NCT06088043 | Zasocitinib (TAK-279) | Phase 3 | Parallel RCT, placebo + active comparator | 3 | 693 |
| NCT04167462 | Deucravacitinib (BMS-986165) | Phase 3 | Parallel RCT, placebo | 2 | 220 |
| NCT06220604 | JNJ-77242113 | Phase 3 | Parallel RCT, placebo + active comparator | 3 | 731 |

### WRN Inhibitors (Oncology)

| NCT ID | Drug | Phase | Design | Sponsor |
|--------|------|-------|--------|---------|
| NCT07262619 | EIK1005 | Phase 1/2 | Adaptive Design | Eikon Therapeutics |
| NCT06710847 | GSK4418959 (SYLVER) | Phase 1/2 | Adaptive Design | GSK |
| NCT06898450 | NDI-219216 | Phase 1/2 | Adaptive Design | Nimbus Therapeutics |

### Revolution Medicines KRAS Portfolio

| NCT ID | Drug | Phase | Design | Status |
|--------|------|-------|--------|--------|
| NCT03634982 | RMC-4630 (SHP2) monotherapy | Phase 1 | Single-Arm | Completed |
| NCT03989115 | RMC-4630 + Cobimetinib | Phase 1/2 | Single-Arm | Completed |
| NCT05054725 | RMC-4630 + Sotorasib | Phase 2 | Adaptive Design | Completed |
| NCT05462717 | RMC-6291 (KRAS G12D) | Phase 1 | Single-Arm | Active |
| NCT06040541 | RMC-9805 (KRAS G12D) | Phase 1 | Single-Arm | Recruiting |
| NCT07349537 | RMC-5127 (KRAS G12V) | Phase 1 | Single-Arm | Recruiting |
| NCT05379985 | RMC-6236 daraxonrasib (RAS multi) | Phase 1/2 | Single-Arm | Recruiting |
| NCT06162221 | RAS(ON) inhibitors NSCLC | Phase 1/2 | Single-Arm | Recruiting |
| NCT06445062 | RAS(ON) inhibitors GI | Phase 1/2 | Single-Arm | Recruiting |
| **NCT06625320** | **RMC-6236 daraxonrasib (PDAC)** | **Phase 3** | **Parallel RCT** | **Active** |

### Sotorasib (KRAS G12C)

| NCT ID | Drug | Phase | Design | Status |
|--------|------|-------|--------|--------|
| NCT04303780 | Sotorasib (CodeBreaK 200) | Phase 3 | Parallel RCT | Active |
| NCT05198934 | Sotorasib + Panitumumab | Phase 3 | Parallel RCT | Completed |

## Key Design Decisions

- **Design classification** from structured API data (not LLM) — allocation, intervention model, arm types are deterministic.
- **All-experimental arms** with non-randomized allocation (dose-escalation cohorts) are classified as Single-Arm, not Nonrandomized Concurrent Control or Parallel RCT.
- **Phase 1 trials** default to Single-Arm design with Unclear superiority.
- **Superiority type** defaults to Superiority for all non-Phase-1 trials. Noninferiority is only set when protocol text explicitly mentions it.
- **Power analysis** uses scipy math (not LLM) — sample size is a numerical calculation. Three dispatch modes for dichotomous, survival, and Phase 1 endpoints.
- **Survival power** uses the Schoenfeld event-count formula from Ch 8, the standard method for PFS/OS trials.
- **Randomization analysis** via keyword heuristics from protocol text (not LLM).
- **LLM role** limited to eligibility criteria classification into Safety/Statistical Power/Feasibility, informed by design context.
- **Masking normalized** per textbook convention: Ch 7 defines double-blind as participant + investigator blinded, so QUADRUPLE/TRIPLE → Double-blind.
- **Adaptive design detection** distinguishes API model names (SEQUENTIAL = dose escalation) from true adaptive design features (group sequential, sample size re-estimation, etc.).

## Files

| File | Purpose |
|------|---------|
| `design_agent_pipeline.py` | Main pipeline — orchestrates all analysis steps |
| `agent_prompt.txt` | LLM prompt with JSON schema |
| `power_visualization.py` | Power curve plots for TYK2 trials |
| `sotorasib_vs_rmc6236_power.png` | Power curve comparison for KRAS Phase 3 trials |
| `llm_agent_pipeline.py` | Legacy: single-trial pipeline (Gemma3) |
| `search_tyk2_trials.py` | Search ClinicalTrials.gov for TYK2 trials |
| `compare_models.py` | Compare LLM model performance |
| `*_comparison.json` | Combined per-portfolio analysis output |
| `NCT*_analysis.json` | Per-trial detailed analysis |
