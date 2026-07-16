# Research Notes — `wei-ai-lab/clinical-trial-design`

Repository: https://github.com/wei-ai-lab/clinical-trial-design
License: Apache-2.0 · Status: pre-beta (v0.0.13, released 2026-04-29)
Languages: R 71%, TypeScript 12%, Python 9%

## Overview
A **Claude Code plugin + MCP server** for end-to-end Phase 2/3 clinical trial design. Biostatisticians and trialists design confirmatory studies through a conversational interface, with computation backed by validated R packages (`gsDesign`, `gsDesign2`, `graphicalMCP`, `simtrial`).

## Four-Layer Architecture
| Layer | Role |
|---|---|
| **R package** (`r-package/ClinicalTrialDesign`) | Pure R statistical engine wrapping/extending gsDesign, gsDesign2, graphicalMCP, simtrial behind a unified result schema |
| **MCP server** (`mcp-server/`) | Exposes R functions as typed tools over Model Context Protocol (stdio) |
| **Skill** (`skills/clinical-trial-design/`) | Domain-expert prompt; translates design briefs into tool calls; 9-step Phase 3 orchestration workflow |
| **Benchmark corpus** (`benchmarks/`) | 176 curated public-trial designs across 21 families — Markdown + YAML with expected outputs/tolerances |

Plus an `eval/` harness (11 scenarios × 6-dimension rubric) and an `examples/` gallery (5 published trials reproduced).

## Tool Surface — 9 MCP Tools

### Single-Primary Design (3)
- **`design_binary`** — event/no-event; fixed or group-sequential; backed by `gsDesign::nBinomial` / `gsDesign`
- **`design_continuous`** — mean difference; fixed or group-sequential; `gsDesign::nNormal` / `gsDesign`
- **`design_survival`** — time-to-event; PH or NPH (maxcombo/rmst/milestone/wlr/ahr); `gsDesign::nSurv`/`gsSurv` (PH) and `gsDesign2::fixed_design_*`/`gs_design_*` (NPH)

All accept `comparison ∈ {superiority, non-inferiority, equivalence}`, `alpha`, `power`, `sided`, `allocation_ratio`, group-sequential params (`k`, `timing`, `sfu`, `sfl`, `test.type`), optional `operational` block, optional `reasoning_chain` array (citation trail with `source_type` tags). `design_survival` adds `events_calc ∈ {schoenfeld (default), lachin-foulkes, freedman}` and accepts `control_hazard_rate` as alternative to `control_median`.

### Multi-Hypothesis Design (3)
- **`design_co_primary`** — two+ co-primary endpoints (PFS+OS, etc.); strategies: fixed-sequence (default), alpha-split, Bonferroni; total N = max across endpoints
- **`design_multi_population`** — same endpoint across multiple populations (subgroup + ITT); `relation ∈ {nested, disjoint}`; nested N driven by largest implied-enrolled-N, disjoint N is the sum
- **`design_graphical_multiplicity`** — Maurer-Bretz alpha recycling with initial weights + transition matrix + Rule-3 validator; `graphicalMCP::graph_create`

### Meta Tools (3)
- **`validate_against_benchmark`** — replay a benchmark case, diff vs expected within tolerance
- **`verify_design`** — Monte Carlo cross-check under H0/H1; ±2 pp power / ±0.5 pp Type I gate
- **`design_report`** — render design summary as markdown, Word (`officer`), or PDF (`rmarkdown`+Pandoc); reasoning chain → Word table; sponsor-confidential entries surface redaction warning

## Operational Kernel
Every endpoint tool accepts an `operational` block solving:
- `accrual_rate × accrual_duration = sample_size_total`
- `total_trial_duration = accrual_duration + follow_up_duration`
- `target_events = sample_size_total × cumulative_event_rate(...)` (survival; via `uniroot` over closed-form pooled exponential-PH)

Supply 0–4 of `{accrual_rate, accrual_duration, follow_up_duration, total_trial_duration}` + optional caps `{max_n, max_duration}`. Solver fills missing values with audit trail (`given`/`derived`); cap violations → structured `feasibility_warnings`.

## Supported Design Families
- Fixed binary / continuous / TTE — ✅ (super / NI / equivalence as applicable)
- Group-sequential binary / continuous / TTE — ✅
- Multi-hypothesis: co-primary, multi-population, graphical — ✅
- Adaptive (SSR, enrichment, selection), MAMS / platform / basket / umbrella — ⏳ roadmap (corpus cases exist)

## Quick Start
Prereqs: R ≥ 4.2, Node ≥ 18. CRAN deps (one-time):
```r
install.packages(c("gsDesign","gsDesign2","graphicalMCP","jsonlite","officer","rmarkdown"))
```
Install plugin (Claude Code):
```
/plugin marketplace add wei-ai-lab/clinical-trial-design
/plugin install clinical-trial-design@wei-ai-lab
```
Or host shell: `claude plugin marketplace add ...` / `claude plugin install ...`. Restart Claude Code after install.

Standalone MCP server (any MCP client): `npx clinical-trial-design@latest`

### Environment overrides
MCP server auto-discovers `Rscript` in common locations. Override via:
- `DESIGNR_RSCRIPT=/full/path/to/Rscript`
- `DESIGNR_LAUNCHER=/full/path/to/launcher.R`

For sandboxed hosts (Posit Workbench, RStudio Server, VS Code Remote), set env in `~/.claude/settings.json` rather than `~/.bashrc`.

## Testing & Quality
- 288/288 testthat (R package)
- 18/18 MCP smoke tests
- CI release-gate (`.github/workflows/release-gate.yml`): R tests + R CMD check + MCP build/smoke + scenario validation
- Security gate (`.github/workflows/security-grep.yml`): forbids disk writes / network calls (`writeLines`, `download.file`, `httr::`, `fetch`, etc.) — statelessness as a *design property*; confidential trial inputs never leave the conversation

## Relevant to This Project
`local_clintrial_agent` performs trial *analysis* (eligibility, power, design classification, masking) from ClinicalTrials.gov structured data using a local LLM. `clinical-trial-design` performs *prospective design* (sample-size / power / boundaries) via validated R packages behind an MCP server. The two are complementary:
- Our `design_agent_pipeline.py` computes power algorithmically (textbook formulas); `clinical-trial-design` uses the same underlying R packages (`gsDesign`, `gsDesign2`) for group-sequential and NPH designs we currently don't cover.
- Their operational kernel (accrual ↔ duration ↔ N solver) is more general than our current power analysis.
- Their `verify_design` Monte-Carlo convention (±2 pp power / ±0.5 pp Type I) is a credible verification floor we could adopt.
- Potential integration: expose `clinical-trial-design` as an MCP tool within this agent's pipeline for prospective-design use cases.

## Tested Dependency Versions (v0.0.13)
| Layer | Dependency | Version |
|---|---|---|
| R runtime | R | 4.5.3 (≥ 4.2) |
| R imports | `gsDesign` | 3.9.0 |
| | `gsDesign2` | 1.1.8 |
| | `graphicalMCP` | 0.2.9 |
| | `jsonlite` | 2.0.0 |
| R suggests | `officer` / `rmarkdown` / `simtrial` / `rpact` / `yaml` / `testthat` | various |
| Node | Node | 22.22.1 (≥ 18) |

## Related Work
[`RConsortium/pharma-skills`](https://github.com/RConsortium/pharma-skills) — complementary R Consortium skill collection for survival group-sequential designs with local R session + `lrsim()` simulation. `clinical-trial-design` is broad + MCP-native (no local R session); `pharma-skills` is local-session + simulation-gated. Both use the same Monte-Carlo verification tolerance convention.

---

# Research Notes — `adityashukla8/clinicaltrials-multiagent`

Repository: https://github.com/adityashukla8/clinicaltrials-multiagent
License: none specified · Status: hackathon-style demo (no releases, no tests) · 7 stars
Languages: Python 99%, Dockerfile
Frontend: separate repo [`adityashukla8/project-qhm7lvsowfqcd1xv1a2up`](https://github.com/adityashukla8/project-qhm7lvsowfqcd1xv1a2up)

## Overview
"Criteria-AI" — a Python multi-agent system (LangGraph + Google Gemini 2.5 Flash) for **patient-to-trial matching** and **eligibility-criteria optimization to boost recruitment**. Operational/oriented, not statistical — the third leg of the trial-lifecycle triangle relative to this repo (analysis) and `clinical-trial-design` (sizing).

## Architecture
LangGraph `StateGraph` over a shared `AgentState` TypedDict, exposed via FastAPI. Two workflows:

**1. `flows/full_trial_match.py`** — 4 nodes + 1 conditional edge
```
get_patient_info → fetch_trials → llm_evaluation
                                   ├─ (matched)   → generate_summary_cards → END
                                   └─ (no match)  → skip_summary_cards   → END
```

**2. `flows/protocol_optimization_workflow.py`** — 3 sequential nodes
```
age_optimization_agent → biomarker_optimization_agent → protocol_optimization_summary_agent
```
Note: the two optimization agents run *sequentially*, not in parallel — the supervisor waits for both.

## Agents (in `agents/`)

| Agent | File | Role | LLM? |
|---|---|---|---|
| Patient | `patient_agent.py` (`get_patient_info_tool`) | Fetch patient from AppWrite DB; build `{age, diagnosis, treatment_history, country, gender, ecog_score, biomarker, metastasis, radiotherapy, histology, condition_recurrence}` | No |
| Trial discovery | `trial_discovery_agent.py` (`return_trial_info_tool`) | Call ClinicalTrials.gov v2 API with patient diagnosis as `query.cond`; **hardcoded filter**: `AREA[Phase](PHASE4 OR PHASE3) AND AREA[LocationCountry](United States)` + `filter.overallStatus=RECRUITING`; max 10 studies | No |
| Eligibility | `eligibility_agent.py` (`evaluate_trials_llm`) | Per-trial Gemini prompt → `{match_criteria, reason, match_requirements}`. Prompt includes: *"If more info is needed, assume the patient meets requirements, you can be a little flexible"* — **bias toward matching** (false-positive risk) | Yes (Gemini 2.5 Flash, `thinking_budget=0`, `temperature=0.1`) |
| Summary card | `clinical_trials_summary_agent.py` (`get_trial_summary_card`) | **18 parallel Tavily web searches per matched trial** via `ThreadPoolExecutor`: official_title, sponsor, locations, enrollment, side effects, patient experiences (Reddit/cancerforums), statistical plan, sample_size, monitoring_frequency, DSMB, safety_documents, patient_faq_summary, etc. Writes aggregated card to AppWrite | No (web search only) |
| Age optimization | `protocol_optimization_age_agent.py` | **Deterministic** age-bucket counting vs trial min/max age → eligible/missed/missed_upper/missed_lower + suggested bounds; LLM wraps the metrics into a structured clinical summary JSON | Mixed (compute + LLM-narrate) |
| Biomarker optimization | `protocol_optimization_biomarker_agent.py` | Counts biomarker distribution across patient DB via `Counter`; sends to LLM with trial eligibility text → suggested revised criteria + % gain estimate. **Does NOT parse numeric thresholds from criteria** — LLM-driven suggestion, no real threshold simulation | Yes (Gemini, `temperature=0.3`) |
| Supervisor summary | `protocol_optimization_summary_agent.py` (`protocol_optimization_summary`) | Combines age + biomarker results, compares against original trial criteria, writes unified optimization report to AppWrite | Yes (Gemini, `temperature=0.3`) |
| Synthetic data | `synthetic_data_agent.py` | Generates synthetic cancer patient profiles (70% USA, matching DB schema) via Gemini, writes to AppWrite for demoing | Yes (Gemini, `temperature=0.3`) |

## Tools (in `tools/`)
- `appwrite_client.py` / `appwrite_get_all_patients.py` / `appwrite_write_trial_info.py` / `appwrite_metrics.py` — AppWrite DB CRUD (patients, trial summaries, matches, optimizations, metrics)
- `trial_api.py` (`fetch_clinical_trial_data`) — ClinicalTrials.gov v2 with `nextPageToken` pagination
- `single_trial_search.py` (`fetch_trial_details_by_nct_id`) — single-trial fetch, returns title/status/phases/conditions/interventions/eligibility/sex/min-max-age/locations
- `tavily_search.py` — wraps `TavilyClient.search(include_answer=True)`; returns `{summary, citations}`
- `clinical_trials_match.py` (`match_trials`) — entry point: runs full workflow, inserts each match to AppWrite
- `run_protocol_optimization_workflow.py` — orchestrates the optimization workflow

## API Surface (FastAPI `main.py`)
| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | health |
| `/patients` · `/patients/{id}` | GET | list / fetch patient |
| `/trial_info` | POST | patient_id → matched trials (criteria/reason/match_requirements) |
| `/matchtrials` | POST | run full matching workflow, persist to AppWrite |
| `/all_trials` | GET | list all stored trial summary cards |
| `/metrics` | GET | AppWrite DB metrics |
| `/search-protocols` · `/search-protocols/{trial_id}` | GET | stored optimization reports |
| `/optimize-protocol` | POST | trial_id → run optimization workflow |

## Code-Quality Observations (from reading source)
- `from ipdb import set_trace as ipdb` imported across **most files** — leftover interactive-debugger artifact, not production-ready
- Hardcoded GCP project `ai-in-action-461412` + `vertexai=True` embedded in agent source
- Hardcoded model `gemini-2.5-flash`, no model-config layer
- Gemini safety settings all disabled (`threshold="OFF"`) in the eligibility agent — and empty `[]` in others
- LLM-output parsing is a brittle regex strip of ` ```json ` fences + bare `json.loads`; only some agents wrap in try/except
- The eligibility prompt's "be a little flexible / assume the patient meets requirements" line biases toward false-positive matches — concerning for a clinical tool
- Biomarker agent counts distribution but does **not** parse numeric thresholds from the eligibility text, so its "gain_estimate" is an LLM guess, not a simulation
- Phase 3/4 + US-only + recruiting filter is hardcoded — restrictive
- No authentication, rate limiting, or input validation beyond Pydantic request models
- No tests, no linting, no type checking (only `TypedDict` state schemas)
- Patient data model is cancer-specific (chemo/radiotherapy/biomarker/metastasis/histology/ecog) — not generalizable to non-oncology without schema change

## Comparison to This Repo

| Dimension | `clinicaltrials-multiagent` | `local_clintrial_agent` (this repo) |
|---|---|---|
| Goal | **Patient-to-trial matching** + eligibility widening for recruitment | **Protocol design assessment** (power, masking, randomization, adaptive, safety) |
| Orientation | Operational / recruitment | Statistical / methodological |
| LLM | Hosted Gemini 2.5 Flash | Local Ollama `gemma2:2b-instruct-q4_K_M` |
| LLM role | Eligibility match/no-match + narrative summaries | Eligibility classification into Safety/Statistical Power/Feasibility |
| Orchestration | LangGraph `StateGraph` (typed-state multi-agent, conditional edges) | Single-file sequential pipeline |
| API | FastAPI (8 endpoints) + AppWrite persistence | CLI (`design_agent_pipeline.py`), JSON output |
| Patient data | AppWrite DB (cancer-specific schema) + synthetic generator | None |
| Trial source | CT.gov v2 by diagnosis + Phase3/4/US/recruiting filter | CT.gov v2 by NCT ID |
| Enrichment | 18 parallel Tavily web searches per trial (incl. Reddit/cancerforums) | API structured fields only |
| Power / stats | ❌ none | ✅ dichotomous + survival (Schoenfeld) + Phase 1 N/A |
| Protocol optimization | Age-range widening + biomarker-threshold relaxation (enrollment yield) | ❌ |
| Tests / CI | ❌ | ❌ |

**Where they overlap:** both parse ClinicalTrials.gov eligibility criteria with an LLM. Their "protocol optimization" (simulating relaxed age/biomarker thresholds to estimate enrollment yield) is conceptually adjacent to our `analyze_study_population()` recruitment-yield estimate — but they go further into actionable criterion rewriting, while we stop at assessment.

**What we could borrow:**
- The LangGraph typed-state multi-agent pattern — a cleaner orchestration shape than our single-file sequential pipeline, and would let individual analysis steps (design, endpoints, power, masking, adaptive, safety) become parallel/fan-in nodes
- The Tavily enrichment idea (web search for sponsor/side-effects/statistical plan beyond what the API exposes) — though with stricter source curation than Reddit
- The synthetic-patient generator pattern, if we ever want to simulate enrollment-yield against our assessed trials
- Their FastAPI surface, if we ever want to expose our pipeline as a service

**Caveats:** their codebase is hackathon-grade (ipdb imports, hardcoded GCP project, brittle JSON parsing, match-bias prompt, no tests). Borrow *patterns*, not code.

---

# Curated Landscape — `github.com/topics/clinical-trials` (699 repos)

Source: https://github.com/topics/clinical-trials (sorted by stars). Filtered to repos relevant to **trial design & optimization**; CTMS/EDC/survey/awesome-list infra omitted unless directly relevant.

## Tier 1 — Directly relevant to design / optimization / our pipeline

### `genomoncology/biomcp` — 548★ · Rust · Apache-2.0
**BioMCP: Biomedical Model Context Protocol.** An MCP server bridging biomedical data sources (PubMed, PubMed Central, clinical trials, genomics) to LLM agents. Same MCP-native philosophy as `wei-ai-lab/clinical-trial-design`, but oriented toward *data retrieval* (literature + trials + variants) rather than *statistical design*. **Relevance:** could serve as the MCP-native layer for the trial-discovery + literature-enrichment steps we currently do with hand-rolled CT.gov API calls and no PubMed access. Updated Jul 16 2026.

### `futianfan/clinical-trial-outcome-prediction` — 165★ · Python · Cell Patterns 2022
**HINT (Hierarchical Interaction Network)** — deep-learning model predicting clinical-trial approval probability across Phases 1–3. Ships the **TOP benchmark dataset** (drug + disease + protocol/eligibility criteria features), trained models, and tutorials. **Relevance:** the only repo here that *predicts trial success* from protocol features — a natural complement to our power analysis (which computes detectable effect from N) and `clinical-trial-design` (which sizes N for a target effect). HINT answers "will this trial succeed?" from a learned historical distribution. Non-commercial use only. Same lab (Sunlab) as PyTrial.

### `Keiji-AI/PyTrial` — 127★ · Python · BSD-2 · ⚠️ unmaintained
**Comprehensive AI-for-drug-development platform** (Sunlab). Unified `fit/predict/save/load` API across six trial tasks. Last release v0.0.6 (Jun 2023); 4 open issues, 6 open PRs, no release cadence since. Heavy ML dependency stack (rdkit, transformers, ctgan, transtab, promptehr, trial2vec, accelerate). Python 3.7 target — version-skew risk on our 3.12 stack. The HINT TOP benchmark dataset is **non-commercial use only** (separate from PyTrial's BSD-2 license). Despite staleness, it remains the most complete open-source ML toolkit spanning the trial lifecycle. Recommend borrowing *patterns and specific modules* rather than adding as a dependency.

See full in-depth analysis below: [PyTrial Deep Dive](#pytrial-deep-dive).

### `cyanheads/clinicaltrialsgov-mcp-server` — 81★ · TypeScript · Apache-2.0
**MCP server wrapping the ClinicalTrials.gov REST API v2** with 7 typed tools: `search_studies`, `get_study_record`, `get_study_count`, `get_field_values`, `get_field_definitions`, `get_study_results` (outcomes/AEs/participant-flow/baseline; optional ~200KB→5KB summary mode), `find_eligible` (patient demographic matching to recruiting trials). Also ships an `analyze_trial_landscape` prompt and a `clinicaltrials://{nctId}` resource. Public hosted instance + stdio/HTTP transports + Zod schemas + OpenTelemetry. **Relevance:** this is the production-grade, MCP-native version of what our pipeline and Criteria-AI both do with hand-rolled `requests.get()` against CT.gov v2. We could either (a) adopt it wholesale as our trial-fetch layer, or (b) mirror its tool design (especially `get_study_results` for outcomes/AEs and `get_field_values`/`get_field_definitions` for data-model discovery) in our own client. 22 releases, v2.8.2, actively maintained (Jul 9 2026).

### `jvfe/pytrials` — 61★ · Python
Thin Python wrapper around the ClinicalTrials.gov API. **Relevance:** a lighter-weight alternative to our hand-rolled API code if we don't want the MCP-server dependency of `cyanheads`. Last updated May 2024 — may lag the v2 API.

### `rpact-com/rpact` — 39★ · R · LGPL-3
**Confirmatory adaptive clinical trial design + analysis.** The de facto industry-standard R package for adaptive designs (inverse-normal + Fisher combination tests, MAMS drop-the-losers, biomarker enrichment, delayed-response, count data, boundary recalculation) — capabilities gsDesign (issue #11) lacks. **LGPL-3** (vs gsDesign's GPL-3): linking from our Python pipeline via rpy2 is license-clean. Backed by RPACT GmbH (paid GxP validation tier; free OSS package fully functional). Per the official rpact-vs-gsDesign comparison vignette, GS survival power/boundaries match gsDesign to 3 decimals — so for the GS-power slice it's a license + API-ergonomics choice, not a numerical one. Already mapped to our `analyze_adaptive_design()` in `cran_task_view_mapping.md`. See full analysis: [rpact Deep Dive](#rpact-deep-dive).

### `cbib/TrialMatchAI` — 31★ · Python · MIT
**End-to-end patient-to-trial matching system** (Nature Communications 2026, Abdallah et al., DOI 10.1038/s41467-026-70509-w). Production-grade: v0.6.0 Jul 13 2026, 231 commits, 377 tests, uv + ruff + pre-commit + pip-audit, 10 releases. Two-stage architecture: build (corpus embeddings + biomedical entity annotations + parsed eligibility constraints + LanceDB hybrid search index), match (patient → retrieve → rerank → per-criterion eligibility reasoning → ranked HTML report). Beats TrialGPT (Jin et al., Nature Comms 2024) on TREC Clinical Trials 2021+2022 benchmark. Patient inputs: free text, FHIR R4, GA4GH Phenopacket, OMOP CDM. Clinical embedders (MedCPT, PubMedBERT) beat general ones (bge-m3, Qwen3) at retrieval. **Most directly relevant to our eligibility-criteria work:** ships a deterministic, no-LLM, regex-based eligibility-constraint extractor (`constraints/extraction.py`) that parses criteria text into typed `Constraint` objects (age, sex, ECOG, labs, biomarkers, prior therapy, temporal windows) with comparators (eq/gt/ge/lt/le/between/present/positive/negative/mutated/wildtype/prior), normalized codes, evidence spans, confidence — pure Python + pydantic, zero heavy deps, MIT-clean. This is the rigorous version of what our LLM criteria-classification step does loosely. See full analysis: [TrialMatchAI Deep Dive](#trialmatchai-deep-dive).

## Tier 2 — Adjacent / analytical / evidence-synthesis

### `ijmarshall/robotreviewer` — 177★ · Python
Automatic synthesis of RCTs — bias-risk assessment and systematic-review automation (Cochrane/ICASR-aligned). **Relevance:** our pipeline assesses *single-trial* design quality; RobotReviewer assesses *cross-trial* bias for evidence synthesis. Different problem, but its bias-detection ML could inform a future "trial quality" scorecard beyond our current power/masking/randomization checks. Last updated Jul 2022 (likely stale).

### `htlin222/meta-pipe` — 108★ · Python
Claude Code-powered end-to-end **meta-analysis automation**: AI-assisted literature review, screening, extraction, analysis, and manuscript generation for systematic reviews. **Relevance:** a Claude-Code-plugin peer (like `clinical-trial-design`). Adjacent to our trial-assessment focus — meta-pipe synthesizes *across* trials, we assess *within* a trial. Updated Jul 3 2026.

### `pharmaverse/admiral` — 310★ · R · CDISC ADaM
ADaM in R Asset Library — builds CDISC-compliant analysis datasets for clinical trials. **Relevance:** the regulatory-standard analysis-dataset layer. If we ever need to align our outputs with submission-grade CDISC ADaM structure, admiral is the reference implementation. Maintained by the pharmaverse consortium. Updated Jul 14 2026.

### `insightsengineering/teal` — 264★ · R
Exploratory Shiny web apps for analyzing clinical trial data. **Relevance:** a model for how to expose trial-analysis interactively (vs. our batch JSON output). From the NEST/Roche insightsengineering org. Updated Jul 13 2026.

### `insightsengineering/tern` — 105★ · R
Tables, Listings, and Graphs (TLG) library — standard clinical-trial output generation. **Relevance:** if we ever need submission-style TLG outputs. Same org as teal. Updated Jul 16 2026.

### `sebasquirarte/biostats` — 86★ · R · MIT
Biostatistics toolbox (14 functions across descriptive stats, sample size, inference, viz) from Laboratorios Sophia. **Relevance:** its `sample_size()` supports NI/equivalence/superiority for mean + proportion outcomes (Chow 2017 formulas) — broader hypothesis-test types than our superiority-only power analysis, but fixed-sample only (no survival, no group-sequential). MIT-licensed (more permissive than gsDesign's GPL-3). See full analysis below: [biostats Deep Dive](#biostats-deep-dive).

### `Merck/metalite.ae` — 26★ · R · GPL-3
**Adverse-event analysis for clinical study reports** (Merck). Part of the `metalite` ecosystem (metadata-driven ADaM analysis). Generates production-ready AE summary tables, specific-AE tables, AE listings, and exposure-adjusted event rates per the *R for Clinical Study Reports and Submission* (R4CSR) book. Ships `rate_compare()` — the Miettinen & Nurminen (1985) test for risk difference (unstratified + stratified with ss/equal/CMH weights, CI via bisection, NI/equivalence via `delta`). **Relevance: reference only, not an integration candidate.** metalite.ae operates on ADaM patient-level datasets (post-trial results analysis); we work from CT.gov protocol-level structured fields (pre-trial design assessment). `rate_compare()` tests *observed* rates (analysis direction); our power analysis needs *expected* rates (design direction) — already covered by `gsDesign::nBinomial()` (issue #11) which supports M&N for sample-size. GPL-3 (same copyleft as gsDesign, without the mRNA-1273 regulatory precedent). If we ever expand into trial-results analysis (assessing whether completed trials' AE results match design assumptions), metalite.ae is the reference. v0.1.3 CRAN Oct 2024, last push Mar 2026.

## Tier 3 — Infrastructure / standards / less central

| Repo | ★ | Lang | Why noted, why deprioritized |
|---|---|---|---|
| `cqframework/clinical_quality_language` | 320 | Kotlin | HL7 CQL spec for clinical decision support / quality measurement. Standard, but CDS/CQM is outside our design-assessment scope. |
| `QuickBirdEng/SurveyKit` · `survey_kit` | 387 / 132 | Kotlin / Dart | Android/Flutter survey libraries aligned with iOS ResearchKit. Study-conduct UI, not design. |
| `seandavi/awesome-cancer-variant-resources` | 336 | — | Awesome-list of cancer variant KBs. Reference, not tooling. |
| `philbowsher/Open-Source-in-New-Drug-Applications-NDAs-FDA` | 80 | — | Curated list of open-source (R & Python) usage cited in FDA NDA/BLA integrated review documents. Reference, not tooling. See full analysis below: [FDA NDA Open-Source References](#fda-nda-open-source-references). |
| `phoenixctms/ctsms` | 70 | Java | Phoenix CTMS — full trial-management system (EDC/CDMS/randomization/inventory). Operational, not analytical. |
| `reliatec-gmbh/LibreClinica` | 67 | Java | Open-source EDC/CDM (OpenClinica successor). Data capture, not design. |
| `opentrials/opentrials` | 65 | JS | Trial discovery/exploration app. Unmaintained (2018). |
| `dermatologist/pyomop` | 64 | Python | OHDSI/OMOP CDM data warehouse + LLM text-to-SQL + MCP. Data infrastructure, not design. |

## Synthesis — where this points for our roadmap

1. **MCP-native trial data access** is now well-covered by `cyanheads/clinicaltrialsgov-mcp-server` (CT.gov v2, 7 tools, results/AE extraction, patient matching). This supersedes both our hand-rolled client and Criteria-AI's. Worth a dedicated integration issue (complements issue #8's `clinical-trial-design` for *sizing* with a *data* layer).
2. **Trial-outcome prediction** (`futianfan/HINT`, `Keiji-AI/PyTrial`) is a capability neither we nor `clinical-trial-design` have — it predicts approval probability from protocol features. Could become a new "feasibility/success-probability" section in our per-trial JSON, complementary to power analysis.
3. **PyTrial's trial-similarity search** could strengthen our portfolio-comparison outputs (`*_comparison.json`) by grounding "similar trial" claims in a learned embedding rather than shared indication alone.
4. **CDISC ADaM alignment** (`pharmaverse/admiral`) is the path if our outputs ever need to feed regulatory submission pipelines — lower priority but worth noting.
5. The topic page confirms the **MCP-server pattern** (`biomcp`, `clinicaltrialsgov-mcp-server`, `clinical-trial-design`, `pyomop`) is the emerging standard for exposing clinical-trial capabilities to LLM agents. Our pipeline's direct-`requests` + local-Ollama approach is increasingly the exception.

---

# PyTrial Deep Dive

Repository: https://github.com/Keiji-AI/PyTrial
License: BSD-2 (package) · ⚠️ HINT TOP benchmark dataset is non-commercial-use only
Status: v0.0.6 (Jun 11 2023) · unmaintained (4 open issues, 6 open PRs) · 127★ · 26 forks
Languages: Python 100%
Paper: Wang et al., "PyTrial: Machine Learning Software and Benchmark for Clinical Trial Applications," arXiv:2306.04018 (2023)

## Package Architecture

```
pytrial/
├── data/           # data loaders + base dataset classes
│   ├── demo_data.py    # load_trial_outcome_data, load_trial_document_data, load_trial_patient_tabular, ...
│   ├── trial_data.py    # TrialDatasetBase (criteria splitting + BERT embedding), TrialOutcomeDatasetBase, TrialDatasetStructured
│   ├── patient_data.py  # TabularPatientBase
│   └── vocab_data.py    # Vocab
├── model_utils/    # shared model utilities (BERT encoder, etc.)
├── tasks/          # 6 task modules
│   ├── indiv_outcome/      # individual patient outcome prediction
│   ├── site_selection/     # trial site selection
│   ├── trial_outcome/       # trial outcome (success) prediction
│   ├── trial_patient_match/ # patient-trial eligibility matching
│   ├── trial_search/        # trial similarity search
│   └── trial_simulation/    # synthetic patient record generation
└── utils/          # trial_utils (ClinicalTrials API client), tabular_utils, trainer, mimic_utils, parallel
```

Unified API across all tasks: `model.fit(train, val)` → `model.predict(test)` → `model.save_model(dir)` / `model.load_model(dir)`. Each task defines its own input/output data classes.

## The 6 Tasks — Models & Relevance

| Task | Implemented models | Relevance to us |
|---|---|---|
| **`trial_outcome`** | LogisticRegression, XGBoost, MLP, **HINT** (Cell Patterns 2022), **SPOT** | **High** — predicts trial approval probability from `{smiles, icdcodes, criteria}`. The TOP benchmark dataset ships with it (Phase I/II/III train/test/valid splits). Adds a "will this trial succeed?" capability we lack. |
| **`trial_search`** | BM25 (commented out), Doc2Vec, WhitenBERT, **Trial2Vec** | **High** — dense-retrieval similarity over trial documents (`title, intervention_name, disease, keyword, description, criteria`). Could replace our indication-only portfolio comparison with learned embedding similarity. |
| **`trial_simulation`** | Tabular: GaussianCopula, CopulaGAN, CTGAN, TVAE, MedGAN · Sequence: RNNGAN, EVA, SynTEG, PromptEHR, KNNSampler, TWIN | **Medium** — generates synthetic patient cohorts for privacy-preserving analysis. Directly feeds issue #9's enrollment-yield simulation (synthetic cohort instead of Criteria-AI's AppWrite DB). |
| **`trial_patient_match`** | models/ subdir (ML-based matching) | Medium — patient-trial eligibility matching (Criteria-AI's problem, but ML-based vs LLM-based). |
| `site_selection` | FRAMM, PGOntropy | Low — trial site selection, outside our design-assessment scope. |
| `indiv_outcome` | causal / confidence / sequence / tabular subdirs | Low — individual patient outcome prediction from EHR data. |

## Key Code-Level Findings

### 1. `TrialDatasetBase._split_protocol` — deterministic criteria splitting
File: `pytrial/data/trial_data.py`

A deterministic, no-LLM splitter for CT.gov eligibility criteria text:
- Lowercases the protocol text, splits on newlines, strips empties
- Finds the "inclusion" and "exclusion" header lines by keyword scan
- Splits into `inclusion_criteria` (list) and `exclusion_criteria` (list)
- Then BERT-embeds each criterion sentence via `model_utils.bert.BERT` and indexes them in a `Vocab`

**Why it matters for us:** our pipeline currently passes the raw eligibility criteria block to the LLM for classification. We could port this splitting logic to run *before* the LLM node — deterministically separating inclusion from exclusion — then send only the classification task (Safety / Statistical Power / Feasibility) to the LLM. This reduces LLM token load, makes the split auditable, and aligns with our "algorithmic where possible" principle.

### 2. `load_trial_outcome_data` — HINT TOP benchmark
File: `pytrial/data/demo_data.py`

Downloads the HINT benchmark dataset (`hint_benchmark_dataset_w_date.zip` from Google Cloud Storage). Returns CSVs keyed by `phase_{I,II,III}_{train,test,valid}.csv`. Each row: `{nctid, label, smiles, icdcodes, criteria}`. `label` = trial success/failure (binary). This is the **training signal** for a trial-success-probability model.

**License caveat:** the HINT repo (`futianfan/clinical-trial-outcome-prediction`) marks this dataset as **non-commercial use only**. PyTrial's BSD-2 license covers the *code*, not the *dataset*.

### 3. `load_trial_document_data` — CT.gov snapshot
File: `pytrial/data/demo_data.py`

Downloads a preprocessed CT.gov snapshot (copy dated 2022-10-01) as a CSV from Google Cloud Storage. Alternatively, `source='clinicaltrials.gov'` triggers `ClinicalTrials().download(date=...)` to fetch a fresh copy. Returns a DataFrame with fields `['title','intervention_name','disease','keyword']` as search fields and `['description','criteria']` as context fields, tagged by `nct_id`.

**Caveat:** the demo path uses the static snapshot. For our use case we'd want the live API (which we already have via our own client), so we'd only use their *preprocessing* (field extraction + column naming), not their data source.

### 4. HINT model — trial outcome prediction
File: `pytrial/tasks/trial_outcome/hint.py`

The Hierarchical Interaction Network (Cell Patterns 2022). Input: drug molecules (SMILES → molecular graph via rdkit), diseases (ICD codes → knowledge graph), protocol (eligibility criteria → BERT embeddings). Output: phase-specific approval probability. Trained models for Phases I/II/III ship in `./save_model`.

**Dependency cost:** HINT pulls in `rdkit` (cheminformatics, non-trivial install), `transformers` (BERT), and the HINT-specific model weights. This is the heaviest module to vendor.

### 5. Trial2Vec — trial similarity search
File: `pytrial/tasks/trial_search/models/trial2vec.py`

Encodes trial documents into dense vectors for cosine-similarity retrieval. Published as a standalone package (`trial2vec` on PyPI, listed in PyTrial's requirements). Takes trial documents with fields `['title','intervention_name','disease','keyword','description','criteria']` and produces a fixed-dimension embedding. Search = cosine similarity in embedding space.

**Dependency cost:** `transformers` + `trial2vec` package. Lighter than HINT (no rdkit).

### 6. `trial_simulation` — synthetic patient generation
Files: `pytrial/tasks/trial_simulation/{tabular,sequence}/`

- **Tabular**: GaussianCopula, CopulaGAN, CTGAN, TVAE, MedGAN — generate tabular patient records from a fitted distribution
- **Sequence**: RNNGAN, EVA, SynTEG, PromptEHR, KNNSampler, TWIN — generate sequential EHR visits

**Relevance:** for issue #9's age-widening enrollment-yield simulation, we need a patient cohort. PyTrial's tabular simulators (especially CTGAN or GaussianCopula) could generate a synthetic oncology cohort from publicly available summary statistics (SEER age distributions, etc.), avoiding the need for Criteria-AI's AppWrite patient DB.

**Dependency cost:** `ctgan`, `copulas`, `rdt`, `sdmetrics`. Medium weight.

## Dependency Stack (from `requirements.txt`)

| Category | Packages | Notes |
|---|---|---|
| Core ML | `torch` (implicit), `scikit_learn`, `xgboost`, `numpy`, `pandas` | Standard |
| NLP/LLM | `transformers`, `datasets`, `gensim`, `nltk` | BERT embedding for criteria |
| Cheminformatics | `rdkit>=2022.9.1` | HINT drug-molecule encoding — heavy install |
| Synthetic data | `ctgan>=0.5.2`, `copulas`, `rdt`, `sdmetrics==0.6.0` | trial_simulation task |
| Tabular transfer | `transtab` | indiv_outcome task |
| Sequence gen | `promptehr` | trial_simulation.sequence |
| Trial embedding | `trial2vec` | trial_search task |
| Misc | `dill`, `wget`, `tqdm`, `joblib`, `networkx`, `icd10-cm`, `accelerate` | utilities |

**Total transitive dependency footprint is substantial.** Our current project is dependency-light (uv + requests + ollama client). Adding PyTrial wholesale would roughly triple the dependency tree.

## Comparison to This Repo

| Dimension | PyTrial | `local_clintrial_agent` (this repo) |
|---|---|---|
| Goal | ML toolkit for trial tasks (outcome prediction, similarity, simulation, matching) | Protocol design assessment (power, masking, randomization, adaptive, safety) |
| Approach | Deep learning / ML models trained on historical trial data | Algorithmic + local Ollama LLM |
| Trial data source | Static CT.gov snapshot (2022-10-01) or live via `ClinicalTrials` client | CT.gov v2 live API by NCT ID |
| Eligibility criteria | Deterministic split + BERT embedding | LLM classification into Safety/Power/Feasibility |
| Outcome prediction | ✅ HINT (phase-specific approval probability) | ❌ |
| Trial similarity | ✅ Trial2Vec (learned dense embedding) | ❌ (indication-only portfolio comparison) |
| Synthetic patients | ✅ CTGAN/GaussianCopula/etc. | ❌ |
| Power / stats | ❌ | ✅ dichotomous + survival (Schoenfeld) |
| Dependencies | Heavy (rdkit, transformers, ctgan, transtab, ...) | Light (uv + requests + ollama) |
| Python target | 3.7 | 3.12 |
| Maintenance | Unmaintained (v0.0.6 Jun 2023) | Active (no tests though) |
| Tests | None visible | None |

## Integration Recommendation

**Do not add PyTrial as a dependency.** It's unmaintained, targets Python 3.7, and carries a heavy transitive dependency stack that would conflict with our lightweight uv-based setup.

**Do vendor specific modules / borrow patterns** (tracked in a separate issue):
1. **HINT** (`trial_outcome/hint.py`) — vend the model + load the TOP benchmark for a `trial_success_probability` field; accept rdkit + transformers as new deps
2. **Trial2Vec** (`trial_search/models/trial2vec.py`) — vend for learned trial-similarity in portfolio comparisons; accept transformers + trial2vec deps
3. **`_split_protocol`** (`data/trial_data.py`) — port the deterministic inclusion/exclusion splitter to run before our LLM node; zero new deps
4. **CTGAN / GaussianCopula** (`trial_simulation/tabular/`) — vend for synthetic cohort generation to feed issue #9's age-widening simulation; accept ctgan deps

**License note:** PyTrial code is BSD-2 (permissive). The HINT TOP benchmark dataset is **non-commercial use only** — if we vendor HINT, we must document this restriction and ensure our usage is research/non-profit, or train a model on a commercially-licensed dataset instead.

---

# FDA NDA Open-Source References

Repository: https://github.com/philbowsher/Open-Source-in-New-Drug-Applications-NDAs-FDA
License: none specified · Status: curated reference list (README-only repo, 25 commits) · 81★ · 10 forks
Maintainer: Phil Bowsher (RStudio/Posit; rinpharma.com)

## What it is
A curated, evidence-backed list of **open-source software (R and Python) usage cited in FDA Integrated Review documents for New Drug Applications (NDAs) and Biologics License Applications (BLAs)**. Each entry links directly to the FDA review PDF on `accessdata.fda.gov` and quotes the exact text string where the reviewer references the software. Not a tool — a *regulatory-evidence corpus* showing that open-source is accepted in FDA submissions.

## Scope
- ~100+ entries spanning 2007–2026, organized by year and language (R / Python)
- Both reviewer-initiated analyses ("Clinical Data Scientist... Software: R") and Agency acceptability assessments of sponsor-submitted open-source ("Acceptable", "Yes, FDA agrees that the software and their versions used to conduct the analyses are acceptable")
- CDISC ADaM datasets (`adae.xpt`, `adsl.xpt`, `adex.xpt`, `adlb.xpt`, `ds.xpt`) are the standard input — reviewers load these into R/Python for independent verification
- R version references range from 2.7.1 (2008) to 4.3.3 (2025); Python references cite version 3
- Notable sponsors appearing: Merck, Pfizer, AstraZeneca, GSK, Novartis, Genentech, BMS, Vertex, UCB, Biogen, Janssen, BeiGene, BridgeBio, Regeneron, Merus, Dizal, Chimerix, Syndax, Madrigal, Verona Pharma, and more

## Key findings relevant to us

### 1. Open-source is regulatorily accepted for NDA/BLA review
The FDA's own reviewers routinely use R (and increasingly Python) for independent safety/efficacy verification of sponsor-submitted trial data. The Agency explicitly marks sponsor open-source submissions as "Acceptable" in multiple reviews. This is a green light for open-source-based trial analysis in regulated contexts.

### 2. `gsDesign` is cited in an FDA-reviewed protocol
The Moderna mRNA-1273 COVID-19 vaccine Phase 3 protocol (2020) states: *"The sample size is calculated using R package gsDesign (Anderson 2020)"*. This is the **same `gsDesign` package** that `wei-ai-lab/clinical-trial-design` (issue #8) wraps via MCP. Direct regulatory precedent for the statistical engine we're considering integrating.

### 3. R + Shiny is the FDA's internal reviewer platform
The 2026 analysis note calls out **OCS Analysis Studio** — FDA/CDER's internal reviewer platform built with R, Shiny, JavaScript, D3.js — as referenced in many NDAs (though the repo excludes those references to focus on sponsor-submitted open-source). This confirms the R/Shiny ecosystem as the FDA's review-tooling standard.

### 4. CDISC ADaM datasets are the universal input format
Nearly every entry references `adae.xpt`, `adsl.xpt`, `adex.xpt`, `adlb.xpt`, or `ds.xpt` — the CDISC ADaM standard datasets. Reviewers load these into R/Python for independent analysis. This reinforces `pharmaverse/admiral` (Tier 2 above) as the reference implementation if our outputs ever need to feed regulatory review.

### 5. Notable R packages cited in FDA reviews
- `gsDesign` — sample size / group sequential (Moderna mRNA-1273)
- `survival` — survival analysis (Intarcia, CDC JYNNEOS)
- `DescTools` — confidence intervals (Ipsen, Merck vaccine review)
- `ratesci` — stratified confidence intervals (Merck vaccine review)
- `PK` — pharmacokinetic AUC calculation (Heron Therapeutics)
- `adaptIVPT` — FDA-maintained IVPT bioequivalence package
- `MPN` — FDA-referenced most-probable-number package
- `iMRMC` — FDA/DIDSR multi-reader multi-case ROC analysis
- `Xpose` + `PsN` + `Pirana` — PopPK workflow (BMS)

### 6. Python is present but less common
Python appears in fewer entries (Genentech 2020, Genzyme 2021, Albireo 2021, Bayer 2021, UCB 2025, IntraBio 2024, Eiger 2020, Zevra 2024) and is often mentioned alongside R in the same review. The FDA Briefing Document for NDA #212833 (Intercept, 2023) explicitly cites "Python (Ver. 3)" for reviewer analysis. Python is accepted but R remains dominant in regulatory review.

## Why this matters for our roadmap
1. **Regulatory validation of our statistical engine choice.** If we integrate `gsDesign` (via `clinical-trial-design`, issue #8), we can point to the mRNA-1273 protocol as FDA-reviewed precedent for the same package.
2. **CDISC ADaM alignment is a future requirement** if our outputs target regulatory submission. `pharmaverse/admiral` (Tier 2) builds these datasets; this repo is the evidence that ADaM is what reviewers expect.
3. **Open-source trial analysis is not a barrier** — the FDA has accepted R/Python in NDAs for ~18 years (oldest R reference: 2007, Summer's Laboratories). Our local-LLM + algorithmic pipeline is methodologically aligned with this regulatory reality, even if we don't currently produce submission-grade outputs.
4. **R is the regulatory lingua franca.** Our pipeline is Python-based, which is accepted but less common in FDA reviews. If regulatory submission becomes a goal, an R-output layer (via `admiral` or `tern` from Tier 2) would align with reviewer expectations.

---

# gsDesign Deep Dive

Repository: https://github.com/keaven/gsDesign
CRAN: https://CRAN.R-project.org/package=gsDesign · pkgdown: https://keaven.github.io/gsDesign/
License: GPL (≥ 3) · Status: **actively maintained** (v3.10.0, Jul 3 2026) · 58★ · 13 forks · 1,178 commits
Author: Keaven Anderson (Merck & Co., Rahway, NJ) — note the Merck affiliation
Languages: R 87%, HTML 6%, RTF 4%, C 2%
Reference book: Jennison & Turnbull, *Group Sequential Methods with Applications to Clinical Trials* (Chapman & Hall/CRC, 2000)

## What it is
The foundational R package for **group sequential clinical trial design**. Computes sample size, boundaries, power, and operating characteristics for confirmatory trials with interim analyses. Based on the α/β spending-function framework from Jennison & Turnbull (2000), plus Wang-Tsiatis designs (O'Brien-Fleming, Pocock). Particular depth in time-to-event endpoints.

**This is the engine that `wei-ai-lab/clinical-trial-design` (issue #8) wraps via MCP** — `design_binary` calls `gsDesign::nBinomial`/`gsDesign`, `design_continuous` calls `gsDesign::nNormal`/`gsDesign`, `design_survival` calls `gsDesign::nSurv`/`gsDesign::gsSurv`. Understanding gsDesign's API surface directly informs what capabilities we'd gain by integrating issue #8.

**Regulatory precedent:** the Moderna mRNA-1273 COVID-19 vaccine Phase 3 protocol states *"The sample size is calculated using R package gsDesign (Anderson 2020)"* — cited in the FDA NDA open-source references above. This is the same package, by the same author (Keaven Anderson).

## Exported API (from NAMESPACE)

### Core design functions
| Function | Purpose |
|---|---|
| `gsDesign()` | Group sequential design for normal endpoints — computes boundaries, sample size, power. The central function. |
| `gsSurv()` | Group sequential design for time-to-event endpoints — solves for sample size/events given accrual, follow-up, dropout. |
| `gsSurvCalendar()` | GS survival design with **calendar-time** interim analysis timing (vs. information-time). |
| `gsSurvPower()` | Computes **power** for a fixed GS survival design — the inverse of `gsSurv()` (which solves for N). Supports "what-if" sensitivity analyses by selectively overriding parameters. |
| `nBinomial()` | Fixed-sample sample size for binary/binomial endpoints (2-arm). |
| `nBinomial1Sample()` | Single-arm binomial sample size. |
| `nNormal()` | Fixed-sample sample size for continuous/normal endpoints. |
| `nSurv()` | Fixed-sample sample size for survival endpoints — supports Lachin-Foulkes (default), **Schoenfeld**, **Freedman**, **Bernstein-Lagakos** methods. |
| `nSurvival()` | Legacy survival sample size (Lachin-Foulkes only). |
| `nEvents()` | Number of events needed for a given HR/alpha/power. |
| `nEventsIA()` | Events needed at an interim analysis. |
| `tEventsIA()` | Calendar time of an interim analysis given enrollment assumptions. |
| `eEvents()` | Expected events under exponential PH accrual/followup. |

### Boundary & summary functions
| Function | Purpose |
|---|---|
| `gsBoundSummary()` | Human-readable summary table of a design — boundaries, Z-values, p-values, HR at bounds, conditional power, spending. The primary "show me the design" output. |
| `gsBound()` / `gsBound1()` | Low-level boundary computation (C-backed via `useDynLib`). |
| `gsBValue()` | B-values (Brownian motion) at boundaries. |
| `gsDelta()` | Treatment effect at boundaries. |
| `gsHR()` | HR at efficacy boundaries. |
| `gsRR()` | Risk ratio at boundaries. |
| `gsCP()` / `gsCPz()` / `gsBoundCP()` | Conditional power at interim. |
| `gsCPOS()` / `gsPOS()` / `gsPP()` | Probability of success / predictive power. |
| `gsPosterior()` | Posterior distributions. |
| `gsDensity()` | Density function for GS designs (C-backed). |
| `gsProbability()` | Crossing probabilities for a given design. |
| `sequentialPValue()` | Sequential p-values for GS designs. |

### Spending functions (20+)
`sfLDOF` (Lan-DeMets O'Brien-Fleming, default), `sfLDPocock` (Lan-DeMets Pocock), `sfHSD` (Hwang-Shih-DeCani), `sfExponential`, `sfPower`, `sfLogistic`, `sfNormal`, `sfCauchy`, `sfBetaDist`, `sfExtremeValue`, `sfExtremeValue2`, `sfLinear`, `sfPoints`, `sfStep`, `sfTDist`, `sfTrimmed`, `sfTruncated`, `sfGapped`, `sfXG1`/`sfXG2`/`sfXG3` (Xi-Gallo conditional error spending), `spendingFunction` (base class), `sfHSD` (Hwang-Shih-DeCani).

### Binary/exact functions
| Function | Purpose |
|---|---|
| `gsBinomialExact()` | Exact binomial boundaries for rare-event/vaccine efficacy trials. |
| `toBinomialExact()` | Convert asymptotic GS survival bounds to exact binomial. |
| `binomialSPRT()` | Wald SPRT for binomial sequential testing. |
| `binomialPowerTable()` | Power table across control rates × treatment effects. |
| `ciBinomial()` | Confidence intervals for binomial risk difference/ratio/odds ratio. |
| `testBinomial()` / `simBinomial()` / `simBinomialSeasonalExact()` | Testing + simulation for binary designs. |
| `repeatedPValueBinomialExact()` / `sequentialPValueBinomialExact()` | Repeated/sequential p-values for exact binomial designs. |

### Sample-size re-estimation
| Function | Purpose |
|---|---|
| `ssrCP()` | Sample size re-estimation via conditional power (Promising Zone). |
| `Power.ssrCP()` | Power computation for SSR designs. |
| `condPower()` | Conditional power computation. |

### Output formatting
- `as_gt()` — gt table output (HTML/LaTeX)
- `as_rtf()` — RTF output (Word) via `r2rtf`
- `as_table()` — plain table output
- `xtable()` — xtable integration
- `plot()` — 6 plot types: boundaries, power, treatment effect at bounds, conditional power, spending functions, expected sample size, B-values

## Key v3.10.0 features (Jul 2026 — latest)

1. **Three-boundary designs (`test.type` 7 & 8)** — efficacy + futility + **harm** bounds simultaneously. Motivated by FDA guidance on overall survival monitoring in oncology. `sfharm` parameter controls harm-bound spending independently.
2. **Selective bound testing** — `testUpper`, `testLower`, `testHarm` parameters (scalar or length-`k` vector) to enable/disable specific bounds at specific interims. Enables futility-only early looks, deferred efficacy testing, selective harm monitoring.
3. **`gsSurvPower()`** — computes power (not N) for a fixed GS survival design. Supports calendar-time and event-driven timing, stratified designs, all test types (1–8 including harm), and "what-if" sensitivity analyses by selectively overriding an existing `gsSurv` object.
4. **Multiple survival sample-size methods** — `nSurv()`/`gsSurv()` now support Lachin-Foulkes (default), Schoenfeld, Freedman, Bernstein-Lagakos. Schoenfeld reproduces SAS PROC SEQDESIGN.
5. **Reversed HR support** — `hr > hr0` for time-to-response, safety endpoints, or reversed HR conventions.

## Dependency Stack (from DESCRIPTION)

| Category | Packages |
|---|---|
| **Depends** | R (≥ 4.1.0) |
| **Imports** | `dplyr`, `ggplot2`, `gt`, `r2rtf`, `rlang`, `tibble`, `tidyr`, `xtable`, `stats`, `graphics`, `methods`, `tools` |
| **Suggests** | `covr`, `data.table`, `gridExtra`, `kableExtra`, `knitr`, `mvtnorm`, `rmarkdown`, `rpact`, `scales`, `testthat`, `vdiffr` |
| **C code** | `src/` — `gsbound`, `gsbound1`, `gsdensity`, `probrej`, `stdnorpts` (compiled via `useDynLib`) |

Lightweight — imports are standard tidyverse + table formatting. No rdkit, no transformers, no torch. The heavy numerical work is in compiled C.

## Vignettes (18)
Notable: `gsDesignPackageOverview`, `SurvivalOverview`, `gsSurvBasicExamples`, `gsSurvPower`, `SpendingFunctionOverview`, `ConditionalPowerPlot`, `ConditionalErrorSpending`, `SelectiveBoundTesting`, `HarmBound`, `GraphicalMultiplicity`, `VaccineEfficacy`, `PoissonMixtureModel`, `MultiSeasonRareEvents`, `binomialSPRTExample`, `binomialTwoSample`, `nNormal`, `toInteger`, `GentleIntroductionToGSD`.

## Testing & CI
- R-CMD-check GitHub Actions workflow
- Codecov coverage tracking
- `testthat` unit tests (coverage >80% since v3.2.0, expanded further in v3.10.0)
- `vdiffr` visual regression testing for plots
- Snapshot tests for `as_gt()` / `as_rtf()` output stability

## Comparison to Our Pipeline

| Dimension | `gsDesign` | `local_clintrial_agent` (this repo) |
|---|---|---|
| Scope | Group sequential design (boundaries, spending, power, SSR) | Protocol assessment (design classification, power, masking, randomization, safety) |
| Survival power | ✅ Schoenfeld + Freedman + Bernstein-Lagakos + Lachin-Foulkes; GS + fixed | ✅ Schoenfeld only; fixed-sample only |
| Binary power | ✅ `nBinomial` — exact + asymptotic; risk difference/ratio/OR | ✅ Normal approximation only |
| Group sequential | ✅ 20+ spending functions, OBF/Pocock, selective bounds, harm bounds, SSR | ❌ |
| Conditional power | ✅ `gsCP`, `ssrCP`, `condPower` | ❌ |
| Exact binomial | ✅ `gsBinomialExact`, SPRT, seasonal rare-event | ❌ |
| Calendar-time designs | ✅ `gsSurvCalendar` | ❌ |
| Three-boundary (efficacy+futility+harm) | ✅ v3.10.0 `test.type` 7/8 | ❌ |
| Output | R objects → gt/RTF/xtable/plots | JSON + PNG |
| Regulatory precedent | ✅ mRNA-1273 protocol, FDA-reviewed | ❌ (not submission-targeted) |
| Interface | R function calls (or Shiny app) | Python CLI |
| Tests | testthat + vdiffr + Codecov | ❌ |

## Integration Significance

`gsDesign` is the **statistical foundation** for both `wei-ai-lab/clinical-trial-design` (issue #8) and the broader R/pharmaverse ecosystem. Our current power analysis (`analyze_sample_size()` in `design_agent_pipeline.py`) uses the Schoenfeld formula for survival and normal approximation for dichotomous — both are the *simplest fixed-sample cases* of what gsDesign offers. Specifically:

1. **Our `analyze_sample_size()` survival branch** uses `D = (Zα + Zβ)² / [p(1-p) × ln(HR)²]` — this is the Schoenfeld method, now one of four methods in `gsDesign::nSurv()`. Integrating gsDesign would add Freedman, Lachin-Foulkes, and Bernstein-Lagakos, plus group-sequential extensions (OBF spending, futility bounds).

2. **Our dichotomous branch** uses normal approximation for detectable absolute difference — this is the asymptotic case of `gsDesign::nBinomial()`, which also supports exact binomial, risk ratio, odds ratio, and non-inferiority.

3. **Group-sequential is the biggest gap.** We currently assess whether a trial *is* group-sequential (via `analyze_adaptive_design()`) but cannot compute what the boundaries *should be*. gsDesign's `gsDesign()` + `gsSurv()` + 20+ spending functions fill this gap entirely.

4. **Harm bounds (v3.10.0)** are directly relevant to oncology OS monitoring — the FDA guidance motivating this feature is the same context as our WRN/KRAS oncology portfolios.

The path to integration runs through `wei-ai-lab/clinical-trial-design` (issue #8), which wraps gsDesign (plus `gsDesign2` for NPH and `graphicalMCP` for multiplicity) behind an MCP server. Calling gsDesign directly from Python would require `rpy2` or subprocess-to-Rscript; the MCP wrapper is the cleaner route.

**License note:** gsDesign is GPL-3. If we vendor or link to it (even via MCP subprocess), GPL-3 copyleft may apply to derivative works. The `clinical-trial-design` MCP server (Apache-2.0) communicates with gsDesign via Rscript subprocess, which is generally considered a separate work — but this should be confirmed before any distribution.

---

# biostats Deep Dive

Repository: https://github.com/sebasquirarte/biostats
CRAN: https://cloud.r-project.org/package=biostats · pkgdown: https://sebasquirarte.github.io/biostats/
License: MIT + file LICENSE · Status: **actively maintained** (v1.1.2, CRAN Mar 5 2026) · 86★
Authors: Sebastian Quirarte-Justo, Angela Carolina Montano-Ruiz, Jose Maria Torres-Arellano (Laboratorios Sophia S.A. de C.V., Mexico)
Languages: R
JOSS paper: submitted (joss.theoj.org pending)
Reference: Chow, S. 2017. *Sample Size Calculations in Clinical Research.* (formulas basis for `sample_size()`)

## What it is
A compact R toolbox (14 functions across 4 domains) for biostatistics and clinical data analysis workflows. Positioned as both a professional toolkit for biostatisticians and an educational resource for researchers transitioning to R. Developed by the biostatistics team at Laboratorios Sophia (a Mexican pharmaceutical company). MIT-licensed — the most permissive license in our landscape survey.

## 14 Functions — 4 Domains

### 1. Descriptive Statistics & EDA (5 functions)
| Function | Purpose |
|---|---|
| `clinical_data()` | Simulate clinical trial datasets (subjects × visits × arms, with configurable dropout/missing rates). Useful for testing/demos — similar in spirit to PyTrial's `trial_simulation.tabular` but simpler. |
| `summary_table()` | Auto summary table with normality testing (Shapiro-Wilk or K-S w/ Lilliefors), effect size, and inferential tests for 1- or 2-group comparisons. Handles numeric + categorical. |
| `normality()` | Normality assessment: S-W (n ≤ 50) or K-S w/ Lilliefors (n > 50) + Q-Q plots + histograms + skewness/kurtosis z-scores. |
| `missing_values()` | Descriptive + visual missing value assessment. |
| `outliers()` | Tukey IQR outlier detection + visualization. |

### 2. Sample Size & Power (2 functions) — most relevant to us
| Function | Purpose |
|---|---|
| `sample_size()` | Sample size for clinical trials. Supports: one-sample / two-sample × parallel / crossover × mean / proportion × **equality / equivalence / non-inferiority / superiority**. Parameters: `alpha`, `beta`, `x1`, `x2`, `SD`, `delta`, `dropout` (exact `n/(1-dropout)` since v1.1.2), `k` (allocation ratio). Based on Chow (2017) formulas. |
| `sample_size_range()` | Computes sample sizes across a range of treatment-effect values (x1) for 70/80/90% power, with a visualization. Calls `sample_size()` internally. Equivalent to our power-curve plots. |

### 3. Statistical Analysis & Inference (2 functions)
| Function | Purpose |
|---|---|
| `omnibus()` | Omnibus tests for 3+ groups: one-way ANOVA, repeated-measures ANOVA, Kruskal-Wallis, Friedman. Auto-selects test based on assumptions (normality, homogeneity, sphericity). Post-hoc with Tukey HSD + p-value adjustment (Holm/Hochberg/Bonferroni/etc.). |
| `effect_measures()` | Odds Ratio, Risk Ratio, NNT/NNH with CIs from a 2×2 contingency table. |

### 4. Data Visualization (5 functions)
`plot_bar()`, `plot_line()`, `plot_hist()`, `plot_box()`, `plot_corr()` — publication-ready ggplot2 wrappers with minimal code.

## Key finding: `sample_size()` hypothesis-test coverage

Our `analyze_sample_size()` only does **superiority** (dichotomous via normal approximation, survival via Schoenfeld). `biostats::sample_size()` covers:

| Hypothesis type | Our pipeline | `biostats::sample_size()` |
|---|---|---|
| Equality (superiority) | ✅ dichotomous + survival | ✅ mean + proportion |
| Non-inferiority | ❌ | ✅ mean + proportion |
| Equivalence | ❌ | ✅ mean + proportion |
| One-sample | ❌ (Phase 1 returns N/A) | ✅ mean + proportion |
| Two-sample parallel | ✅ | ✅ |
| Crossover | ❌ | ✅ mean + proportion |
| Dropout adjustment | ❌ | ✅ exact `n/(1-dropout)` |
| Allocation ratio (k) | ✅ (from API arm count) | ✅ explicit `k` parameter |
| Survival / time-to-event | ✅ Schoenfeld | ❌ |
| Group-sequential | ❌ | ❌ |

**What biostats adds:** non-inferiority, equivalence, one-sample, and crossover designs for mean/proportion outcomes. **What it lacks:** survival (our Schoenfeld), group-sequential (gsDesign), and any NPH/multiplicity.

## Dependency Stack

R package, lightweight. Imports: `nortest` (Lilliefors K-S correction), standard R stats/graphics. Suggests: `cmake`/`nloptr` on Linux for source builds. No ggplot2 dependency stated in DESCRIPTION for imports, but plot functions use ggplot2. Much lighter than gsDesign or PyTrial.

## Testing & CI
- R-CMD-check GitHub Actions
- Codecov coverage
- JOSS (Journal of Open Source Software) submission in progress
- No visual regression testing (vs. gsDesign's vdiffr)

## Why it's lower priority than gsDesign (issue #11) or PyTrial (issue #10)

1. **No survival endpoints.** Our oncology portfolios (WRN, KRAS) are dominated by PFS/OS — biostats doesn't cover time-to-event.
2. **No group-sequential.** The biggest capability gap identified in issue #11; biostats is fixed-sample only.
3. **Overlaps with gsDesign.** `gsDesign::nBinomial()` and `gsDesign::nNormal()` cover the same mean/proportion space *plus* group-sequential, exact binomial, and non-inferiority. If we integrate gsDesign (issue #11 via `clinical-trial-design`), biostats' `sample_size()` is subsumed.
4. **Educational positioning.** The package is designed as a teaching tool + general biostats toolbox, not a regulatory-grade design engine.

## Where it *could* be useful

1. **Non-inferiority / equivalence power** for our TYK2 psoriasis trials (PASI-75, dichotomous). If we want a quick, MIT-licensed, R-only NI/equivalence computation without the gsDesign GPL-3 + MCP wrapper overhead, `biostats::sample_size()` is the lighter path. But this is a subset of what issue #11 Phase 2 proposes via gsDesign.
2. **`sample_size_range()`** is a clean implementation of the power-curve-across-effects visualization we already do in `power_visualization.py` — could borrow the approach for a faceted multi-power-level plot (70/80/90%).
3. **`clinical_data()`** is a simple synthetic-cohort generator (similar to PyTrial's `trial_simulation.tabular` but far lighter — no GAN/copula deps). Could feed issue #9's enrollment-yield simulation if we want a zero-dependency alternative to PyTrial's CTGAN.
4. **`summary_table()` + `normality()` + `effect_measures()`** are standard biostats utilities we don't currently produce — useful if we ever expand beyond protocol assessment into trial-results analysis.

## Integration recommendation

**Do not add as a dependency.** Its core value (NI/equivalence sample size for mean/proportion) is a subset of what gsDesign offers (issue #11), and gsDesign has regulatory precedent + group-sequential. If we want the NI/equivalence capability without the GPL-3 / MCP overhead, port the Chow (2017) formulas directly to Python (they're closed-form and simple — biostats' own R implementation is straightforward). The MIT license makes porting + attribution trivial.

**Do reference the `sample_size_range()` multi-power-level visualization pattern** if we extend `power_visualization.py` beyond single-power curves.

---

# rpact Deep Dive

Repository: https://github.com/rpact-com/rpact
CRAN: https://cran.r-project.org/package=rpact · pkgdown: https://docs.rpact.org/ · vignettes: https://www.rpact.org/vignettes/
License: **LGPL-3** (weaker copyleft than gsDesign's GPL-3 — links permitted, modifications to rpact itself must stay LGPL) · Status: **actively maintained** (v4.4.0 CRAN Mar 4 2026; dev 4.5.0.9311; last push Jul 15 2026) · 39★
Authors: Gernot Wassmer, Friedrich Pahlke (RPACT GmbH, Germany) · ORCID 0000-0001-9397-1797 / 0000-0003-2105-2582
Backed by: **RPACT GmbH** — commercial entity selling validated/GxP installation qualification, RPACT Cloud (Shiny), and SLA; the open-source package is free + LGPL-3
Monograph: Wassmer & Brannath (2025), *Group Sequential and Confirmatory Adaptive Designs in Clinical Trials*, 2nd ed., Springer. DOI 10.1007/978-3-031-89669-9
Languages: R (≥ 3.6.0), with compiled C++ via Rcpp
CRAN Task View: ClinicalTrials (in-views) · reverse-suggests: `adoptr`, `eventTrack`, **`gsDesign`** (gsDesign suggests rpact!), `simIDM`

## What it is

The most comprehensive open-source R package for **confirmatory adaptive clinical trial design and analysis**. It implements the combination-testing principle (Bauer-Kieser, inverse-normal combination) *plus* classical group-sequential spending functions, with built-in analysis-side tooling — not just planning. Designed to be GxP-validatable (RPACT sells formal validation docs for FDA/EMA corporate systems; the package ships `testPackage()` for installation qualification).

It is the **de facto industry standard** for confirmatory adaptive designs in the R/pharmaverse — and notably is the package gsDesign itself *suggests* (reverse-suggests relationship), i.e. they are complementary, not competitive.

## License: why LGPL-3 matters (vs. gsDesign GPL-3)

This is the **single most important differentiator** for our integration calculus:

| License | gsDesign (issue #11) | rpact |
|---|---|---|
| SPDX | GPL-3 | LGPL-3 |
| Linking from proprietary/closed code | ❌ (copyleft extends to combined work) | ✅ (linking permitted; only modifications to rpact itself must stay LGPL) |
| Subprocess-to-Rscript boundary | generally OK (separate work) | generally OK (separate work) |
| Vendoring / porting formulas | triggers GPL on derivatives | linking-only does **not** trigger copyleft |

For our Python pipeline, this means:
- **rpy2-importing rpact** (as a Python-linked R library) is license-clean under LGPL-3 in a way it is *not* under gsDesign's GPL-3. This removes the biggest legal risk identified in issue #11.
- **Subprocess-to-Rscript** is fine for both, but rpact is safer if we ever want in-process linking.
- **Porting the formulas** still requires attribution either way, but LGPL-3 is friendlier for derivative statistical code.

The tradeoff: rpact's commercial tier (RPACT GmbH SLA / validation docs) is what funds the open-source package. The open-source package is fully functional, but **formal FDA/GxP validation documentation is paid** — whereas gsDesign's regulatory precedent (mRNA-1273, issue #11) is "the protocol cites the open-source package directly." For our *analysis* (not regulatory submission) use case, the missing paid validation is not a blocker.

## Functional range — what rpact covers (and gsDesign doesn't)

### Shared with gsDesign (group-sequential core)
- `getDesignGroupSequential()` — OBF/Pocock alpha-spending (`asOF`, `asP`), Wang-Tsiatis, fixed, user-defined spending functions; one- or two-sided
- `getSampleSizeMeans/Rates/Survival()` + `getPowerMeans/Rates/Survival()` — means, rates (binary), survival; Schoenfeld + other event-count formulas for survival
- `getConditionalPower()`, `getConditionalRejectionProbabilities()`
- Piecewise-exponential survival, staggered accrual, dropout

### rpact-only (beyond gsDesign)
| Capability | rpact function | Why it matters for us |
|---|---|---|
| **Inverse-normal combination test** | `getDesignInverseNormal()` | Required for data-driven sample-size re-estimation (SSR) with Type I control. gsDesign's GS method does *not* control Type I under SSR; the combination test does. Confirmed in the survival planning vignette (GS method → 3.52% Type I, inverse-normal → 2.55%). |
| **Fisher combination test** | `getDesignFisher()` | Alternative combination function for adaptive designs |
| **Multi-arm multi-stage (MAMS)** | `getSimulationMultiArmMeans/Rates/Survival()` | Drop-the-losers, treatment selection at interim, closed combination test. Applies to platform / basket oncology designs (our KRAS portfolio is multi-arm). |
| **Enrichment designs** | `getSimulationEnrichmentMeans/Rates/Survival()` | Subpopulation selection at interim (biomarker-positive subgroups). Directly relevant to our WRN/KRAS biomarker-driven portfolios. |
| **Delayed response designs** (Hampson & Jennison 2013) | documented in `rpact_delayed_response_designs` vignette | Handles the common oncology reality that the endpoint matures after the decision point. |
| **Count data** (negative binomial) | `getSampleSizeCounts()`, `getPowerCounts()`, `getSimulationCounts()` | Rate-based endpoints with overdispersion (e.g. exacerbation counts). Neither gsDesign nor biostats cover this. |
| **Automatic boundary recalculation** | `rpact_boundary_update_example` vignette | Recomputes OBF/Pocock bounds when observed information rates deviate from planned (under-/over-running). Critical for real-world interim analyses that don't hit the planned IA fraction exactly. |
| **Repeated confidence intervals + repeated p-values** | `getRepeatedConfidenceIntervals()`, `getRepeatedPValues()` | Stage-wise inference throughout the trial, not just at the final look |
| **Final confidence interval + p-value** | `getFinalConfidenceInterval()`, `getFinalPValue()` | Confidence intervals that respect the sequential testing (naive CIs are biased) |
| **Closed combination / conditional Dunnett** | `getClosedCombinationTestResults()`, `getClosedConditionalDunnettTestResults()`, `getDesignConditionalDunnett()` | Multi-arm testing with closed testing procedure |
| **Stagewise test actions / stage results** | `getTestActions()`, `getStageResults()` | Analysis-side decision logging |
| **Accrual time/intensity helpers** | `getAccrualTime()`, `getNumberOfSubjects()`, `getEventProbabilities()` | Flexible staggered accrual specification (the vignette shows 4 different accrual-specification modes) |

### gsDesign-only (rpact lacks)
- `gsBinomialExact` / SPRT — **exact binomial** designs for rare events (vaccine efficacy)
- `test.type` 7/8 three-boundary designs (efficacy + futility + **harm**) — the FDA oncology OS-monitoring harm-boundary feature (gsDesign v3.10.0, issue #11 Phase 3)
- `gsSurvCalendar` — calendar-time (vs. information-fraction) interim timing
- `gsSurvPower()` — inverse problem (fixed N → power), though rpact's `getPowerSurvival()` covers the same use case via a different entry point

So the picture is **mostly complementary**: rpact leads on adaptive/multi-arm/enrichment/analysis-side, gsDesign leads on exact-binomial/harm-bounds/calendar-time. Both cover the GS spending-function core.

## API surface — the 3-step pattern

rpact's API follows a consistent `getDesign*() → getSampleSize*/getPower* → getSimulation*` pattern, with `getAnalysisResults()` for the analysis side:

```
# 1. Define the design (boundaries)
design <- getDesignGroupSequential(
    sided = 1, alpha = 0.025, beta = 0.2,
    informationRates = c(0.33, 0.7, 1),
    typeOfDesign = "asOF"           # OBF alpha-spending
)

# 2. Compute sample size / power for an endpoint
getSampleSizeSurvival(design,
    lambda1 = ..., lambda2 = ...,   # or hazardRatio
    accrualTime = ..., dropoutRate1 = 0.05, dropoutTime = 12,
    typeOfComputation = "Schoenfeld"
)

# 3. (Optional) Verify by Monte-Carlo simulation
getSimulationSurvival(design, ..., maxNumberOfIterations = 10000, seed = ...)
```

The same 3-step shape applies to means, rates, counts, multi-arm, and enrichment. This is **cleaner than gsDesign's monolithic `gsSurv()` / `nBinomial()`** and easier to wrap from Python.

For adaptive analysis (the part gsDesign doesn't do): `getAnalysisResults(design, dataSample, dataStageResults)` produces repeated CIs, repeated p-values, conditional power, and final CIs/p-values.

## rpact vs gsDesign — the official comparison

rpact ships a dedicated vignette "Comparing Sample Size and Power Calculation Results for a Group Sequential Trial with a Survival Endpoint: rpact vs. gsDesign" (`rpact_vs_gsdesign_examples`). Headline result for a 3-look PFS design (HR=0.75, piecewise-exponential control, OBF spending, 1405 subjects):

| Stage | gsDesign Z | rpact Z | gsDesign ~HR | rpact HR(t) | gsDesign month | rpact month |
|---|---|---|---|---|---|---|
| 1 (33%) | 3.7307 | 3.731 | 0.5162 | 0.516 | 27 | 26.79 |
| 2 (70%) | 2.4396 | 2.440 | 0.7431 | 0.743 | 39 | 38.62 |
| 3 (final) | 2.0001 | 2.000 | 0.8158 | 0.816 | 51 | 50.80 |

**Boundaries match to 3 decimals; analysis times match to ~0.0001 months.** The only difference is a slight inflation-factor discrepancy (385.05 vs 385.88 events) that the vignette explicitly notes "has definitely no consequences in practice." For our assessment purposes, **rpact and gsDesign give identical GS power/boundaries** — the choice is license + adaptive-coverage + API ergonomics, not numerical accuracy.

## Dependencies

| Role | Packages |
|---|---|
| Depends | R ≥ 3.6.0 |
| Imports | `methods`, `stats`, `utils`, `graphics`, `tools`, `rlang`, `R6` (≥ 2.5.1), `knitr` (≥ 1.19), `Rcpp` (≥ 1.0.3) |
| LinkingTo | `Rcpp` (compiled C++) |
| Suggests | `ggplot2` (≥ 3.5.0), `testthat` (≥ 3.0.0), `rmarkdown` (≥ 1.10), `rappdirs` (≥ 0.3.3) |

Notably **lighter than gsDesign** (no dplyr/gt/r2rtf/xtable); ggplot2 is optional (suggests). The compiled C++ via Rcpp is the only non-pure-R piece. No system-level C/Fortran dependencies beyond a working R toolchain.

## Vignette library — 31 vignettes

The richest documentation in the landscape. Categories (from the vignette index):
- **Analysis (6)** — analysis of GS survival, multi-arm rates, continuous w/ covariates, two-arm adjusted means from raw data
- **Planning (17)** — boundaries, binary/rates, continuous/means, survival (×4 incl. promising zone, simulation-based NPH, vs gsDesign), delayed response, count data, MAMS, enrichment, futility bounds, sample-size reassessment, boundary recalculation
- **Power simulation (9)** — simulation-based operating characteristics for all endpoint types + multi-arm
- **Utilities (10)** — ggplot2 enhancement, summary factories, generics, installation qualification, hidden features, accrual time

The **installation qualification vignette** (`rpact_installation_qualification`) + `testPackage()` are unique — formal IQ documentation for regulated environments, even in the free package. The paid RPACT SLA adds OQ/PQ.

## Why it's higher priority than biostats, comparable to gsDesign

1. **License.** LGPL-3 removes the GPL-3 copyleft risk that gates issue #11. If we go the rpy2/in-process route, rpact is license-clean; gsDesign is not.
2. **Adaptive coverage gsDesign lacks.** Our `analyze_adaptive_design()` *detects* sequential, dose-escalation, and platform signals but computes nothing. rpact's inverse-normal combination + MAMS + enrichment + delayed-response + boundary-recalculation directly map to the adaptive-design categories our detector flags. This is the single biggest capability gap after group-sequential power.
3. **Multi-arm / platform relevance.** Our KRAS portfolio (NCT06625320, NCT04303780) is multi-arm; rpact's MAMS simulation with drop-the-losers + closed combination test is the matched tool. gsDesign has no MAMS.
4. **Biomarker enrichment.** Our WRN portfolio is biomarker-defined (WRN-deficient tumors); rpact's enrichment-design simulation is the only open-source tool we've found for it.
5. **API ergonomics for Python wrapping.** The `getDesign*() → getSampleSize*() → getSimulation*()` 3-step pattern is uniform across endpoints, vs gsDesign's per-endpoint monolithic functions. Easier to wrap behind a small Python adapter.
6. **Analysis-side capability.** rpact is the only package in the landscape that does both design *and* analysis (repeated CIs, conditional power, final CIs). If we ever expand from protocol assessment into trial-results analysis, rpact is the path.

### Why it's not a slam-dunk replacement for issue #11
1. **No exact binomial / rare-event designs.** Vaccine-efficacy and rare-AE trials need `gsBinomialExact` (gsDesign only).
2. **No harm-boundary `test.type` 7/8.** The FDA oncology OS-monitoring three-boundary feature (issue #11 Phase 3) is gsDesign-only. rpact's futility bounds are conventional (non-binding), not the harm-specific third boundary.
3. **No mRNA-1273-style regulatory precedent.** gsDesign is cited in an FDA-reviewed NDA protocol; rpact is widely used in pharma but the open-source citation precedent we have is gsDesign.
4. **Commercial validation tier.** The free rpact package works, but formal GxP validation docs are paid (RPACT SLA). For *analysis* (not submission) this is fine; for prospective regulatory design it's a consideration.

## Integration recommendation

**Strong candidate to elevate alongside (or partially ahead of) gsDesign (issue #11).** The license advantage + adaptive/multi-arm/enrichment coverage + API ergonomics make rpact the better fit for our *assessment* use case (we flag adaptive designs but compute nothing). gsDesign remains the better fit for the *exact-binomial / harm-boundary / regulatory-precedent* slice.

Concretely:
- **For GS survival power + boundaries on our oncology portfolios** (issue #11 Phase 1): rpact and gsDesign give identical results (per the official comparison vignette). Use rpact to avoid the GPL-3 boundary question entirely.
- **For adaptive-design assessment** (multi-arm, enrichment, SSR, boundary recalculation): rpact is the only open-source option. Open a dedicated issue.
- **For harm bounds + exact binomial**: keep gsDesign (issue #11 Phase 3), accepting the GPL-3 subprocess boundary is "generally a separate work."
- **For Python integration**: rpact's uniform `getDesign*() → getSampleSize*() → getSimulation*()` pattern is more amenable to a small typed Python adapter than gsDesign's heterogeneous API. An MCP wrapper in the spirit of `clinical-trial-design` (issue #8) but targeting rpact would be a clean contribution — and LGPL-3 makes the wrapper's own license choice unconstrained.

**Decision point:** does the LGPL-3 license + adaptive coverage move us to (a) prefer rpact over gsDesign for the GS-power slice and split issue #11 into "rpact for GS + adaptive" + "gsDesign for harm-bounds + exact-binomial only," or (b) keep issue #11 as the single GS-power issue and open a *separate* rpact issue scoped to adaptive/multi-arm/enrichment only? Recommend (b) — narrower issues are easier to scope, and the gsDesign-vs-rpact GS-power choice can be made at implementation time once we know the host R environment.

---

# TrialMatchAI Deep Dive

Repository: https://github.com/cbib/TrialMatchAI
License: **MIT** (Copyright 2024 Majd Abdallah, Macha Nikolski, Mikaël Georges — CBiB / University of Bordeaux + CNRS IBGC) · Status: **actively maintained** (v0.6.0 Jul 13 2026, 10 releases, 231 commits) · 31★ · 13 forks
Paper: Abdallah et al., "TrialMatchAI: an end-to-end AI-powered clinical trial recommendation system to streamline patient-to-trial matching," *Nature Communications* **17**, 4472 (2026). DOI 10.1038/s41467-026-70509-w
Languages: Python 97.2%, HTML 2.7%
Origin: CBiB (Centre de Bioinformatique Bordeaux) + CNRS IBGC, University of Bordeaux, France
Docs: https://cbib.github.io/TrialMatchAI/ (MkDocs Material)

## What it is

An end-to-end, production-grade **patient-to-trial matching system**. Given a patient (free-text clinical notes, FHIR R4 bundle, GA4GH Phenopacket, or OMOP CDM extract), it returns a ranked shortlist of eligible clinical trials, each explained criterion-by-criterion. Everything runs locally on a single GPU server — patient data never leaves the environment. Published in Nature Communications 2026; beats TrialGPT (Jin et al., Nature Comms 2024) on the TREC Clinical Trials 2021+2022 benchmark.

This is the **third leg of the trial-lifecycle triangle**: Criteria-AI (issue #9) does patient-matching hackathon-grade; TrialMatchAI does it production-grade + peer-reviewed; we do trial-design assessment. The task is orthogonal to ours, but the **eligibility-criteria technology is directly applicable**.

## Engineering quality — by far the highest in our landscape

| Dimension | TrialMatchAI | Criteria-AI (#9) | lingyue404/clinical-agent |
|---|---|---|---|
| Peer review | ✅ Nature Communications 2026 | ❌ | ACM BCB '24 |
| Tests | ✅ 377 tests, pytest | ❌ | ❌ |
| Packaging | ✅ PyPI (`trialmatchai`), `pyproject.toml`, uv lock, extras (llm/gpu/entity/finetune) | ❌ | ❌ (notebook) |
| Linting | ✅ ruff + pre-commit + gitleaks + pip-audit | ❌ | ❌ |
| Docs | ✅ MkDocs Material site + API reference | ❌ | ❌ |
| Releases | ✅ 10 tagged releases, semver, OIDC trusted publishing | ❌ | ❌ |
| Benchmark | ✅ TREC CT 2021+2022, recall@k, nDCG@10, P@10 | ❌ | ❌ |
| Resume/crash-safety | ✅ atomic writes, completion sentinels, idempotent stages | ❌ | ❌ |
| Incremental updates | ✅ `update-registry` from CT.gov v2 | ❌ | ❌ |
| Patient interop | ✅ FHIR, Phenopacket, OMOP CDM, free text | AppWrite (cancer-only) | none |
| LLM | local vLLM (MedGemma, phi-4) + LoRA fine-tuning | hosted Gemini | hosted GPT-4 |

## Architecture — two-stage build + match

### Build (one-time, GPU)
1. **Prepare corpus** — normalize ClinicalTrials.gov records to `data/trials_jsons/<NCT_ID>.json`; chunk eligibility criteria into one row per criterion
2. **Entity annotation** — GLiNER2 in-process NER (replaced BERN2 daemons in v0.2.0) for diseases, drugs, genes, procedures, labs
3. **Concept linking** — link entities to standardized vocabularies (genes, diseases, chemicals, phenotypes via OBO ontologies; SNOMED/LOINC/RxNorm via optional OMOP `CONCEPT.csv`)
4. **Constraint extraction** — deterministic regex parsing of each criterion into typed `Constraint` objects (see below)
5. **Embedding** — embed trial documents + per-criterion text (MedCPT, PubMedBERT, bge-m3, or Qwen3-Embedding)
6. **Index** — LanceDB embedded hybrid search (BM25 + vector), no external search service

### Match (per-patient, GPU)
1. **Import patient** — auto-detect format (text/FHIR/Phenopacket/OMOP) → canonical patient profile with provenance
2. **Entity extraction + variant recognition** — extract patient's conditions, biomarkers, labs, medications; genetic-variant recognizer for mutations
3. **First-level retrieval** — hybrid (BM25 + vector) over trial corpus; multi-channel query fusion (primary condition + per-comorbidity channels)
4. **Criterion retrieval + reranking** — retrieve relevant criteria per trial, rerank with vLLM-served LLM reranker
5. **Constraint-aware criterion scoring** — evaluate extracted constraints against patient facts (`ConstraintEvaluation`)
6. **Per-criterion eligibility reasoning** — chain-of-thought LLM (MedGemma/phi-4 with LoRA adapter) produces Met/Not-Met/Unclear/Irrelevant verdict per criterion
7. **Final ranking + HTML report** — self-contained offline `report.html` per patient

## The piece most relevant to us: deterministic constraint extraction

File: `src/trialmatchai/constraints/extraction.py` (~17KB, pure Python regex + pydantic)

A **deterministic, no-LLM parser** that extracts structured `Constraint` objects from eligibility-criterion text. This is the rigorous, auditable version of what our LLM criteria-classification step does loosely — and it's directly portable to our pipeline.

### Constraint schema (`constraints/models.py`, pydantic)

```python
ConstraintKind = "age" | "sex" | "condition" | "phenotype" | "medication"
              | "procedure" | "lab" | "biomarker" | "performance_status" | "temporal"

ConstraintComparator = "present" | "absent" | "eq" | "ne" | "gt" | "ge" | "lt" | "le"
                     | "between" | "positive" | "negative" | "mutated" | "wildtype"
                     | "prior" | "current"

class Constraint(BaseModel):
    kind: ConstraintKind
    label: str
    comparator: ConstraintComparator
    value: float | str | None
    min_value: float | None
    max_value: float | None
    unit: str | None
    normalized_codes: list[dict]     # vocabulary + code (e.g. SNOMED, LOINC)
    temporal_window: str | None
    confidence: float                # 0.0–1.0
    evidence_text: str | None        # the matched text span
    evidence_start: int | None       # char offset
    evidence_end: int | None
```

Plus `ConstraintSet` (per-criterion, with polarity inclusion/exclusion/unknown), `PatientConstraintFact`, `PatientConstraintContext`, and `ConstraintEvaluation` (matched/violated/unknown/not_applicable + score_signal + reason).

### What it extracts (8 constraint types)

| Type | Example criteria text parsed | Output |
|---|---|---|
| **age** | "Age 18-65 years", "≥ 18 years", "adults", "younger than 70" | `between`/`ge`/`le`/`lt` with min/max + unit=years |
| **sex** | "Women", "female" (skips pregnancy/contraception contexts) | `eq` female/male |
| **performance_status** | "ECOG 0-2", "ECOG ≤ 2", "Karnofsky ≥ 70" | `between`/`le`/`ge` ECOG or Karnofsky |
| **lab** | "ANC ≥ 1500", "bilirubin ≤ 1.5 mg/dL", "creatinine < 1.5" | `ge`/`le`/`lt` with value + unit; strips thousands separators |
| **biomarker** | "EGFR mutated", "KRAS positive", "PD-L1 negative", "BRCA wild-type" | `mutated`/`positive`/`negative`/`wildtype`; 13-gene symbol list (ALK, BRAF, BRCA1/2, EGFR, ERBB2/HER2, KRAS, NTRK, PD-L1, PIK3CA, ROS1, TP53) |
| **prior therapy** | "prior treatment with platinum", "previously treated with...", "received prior..." | `prior` medication |
| **temporal** | "within the last 6 months", "within 30 days" | `current` with value + unit (days/weeks/months/years) |
| **entity-derived** | GLiNER2 NER output → condition/medication/procedure/biomarker/lab | `present`/`prior`/`mutated`/`positive`/`negative` with normalized codes |

### Design decisions worth noting

- **Pregnancy/contraception guard:** `_sex_constraints()` returns `[]` if the criterion mentions pregnancy/breastfeeding/lactation/contraception/childbearing — because female/male in those contexts describes the condition, not a sex restriction. This prevents tripping the near-ubiquitous pregnancy exclusion for every woman. A subtle real-world correctness fix we'd never derive from first principles.
- **Lab comparator required:** bare "creatinine 1.5" without `>=`/`<=`/`>`/`<` is skipped — directionally ambiguous. Only explicit comparators produce a constraint.
- **Biomarker status token required:** a bare gene name in a drug phrase ("EGFR inhibitor") is NOT a biomarker requirement — only "EGFR mutated/positive/negative/wild-type" counts. Prevents spurious biomarker constraints from drug-name mentions.
- **"greater than" is exclusive:** `_normalize_comparator("greater than") → "gt"` (exclusive), not `ge`. Correct semantics.
- **Thousands-separator stripping:** "10,000" → 10000.0, not 10. A bug they fixed in v0.3.1 that we'd hit too.
- **Deduplication** by `(kind, label, comparator, value, min, max, codes)` — same constraint from multiple regex passes doesn't inflate.
- **Evidence spans:** every constraint carries `evidence_start`/`evidence_end` char offsets — auditable provenance, not a black box.
- **Confidence scores:** explicit `confidence` per constraint (0.7–0.9 for regex-derived, 0.8 for entity-derived).

## Why this matters for our pipeline

Our `design_agent_pipeline.py` passes raw eligibility-criteria text to the local LLM (Ollama gemma2) for classification into Safety / Statistical Power / Feasibility categories. The LLM does not extract structured constraints — it categorizes. This means:

1. **We cannot quantify recruitment restrictiveness from criteria.** Our `analyze_study_population()` estimates restrictiveness from the *count* of criteria and keyword heuristics, not from actual age bands, ECOG ceilings, lab thresholds, or biomarker requirements. TrialMatchAI's extractor gives us those structured constraints directly.
2. **We cannot simulate eligibility widening** (issue #9's age-range/biomarker-threshold relaxation) without parsing numeric thresholds from criteria. The extractor gives us `age.between(18, 65)`, `ecog.le(2)`, `biomarker.mutated(KRAS)` — exactly the thresholds to widen.
3. **Our LLM classification and their deterministic extraction are complementary, not competing.** Run the deterministic extractor first (structured constraints: age, ECOG, labs, biomarkers, prior therapy), then send the *remainder* (semantic criteria: "adequate organ function", "life expectancy > 12 weeks", "willing to use contraception") to the LLM. Less LLM token load, more auditable, aligns with our "algorithmic where possible" principle.

## Other notable capabilities (less directly relevant)

- **Hybrid retrieval (BM25 + vector) with reciprocal-rank fusion** — production-grade "find similar trials" approach. If we ever want portfolio-level trial-similarity (beyond our current indication-only comparison), this is the architecture. Relevant to issue #10 (PyTrial Trial2Vec) as the stronger alternative — TrialMatchAI's hybrid RRF beats embedding-only retrieval.
- **TREC Clinical Trials benchmark methodology** — the standard eval for trial matching. If we ever evaluate our own criteria-classification quality, the TREC methodology (qrels, nDCG@10, recall@k, condensed vs. full normalization) is the reference.
- **Incremental CT.gov registry updater** — `update-registry --since YYYY-MM-DD` fetches changed studies and upserts into the index. We fetch single trials by NCT ID; this is the pattern for portfolio-wide incremental refresh.
- **FHIR / Phenopacket / OMOP patient importers** — if we ever accept patient data (for enrollment-yield simulation, issue #9), these are the interoperable import patterns.
- **Clinical embedders benchmarked** — MedCPT and PubMedBERT beat bge-m3 and Qwen3-Embedding at every retrieval depth. Domain specialization beats larger general models for clinical text.
- **vLLM + LoRA fine-tuning** — config-driven model swapping (MedGemma, phi-4) with `trialmatchai finetune {cot,reranker,ner}`. If we ever move beyond gemma2:2b, their fine-tuning stack is the reference.

## Integration recommendation

**Port the deterministic constraint extractor (`constraints/extraction.py` + `models.py`) into our pipeline.** This is the single highest-value, lowest-cost integration in our landscape:

1. **Zero heavy dependencies.** Pure Python regex + pydantic. No rdkit, no transformers, no torch, no R, no GPU. Fits our lightweight uv stack exactly.
2. **MIT license.** Clean to port with attribution.
3. **Directly addresses our eligibility-criteria analysis gap.** We currently classify criteria via LLM; this gives us structured numeric/typed constraints deterministically.
4. **Feeds issue #9.** The eligibility-widening simulation needs actual numeric thresholds (age bands, ECOG ceilings, lab cutoffs, biomarker status) to widen — the extractor provides exactly those.
5. **Complements (doesn't replace) our LLM step.** Deterministic extraction for structured constraints; LLM for semantic classification. Less token load, more auditability.

**Do not adopt the full TrialMatchAI system.** The matching task (patient → ranked trials) is orthogonal to ours, and the GPU-dependent components (vLLM, MedCPT embedding, LoRA fine-tuning, LanceDB index) are heavy infrastructure we don't need. Port the ~20KB extractor + schema; reference the architecture for future capabilities.

**Do reference the hybrid RRF retrieval architecture** if issue #10 (PyTrial Trial2Vec trial-similarity) progresses — TrialMatchAI's hybrid BM25+vector with reciprocal-rank fusion is the stronger, benchmarked approach vs. embedding-only.

