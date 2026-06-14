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
| 4 | **Ch 8 — Sample Size / Power** | `analyze_sample_size()` | **Three dispatch modes**: (a) **Dichotomous** — detectable absolute difference via normal approximation for proportion-based endpoints (e.g., PASI-75, ORR). (b) **Survival** — detectable hazard ratio via Schoenfeld event-count formula for PFS/OS endpoints. (c) **Phase 1** — returns N/A with explanation. **Indication-parameterized**: control event rate, median survival, and event rate are looked up by inferred indication |
| 5 | **Ch 6 — Randomization** | `analyze_randomization()` | Randomization type (Simple/Blocked/Stratified/Adaptive), allocation ratio, stratification factors — keyword detection from protocol text |
| 6 | **Ch 7 — Blindness** | (in `trial_integrity`) | API masking normalized: QUADRUPLE/TRIPLE/DOUBLE → Double-blind, SINGLE → Single-blind, NONE → Open-label |
| 7 | **Ch 19 — Adaptive Designs** | `analyze_adaptive_design()` | Detects Group Sequential, Sample Size Re-estimation, Response-Adaptive Randomization, Basket/Umbrella/Platform, Dose-Finding, Seamless Phase 2/3. Also detects dose-escalation method (3+3, CRM, Bayesian) |
| 8 | **Ch 12 — Safety / AEs** | `analyze_safety_adverse_events()` | Extracts AE terms from protocol text, classifies reporting method (MedDRA/CTCAE grading), detects DSMB and SAE stopping rules |
| 9 | **LLM Classification** | Ollama `gemma2:2b-instruct-q4_K_M` | Eligibility criteria classified into Safety / Statistical Power / Feasibility with justifications. **Batched** in groups of 20 to avoid truncation |

## Requirements

- Python 3.12
- [Ollama](https://ollama.ai/) with models:
  - `gemma2:2b-instruct-q4_K_M` (current pipeline)
  - `gemma3:1b-it-qat` (legacy)
- Dependencies managed with `uv`:

```bash
uv venv .venv --python 3.12
source .venv/bin/activate
uv sync
```

## Usage

```bash
source .venv/bin/activate
python design_agent_pipeline.py
```

By default, this analyzes all 3 TYK2 psoriasis trials. To analyze other trials, modify the `__main__` block or import the pipeline functions directly.

## Output

### Per-trial: `analysis_json/{NCT_ID}_analysis.json`

Full JSON with all analysis sections:

```json
{
  "nct_id": "NCT06088043",
  "title": "A Study About How Well TAK-279 Works...",
  "phase": "PHASE3",
  "indication": "psoriasis",
  "eligibility": [
    {
      "text": "Plaque psoriasis for at least 6 months",
      "reasoning_category": "Statistical Power",
      "justification": "...",
      "competing_risk": false
    }
  ],
  "criteria_metadata": {
    "total_parsed": 7,
    "classified": 7,
    "batches": 1,
    "batch_size": 20
  },
  "population": { "..." },
  "sample_size": {
    "enrollment_actual": 693,
    "estimated_n_per_arm": 231,
    "num_arms": 3,
    "primary_endpoint_type": "Dichotomous (Proportion)",
    "estimated_control_event_rate": 0.1,
    "indication_params_used": { "control_rate_dichotomous": 0.1 },
    "power_analysis": {
      "alpha": 0.05,
      "power_target": 0.80,
      "detectable_absolute_difference": 0.100,
      "estimated_power_for_20pct_improvement": 1.0,
      "assessment": "Adequately Powered"
    }
  },
  "endpoints": [ "..." ],
  "trial_integrity": { "..." },
  "trial_design": {
    "design_type": "Parallel RCT",
    "control_type": "Placebo",
    "superiority_type": "Superiority"
  },
  "randomization": { "..." },
  "adaptive_designs": { "..." },
  "safety_adverse_events": { "..." },
  "summary": { "Safety": 3, "Statistical Power": 2, "Feasibility": 2 }
}
```

### Combined Comparison Files

- `analysis_json/tyk2_comparison.json` — TYK2 psoriasis trials
- `analysis_json/wrn_comparison.json` — WRN inhibitor oncology trials
- `analysis_json/rme_comparison.json` — Revolution Medicines KRAS trials

### Visualization

![Sotorasib vs RMC-6236 Power Comparison](images/sotorasib_vs_rmc6236_power.png)

Power curve comparison between Sotorasib (CodeBreaK 200, N=345) and RMC-6236 (RASolute 302, N=500). The vertical dashed line marks the actual published HR from CodeBreaK 200 (HR=0.66).

![TYK2 Power Analysis](images/power_analysis.png)

Power curves for all three TYK2 psoriasis trials (Zasocitinib, Deucravacitinib, JNJ-77242113).

![Power vs Effect Size](images/power_vs_effect.png)

Detectable effect size vs sample size comparison across TYK2 trials.

## Power Analysis

The pipeline supports three types of power analysis depending on endpoint. All modes use **indication-specific parameters** inferred from the trial's conditions and title:

| Indication | Control Rate (Dichotomous) | Median OS (mo) | Median PFS (mo) | Event Rate |
|---|---|---|---|---|
| psoriasis | 0.10 | — | — | — |
| nsclc | 0.30 | 12.0 | 4.5 | 0.80 |
| pdac | 0.05 | 6.0 | 3.5 | 0.85 |
| msi_h_tumor | 0.15 | 18.0 | 5.0 | 0.75 |
| solid_tumor | 0.15 | 10.0 | 4.0 | 0.80 |

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

| NCT ID | Drug | Phase | Design | Arms | Enrollment | Power Assessment |
|--------|------|-------|--------|------|-----------|-----------------|
| NCT06088043 | Zasocitinib (TAK-279) | Phase 3 | Parallel RCT, placebo + active comparator | 3 | 693 | Adequately Powered |
| NCT04167462 | Deucravacitinib (BMS-986165) | Phase 3 | Parallel RCT, placebo | 2 | 220 | Borderline |
| NCT06220604 | JNJ-77242113 | Phase 3 | Parallel RCT, placebo + active comparator | 3 | 731 | Adequately Powered |

### WRN Inhibitors (Oncology)

| NCT ID | Drug | Phase | Design | Indication |
|--------|------|-------|--------|-----------|
| NCT07262619 | EIK1005 | Phase 1/2 | Adaptive Design | MSI-H tumor |
| NCT06710847 | GSK4418959 (SYLVER) | Phase 1/2 | Adaptive Design | Solid tumor |
| NCT06898450 | NDI-219216 | Phase 1/2 | Adaptive Design | Solid tumor |

### Revolution Medicines KRAS Portfolio

| NCT ID | Drug | Phase | Design | Indication |
|--------|------|-------|--------|-----------|
| NCT03634982 | RMC-4630 (SHP2) monotherapy | Phase 1 | Single-Arm | Solid tumor |
| NCT03989115 | RMC-4630 + Cobimetinib | Phase 1/2 | Single-Arm | NSCLC |
| NCT05054725 | RMC-4630 + Sotorasib | Phase 2 | Adaptive Design | NSCLC |
| NCT05462717 | RMC-6291 (KRAS G12D) | Phase 1 | Single-Arm | Solid tumor |
| NCT06040541 | RMC-9805 (KRAS G12D) | Phase 1 | Single-Arm | Solid tumor |
| NCT07349537 | RMC-5127 (KRAS G12V) | Phase 1 | Single-Arm | Solid tumor |
| NCT05379985 | RMC-6236 daraxonrasib (RAS multi) | Phase 1/2 | Single-Arm | Solid tumor |
| NCT06162221 | RAS(ON) inhibitors NSCLC | Phase 1/2 | Single-Arm | NSCLC |
| NCT06445062 | RAS(ON) inhibitors GI | Phase 1/2 | Single-Arm | Solid tumor |
| **NCT06625320** | **RMC-6236 daraxonrasib (PDAC)** | **Phase 3** | **Parallel RCT** | **PDAC** |

### Sotorasib (KRAS G12C)

| NCT ID | Drug | Phase | Design | Indication |
|--------|------|-------|--------|-----------|
| NCT04303780 | Sotorasib (CodeBreaK 200) | Phase 3 | Parallel RCT | NSCLC |

## Key Design Decisions

- **Design classification** from structured API data (not LLM) — allocation, intervention model, arm types are deterministic.
- **Indication inference** from protocol conditions and title — maps to a lookup table of indication-specific power parameters. Falls back to defaults when indication is unknown.
- **Power analysis** uses indication-specific control event rates, median survivals, and event rates (not hardcoded). The `indication_params_used` field in the output shows which parameters drove the calculation.
- **Criteria batching** — eligibility criteria are chunked into batches of 20 and sent to the LLM sequentially. The `criteria_metadata` field tracks total parsed, classified, and batch count.
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
| `pyproject.toml` | Project metadata and dependencies (uv) |
| `uv.lock` | Locked dependency versions |
| `analysis_json/` | Per-trial and per-portfolio analysis outputs |
| `images/` | Power curve visualizations |
