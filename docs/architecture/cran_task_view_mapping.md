# CRAN Task View: Clinical Trials Mapping

This document maps the **CRAN Task View: Clinical Trial Design, Monitoring, Analysis and Reporting** (maintained on [GitHub](https://github.com/cran-task-views/ClinicalTrials)) to our Python-based Clinical Trial Analysis Agent. 

Interestingly, both this task view and our pipeline share the exact same theoretical foundation: **Friedman, Furberg & DeMets, *Fundamentals of Clinical Trials***.

---

## 🗺️ Pipeline Mapping to CRAN Packages

The table below shows how the steps in our Python pipeline ([design_agent_pipeline.py](file:///Users/leelasdodda/Documents/Codes/local_clintrial_agent/design_agent_pipeline.py)) align with the core chapters of *Fundamentals of Clinical Trials* and the corresponding specialized R packages from the CRAN Task View.

| Pipeline Step | Textbook Chapter | Python Pipeline Function / Module | Primary CRAN R Packages | Purpose / Methodological Overlap |
| :--- | :--- | :--- | :--- | :--- |
| **1. Study Design** | **Ch 5 — Study Design** | [`classify_design_from_api()`](file:///Users/leelasdodda/Documents/Codes/local_clintrial_agent/design_agent_pipeline.py#L41-L129) | `asd`, `CohortPlat`, `ncc` | Identifies trial models (Parallel RCT, Crossover, Adaptive Design, Single-Arm). CRAN packages focus on simulating these structures (e.g., non-concurrent controls in platform trials with `ncc`). |
| **2. Endpoints** | **Ch 3 — Endpoints** | `classify_endpoint_type()` | `clinsig` | Classifies clinical endpoints (Surrogate, Clinical, Safety, etc.). `clinsig` helps calculate clinical significance vs. statistical significance. |
| **3. Population** | **Ch 4 — Study Population** | [`analyze_study_population()`](file:///Users/leelasdodda/Documents/Codes/local_clintrial_agent/design_agent_pipeline.py#L131-L186) | `accrualPlot` | Estimates recruitment yields and patient restrictiveness. `accrualPlot` is used to simulate and visualize cohort accrual rates. |
| **4. Sample Size & Power** | **Ch 8 — Sample Size / Power** | [`analyze_sample_size()`](file:///Users/leelasdodda/Documents/Codes/local_clintrial_agent/design_agent_pipeline.py#L188-L289) | `TrialSize`, `PowerTOST`, `drugdevelopR` | Computes detectable differences (dichotomous) or HR (survival via Schoenfeld formula). `TrialSize` provides sample size formulas, and `PowerTOST` specializes in bioequivalence power. |
| **5. Randomization** | **Ch 6 — Randomization** | [`analyze_randomization()`](file:///Users/leelasdodda/Documents/Codes/local_clintrial_agent/design_agent_pipeline.py#L440-L492) | `blockrand`, `carat`, `covadap` | Keyword detection for blocking/stratification. CRAN packages (like `carat` and `covadap`) generate and analyze covariate-adaptive randomization schedules. |
| **6. Blinding / Masking** | **Ch 7 — Blindness** | `trial_integrity` (via [`masking_map`](file:///Users/leelasdodda/Documents/Codes/local_clintrial_agent/pipeline_config.yaml#L112-L118)) | *N/A (Primarily operational)* | Normalizes trial masking fields (TRIPLE/QUADRUPLE → Double-blind). R packages in this area are rare as blinding is an operational trial procedure. |
| **7. Adaptive Designs** | **Ch 19 — Adaptive Designs** | [`analyze_adaptive_design()`](file:///Users/leelasdodda/Documents/Codes/local_clintrial_agent/design_agent_pipeline.py#L494-L571) | `rpact`, `adestr`, `adoptr`, `bcrm`, `dfcrm`, `ewoc` | Detects sequential, dose-escalation, and platform signals. `rpact` computes O'Brien-Fleming/Pocock boundaries. `bcrm`/`dfcrm`/`ewoc` run Continual Reassessment Method / Dose-Escalation. |
| **8. Safety / AEs** | **Ch 12 — Safety / AEs** | [`analyze_safety_adverse_events()`](file:///Users/leelasdodda/Documents/Codes/local_clintrial_agent/design_agent_pipeline.py#L573-L662) | `clinfun` | Extracts AEs and categorizes MedDRA/CTCAE grading and DSMB details. `clinfun` offers clinical trial design utilities including toxicity monitoring and safety stopping boundaries. |

---

## 🐍 Comparable Python Packages

While the R ecosystem historically has a larger collection of niche clinical trial design packages, Python has several comparable libraries for core trial workflows:

| CRAN R Package | Comparable Python Package | Category | Capabilities |
| :--- | :--- | :--- | :--- |
| `TrialSize` / `CRTSize` | `statsmodels.stats.power` | Sample Size & Power | `statsmodels` provides standard power analysis classes (e.g., `TTestIndPower`, `FTestAnovaPower`) to calculate power, sample size, and effect sizes. |
| `dfcrm` / `bcrm` / `ewoc` | `clintrials` | Dose-Finding / Phase I | `clintrials` implements Phase I dose-finding designs in Python including the Continual Reassessment Method (CRM), EffTox, and efficacy-toxicity designs. |
| `blockrand` / `carat` | `clinical-randomization` (or custom) | Randomization | Python packages or simple custom scripts can be used to generate permuted block randomization lists or implement covariate-minimization allocation. |
| `rpact` / `gsDesign` | `GroupSeq` / `rpy2` integration | Group Sequential / Adaptive | `GroupSeq` calculates boundaries for group sequential designs. For advanced adaptive designs, using `rpy2` to wrap the R package `rpact` is the industry standard. |
| *N/A (General R)* | `PyTrial` | Machine Learning in Trials | A Python-exclusive library specifically designed for AI/ML in clinical trials (e.g., patient-trial matching, outcome prediction, synthetic trial simulation). |
| *N/A (R markdown/rtables)*| `pycsr` / `polars` / `plotnine` | Clinical Reporting & CDISC | Packages and guides under `pycsr.org` facilitate creating CDISC-compliant tables and Clinical Study Reports (CSR) using Python's modern data ecosystem. |

---

## ⚡ Implemented Python-to-R Bridge Features

We have built a production-ready Python-to-R bridge module ([examples/rpy2_bridge.py](file:///Users/leelasdodda/Documents/Codes/local_clintrial_agent/examples/rpy2_bridge.py)) that exposes key CRAN packages directly to our Python pipeline using the `rpy2` library in ABI-compatible mode. 

The following R-based clinical trial features are fully implemented and verified working:

### 1. Group Sequential & Adaptive Designs (`rpact` & `gsDesign`)
* **Features:** Group sequential alpha spending boundaries (O'Brien-Fleming, Pocock), exact binomial sizing, and survival sample sizing/event calculations.
* **Bridge Methods:** `rpact_group_sequential()`, `rpact_sample_size_survival()`, `rpact_mams_simulation()`, `gsdesign_survival()`, `gsdesign_fixed_survival()`, `gsdesign_exact_binomial()`.

### 2. Dose-Finding & Phase I CRM (`dfcrm`)
* **Features:** Bayesian Continual Reassessment Method (CRM) for safety monitoring and identifying Maximum Tolerated Dose (MTD).
* **Bridge Method:** `dfcrm_crm()`.

### 3. Patient Randomization List Generator (`blockrand`)
* **Features:** Permuted block randomization list generation for trial allocation, supporting varying block sizes and custom treatment arm names.
* **Bridge Method:** `blockrand_generate()`.

### 4. Bioequivalence Sizing (`PowerTOST`)
* **Features:** Calculates sample size and achieved power for bioequivalence testing (Two One-Sided Tests / TOST) in standard designs (e.g. 2x2 Crossover).
* **Bridge Method:** `powertost_sample_size()`.

### 5. Simon's Phase II Two-Stage Designs (`clinfun`)
* **Features:** Simon's minimax and optimal two-stage designs for Phase II oncology trials (interim futility stopping rules).
* **Bridge Method:** `clinfun_simon2stage()`.

---

## 💡 Future Expansion: Non-Proportional Hazards and Multiplicity

We can continue expanding the bridge to cover more advanced scenarios:
1. **NPH Trials (`gsDesign2`):** Utilize non-proportional hazard methods (MaxCombo, weighted log-rank tests) directly in our sizing pipeline.
2. **Multi-Hypothesis Testing (`graphicalMCP`):** Maurer-Bretz alpha recycling procedures for trials with multiple primary endpoints/treatment comparisons.
