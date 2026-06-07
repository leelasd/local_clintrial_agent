# Study Plan: Clinical Trials for LLM and Drug Discovery Experts

This study plan is designed to bridge the gap between upstream drug discovery/generative AI engineering and downstream clinical development. It leverages two top-tier Coursera programs and the standard graduate-level textbook *Fundamentals of Clinical Trials* (5th Edition, Friedman et al.).

The curriculum is structured around building actual clinical Agentic AI systems as you learn.

---

## Syllabus & Resources Reference
1. **Textbook:** *Fundamentals of Clinical Trials* (5th Edition) by Lawrence M. Friedman, Curt D. Furberg, David L. DeMets.
2. **Coursera Course 1 (JHU):** *Design and Interpretation of Clinical Trials* (Johns Hopkins University) - [Link](https://www.coursera.org/learn/clinical-trials)
3. **Coursera Course 2 (Vanderbilt):** *Data Management for Clinical Research* (Vanderbilt University) - [Link](https://www.coursera.org/learn/clinical-data-management)

---

## Phase 1: Trial Mechanics, Endpoints & Protocol Design
**Timeline:** Weeks 1-2  
**Primary Focus:** Learning the baseline blueprints of a clinical trial. Understanding the anatomy of a protocol, defining study populations, and selecting clinically meaningful endpoints.

### 1. Readings & Lectures
* **Coursera (Johns Hopkins):**
  * Module 1: Introduction to Clinical Trials (Basic trial terminology, history)
  * Module 2: Defining the Study Population & Endpoints
* **Textbook Chapters:**
  * Chapter 1: Introduction to Clinical Trials
  * Chapter 2: Ethical Issues (Focus on Informed Consent and Institutional Review Board (IRB) structures)
  * Chapter 4: What is the Question? (Primary vs. Secondary outcomes, surrogate endpoints)
  * Chapter 5: Study Population (Drafting inclusion and exclusion criteria)

### 2. Core Concepts to Master
* **Endpoints:** The difference between hard endpoints (e.g., Overall Survival) and surrogate endpoints (e.g., Progression-Free Survival, biomarker level drops).
* **Population Selection:** How inclusion/exclusion criteria balance scientific homogeneity with the generalizability of results.
* **Ethics:** GCP (Good Clinical Practice) constraints and the absolute boundary of Patient Consent.

### 3. Agentic AI Bridge (Practical Project)
* **Project Name:** The "Protocol Schema Extractor & Analyzer"
* **Task:** Build an agent that ingests an unstructured 100-page clinical trial protocol PDF (you can find samples on ClinicalTrials.gov or PubMed).
* **Implementation:**
  * Configure a Retrieval-Augmented Generation (RAG) agent using LlamaIndex or LangChain.
  * Define a strict JSON schema for outputting structured trial criteria.
  * Force the agent to output:
    1. Study demographics (age, sex, geography).
    2. Primary, secondary, and exploratory endpoints.
    3. Categorized list of inclusion and exclusion criteria (e.g., lab value requirements, prior therapies, exclusion diagnoses).
    4. Citations pointing to the exact page and paragraph of the source PDF.

---

## Phase 2: Trial Optimization, Randomization & Statistical Design
**Timeline:** Weeks 3-4  
**Primary Focus:** Moving from static to dynamic designs. Learning how trials minimize bias (blinding, randomization) and optimize efficiency (adaptive designs, master protocols).

### 1. Readings & Lectures
* **Coursera (Johns Hopkins):**
  * Module 3: Special Designs (Crossover, Factorial, Cluster Trials)
  * Module 4: Randomization & Blinding
  * Module 5: Adaptive Designs and Interim Analyses
* **Textbook Chapters:**
  * Chapter 7: Basic Study Design (Focus on Basket, Umbrella, and Platform designs for precision medicine)
  * Chapter 10: Randomization
  * Chapter 11: Blindness
  * Chapter 19: Adaptive Designs (Altering sample sizes, dropping inactive arms, modifying doses)

### 2. Core Concepts to Master
* **Adaptive Designs:** The strict mathematical rules allowing clinical teams to change trial parameters mid-trial without destroying statistical validity.
* **Precision Protocols:** How Basket trials allow drug developers to test one drug across multiple different cancers (histologies) matching the same genetic biomarker (e.g., MSI-H).
* **Blinding Integrity:** How to enforce data isolation to prevent unblinding.

### 3. Agentic AI Bridge (Practical Project)
* **Project Name:** The "Multi-Agent Basket Trial Simulator"
* **Task:** Create a multi-agent orchestration (using AutoGen, CrewAI, or LangGraph) to model and optimize a Phase 2 adaptive basket trial.
* **Implementation:**
  * **Agent A (Site Simulator):** Generates synthetic patient enrollment data across 3 tumor baskets (e.g., Colorectal, Endometrial, Gastric) treated with a mock WRN inhibitor, outputting weekly tumor size updates.
  * **Agent B (Statistical Engine):** Ingests this stream, runs a mock Bayesian threshold calculation, and determines the probability of success for each basket.
  * **Agent C (Lead Decision Maker):** Evaluates Agent B's output against the protocol's adaptive rules. It must autonomously decide to drop the "Gastric" basket if efficacy is low, expand the "Colorectal" basket, and draft a formal protocol amendment summarizing the statistical justification.

---

## Phase 3: Clinical Data Systems, EHR Integration & Schemas
**Timeline:** Weeks 5-6  
**Primary Focus:** The data topology of clinical trials. Learning how clinical databases are built, the CDISC/SDTM regulatory data standards, and how EHR systems represent patient records.

### 1. Readings & Lectures
* **Coursera (Vanderbilt):**
  * Module 1: Clinical Data Management Overview
  * Module 2: Case Report Forms (CRFs) & Data Standards
  * Module 3: Database Design and Electronic Data Capture (EDC)
* **Textbook Chapters:**
  * Chapter 13: Data Collection and Quality Control
  * Chapter 16: Survival Analysis (Focus on how time-to-event data is captured and represented)

### 2. Core Concepts to Master
* **EDC Systems:** How Electronic Data Capture platforms collect, track, and audit data (compliance with 21 CFR Part 11).
* **CDISC Standards:** The transition of data from raw EHR to CDASH (source collection), SDTM (standardized submission domains), and ADaM (analytical formats).
* **Source Data Verification (SDV):** The process of cross-checking clinical trial database entries against the actual patient medical charts.

### 3. Agentic AI Bridge (Practical Project)
* **Project Name:** The "Automated EDC-SDTM Mapping Agent"
* **Task:** Bridge the gap between unstructured healthcare data and rigid regulatory clinical databases.
* **Implementation:**
  * Generate or download mock patient EHR timelines (e.g., containing diagnosis codes, treatment logs, and lab results).
  * Build an LLM agent equipped with the CDISC SDTM implementation guides as vector databases.
  * Task the agent with extracting unstructured adverse events from the clinical notes and mapping them directly to the SDTM `AE` (Adverse Events) domain, outputting a validated CSV schema containing variables like `AETERM` (reported term), `AEDECOD` (standardized MedDRA term), and `AESTDTC` (start date).

---

## Phase 4: Monitoring, Safety, Pharmacovigilance & Study Closeout
**Timeline:** Weeks 7-8  
**Primary Focus:** Safety oversight, data monitoring committees, identifying safety signals, and generating the final Clinical Study Report (CSR).

### 1. Readings & Lectures
* **Coursera (Johns Hopkins):**
  * Module 6: Safety Monitoring & Safety Committees (DSMB)
  * Module 7: Study Closeout & Analyzing and Reporting Results
* **Textbook Chapters:**
  * Chapter 14: Assessing and Reporting Adverse Events
  * Chapter 15: Study Monitoring (Data and Safety Monitoring Boards)
  * Chapter 20: Reporting and Interpreting Results

### 2. Core Concepts to Master
* **Serious Adverse Events (SAEs):** What qualifies an event as "Serious" (hospitalization, death, life-threatening) and the legally mandated tight timelines (often 7 or 15 days) for reporting to the FDA.
* **Data Safety Monitoring Boards (DSMB):** The independent group of experts that regularly unblinds and reviews safety data to ensure patients are not being harmed.
* **The Clinical Study Report (CSR):** The massive, highly standardized document containing the final analysis of a trial submitted to regulators.

### 3. Agentic AI Bridge (Practical Project)
* **Project Name:** The "Pharmacovigilance Intake & Narrative Drafter"
* **Task:** Build an agent that accelerates safety review by automatically drafting regulatory-compliant narrative summaries of adverse events.
* **Implementation:**
  * Input a simulated raw clinical data feed indicating a patient was hospitalized (an SAE) during the trial of a mock small-molecule drug.
  * Build an agent containing a structural template of an FDA safety narrative.
  * The agent must autonomously query the mock EHR database for that patient's history, current dosing, concomitant medications, and lab trends leading up to the event.
  * The agent outputs a highly structured, professional, chronological narrative detailing the event, leaving the medical monitor with only the final review and signature.
