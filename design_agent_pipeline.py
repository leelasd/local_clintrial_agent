import requests
import json
import math
import re
import ollama
import argparse
from pathlib import Path
from collections import Counter
from scipy import stats
import yaml

# Import clintrial_agent modules
from clintrial_agent.config import CONFIG, INDICATION_PARAMS, INDICATION_ALIASES, DEFAULT_INDICATION_PARAMS
from clintrial_agent.data import fetch_trial
from clintrial_agent.stats import analyze_sample_size, _dichotomous_power_curve, _survival_power_curve
from clintrial_agent.llm import infer_indication, classify_eligibility_criteria
from clintrial_agent.reporting import generate_power_plots

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import numpy as np
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


# Indication inference imported from clintrial_agent.llm


def classify_design_from_api(protocol):
    """Classify trial design type from API's structured data."""
    design = protocol.get('designModule', {})
    arms = protocol.get('armsInterventionsModule', {})
    design_info = design.get('designInfo', {})
    
    study_type = design.get('studyType', '')
    allocation = design_info.get('allocation', '')
    intervention_model = design_info.get('interventionModel', '')
    primary_purpose = design_info.get('primaryPurpose', '')
    phases = design.get('phases', [])
    masking_info = design_info.get('maskingInfo', {})
    masking = masking_info.get('masking', '')
    
    arm_groups = arms.get('armGroups', [])
    arm_types = [a.get('type', '') for a in arm_groups]
    
    # Determine control_type
    is_phase1 = any('PHASE1' in p for p in phases)
    is_nonrandomized = allocation == 'NON_RANDOMIZED'
    all_experimental = all(t == 'EXPERIMENTAL' for t in arm_types) if arm_types else False
    
    if 'PLACEBO_COMPARATOR' in arm_types:
        control_type = 'Placebo'
    elif 'ACTIVE_COMPARATOR' in arm_types:
        control_type = 'Active Comparator'
    elif 'SHAM_COMPARATOR' in arm_types:
        control_type = 'Active Comparator'
    elif 'NO_INTERVENTION' in arm_types:
        control_type = 'No Treatment'
    elif len(arm_types) <= 1:
        control_type = 'None (Single-Arm)'
    elif (is_phase1 or is_nonrandomized) and all_experimental:
        control_type = 'None (Single-Arm)'
    else:
        control_type = 'Standard of Care'
    
    # Determine design_type
    if intervention_model == 'CROSSOVER':
        design_type = 'Crossover'
    elif intervention_model == 'FACTORIAL':
        design_type = 'Factorial'
    elif intervention_model == 'SEQUENTIAL':
        design_type = 'Adaptive Design'
    elif intervention_model == 'SINGLE_GROUP':
        design_type = 'Single-Arm'
    elif allocation == 'RANDOMIZED' and intervention_model == 'PARALLEL':
        design_type = 'Parallel RCT'
    elif allocation != 'RANDOMIZED' and intervention_model == 'PARALLEL' and not all_experimental:
        design_type = 'Nonrandomized Concurrent Control'
    elif intervention_model == 'PARALLEL' and allocation == 'RANDOMIZED':
        design_type = 'Parallel RCT'
    elif all_experimental and not is_phase1:
        design_type = 'Adaptive Design'
    elif is_phase1:
        design_type = 'Single-Arm'
    else:
        design_type = 'Other'
    
    # Determine superiority_type from phase and purpose
    # Noninferiority/equivalence trials are more common in Phase 3 with active comparators
    description_text = (
        protocol.get('descriptionModule', {}).get('briefSummary', '') + ' ' +
        (protocol.get('descriptionModule', {}).get('detailedDescription', '') or '') + ' ' +
        protocol.get('eligibilityModule', {}).get('eligibilityCriteria', '')
    ).lower()
    mentions_noninferiority = any(k in description_text for k in CONFIG['noninferiority_keywords'])
    
    if is_phase1:
        superiority_type = 'Unclear'
    elif control_type == 'None (Single-Arm)':
        superiority_type = 'Unclear'
    elif mentions_noninferiority:
        superiority_type = 'Noninferiority'
    elif control_type == 'Placebo':
        superiority_type = 'Superiority'
    else:
        superiority_type = 'Superiority'
    
    return {
        'design_type': design_type,
        'control_type': control_type,
        'superiority_type': superiority_type,
        'allocation': allocation,
        'intervention_model': intervention_model,
        'primary_purpose': primary_purpose,
        'phases': phases
    }


def analyze_study_population(protocol):
    """Analyze study population from eligibility module structured data."""
    elig = protocol.get('eligibilityModule', {})
    design_mod = protocol.get('designModule', {})
    enrollment = design_mod.get('enrollmentInfo', {})
    
    sex = elig.get('sex', 'ALL')
    min_age = elig.get('minimumAge', 'N/A')
    max_age = elig.get('maximumAge', 'N/A')
    healthy_vol = elig.get('healthyVolunteers', False)
    std_ages = elig.get('stdAges', [])
    
    # Determine age range stringency
    age_restrictiveness = 'Low'
    if min_age != 'N/A' and max_age != 'N/A':
        age_restrictiveness = 'High'
    elif min_age != 'N/A' or max_age != 'N/A':
        age_restrictiveness = 'Moderate'
    
    # Detect whether criteria include significant competing risk exclusions
    criteria_text = elig.get('eligibilityCriteria', '').lower()
    competing_keywords = CONFIG['competing_keywords']
    has_competing_risks = any(k in criteria_text for k in competing_keywords)
    
    # Estimate recruitment yield based on restrictiveness
    restrictive_count = 0
    if sex != 'ALL':
        restrictive_count += 1
    if max_age != 'N/A' or min_age != 'N/A':
        restrictive_count += 1
    if healthy_vol:
        restrictive_count -= 1  # healthy volunteers are LESS restrictive
    
    _recruit_thresh = CONFIG['recruitment_yield']['restrictive_count_thresholds']
    if restrictive_count >= _recruit_thresh['low']:
        recruitment_yield = 'Low (<5% screen-to-enroll)'
    elif restrictive_count >= _recruit_thresh['moderate']:
        recruitment_yield = 'Moderate (5-20% screen-to-enroll)'
    else:
        recruitment_yield = 'High (>20% screen-to-enroll)'
    
    # Enrollment info
    enrollment_count = enrollment.get('count', 'N/A')
    enrollment_type = enrollment.get('type', 'N/A')
    
    return {
        'sex': sex,
        'age_range': f"{min_age} - {max_age}" if max_age != 'N/A' else f"{min_age}+",
        'std_ages': std_ages,
        'healthy_volunteers': healthy_vol,
        'age_restrictiveness': age_restrictiveness,
        'has_competing_risk_exclusions': has_competing_risks,
        'recruitment_yield_estimate': recruitment_yield,
        'enrollment_count': enrollment_count,
        'enrollment_type': enrollment_type
    }

# Sample size and power calculations imported from clintrial_agent.stats

def analyze_randomization(protocol):
    """Extract randomization details from API data and description text."""
    design_info = protocol.get('designModule', {}).get('designInfo', {})
    arms = protocol.get('armsInterventionsModule', {})
    arm_groups = arms.get('armGroups', [])
    
    allocation = design_info.get('allocation', '')
    
    # Determine allocation ratio from arm count (defaults to equal)
    interventional = [a for a in arm_groups if a.get('type') != 'NO_INTERVENTION']
    num_arms = len(interventional)
    allocation_ratio = '1:1' if num_arms <= 2 else f'1:1:1' if num_arms == 3 else f'1:' * (num_arms - 1) + '1'
    
    # Check description text for randomization details
    description_text = (
        protocol.get('descriptionModule', {}).get('briefSummary', '') + ' ' +
        protocol.get('descriptionModule', {}).get('detailedDescription', '') + ' ' +
        protocol.get('eligibilityModule', {}).get('eligibilityCriteria', '')
    ).lower()
    
    # Detect randomization type from keywords
    has_stratified = any(k in description_text for k in ['stratified', 'stratum', 'stratification'])
    has_blocked = any(k in description_text for k in ['block', 'permuted block', 'block randomization'])
    has_adaptive_rand = any(k in description_text for k in ['adaptive randomization', 'response-adaptive', 'minimization'])
    
    # Infer stratification factors
    stratification_factors = []
    factor_keywords = CONFIG['stratification_factor_keywords']
    for factor in factor_keywords:
        if factor in description_text:
            stratification_factors.append(factor.title())
    
    # Determine type
    if has_adaptive_rand:
        rand_type = 'Adaptive'
    elif has_stratified and has_blocked:
        rand_type = 'Stratified'
    elif has_stratified:
        rand_type = 'Stratified'
    elif has_blocked:
        rand_type = 'Blocked'
    elif allocation == 'RANDOMIZED':
        rand_type = 'Simple'
    else:
        rand_type = 'Not described'
    
    return {
        'randomization_type': rand_type,
        'allocation_ratio': allocation_ratio,
        'stratification_factors': stratification_factors,
        'randomization_description': f"{'Stratified by ' + ', '.join(stratification_factors[:3]) + '. ' if stratification_factors else ''}{'Blocked randomization.' if has_blocked else 'Simple randomization.' if rand_type == 'Simple' else ''}"
    }


def analyze_adaptive_design(protocol, api_design):
    """Detect adaptive design features from protocol description text and API data."""
    description_text = (
        protocol.get('descriptionModule', {}).get('briefSummary', '') + ' ' +
        (protocol.get('descriptionModule', {}).get('detailedDescription', '') or '') + ' ' +
        protocol.get('eligibilityModule', {}).get('eligibilityCriteria', '')
    ).lower()
    
    # Check API for sequential/intervention model suggesting adaptation
    intervention_model = api_design.get('intervention_model', '')
    phases = api_design.get('phases', [])
    
    # Detect adaptive design types from keywords
    adaptive_signals = CONFIG['adaptive_signals']
    
    adaptive_types = []
    for design_type, keywords in adaptive_signals.items():
        if any(k in description_text for k in keywords):
            adaptive_types.append(design_type)
    
    # Phase 1 trials are inherently dose-finding (adaptive)
    is_phase1 = any('PHASE1' in p for p in phases)
    if is_phase1 and 'Dose-Finding / Phase I' not in adaptive_types:
        adaptive_types.append('Dose-Finding / Phase I')
    
    # Look for specific stopping rules
    _sr = CONFIG['stopping_rule_keywords']
    stopping_rules = 'Not mentioned'
    if any(k in description_text for k in _sr['obrien_fleming']):
        stopping_rules = "O'Brien-Fleming boundary"
    elif any(k in description_text for k in _sr['pocock']):
        stopping_rules = 'Pocock boundary'
    elif any(k in description_text for k in _sr['lan_demets']):
        stopping_rules = "Lan-DeMets alpha spending function"
    elif any(k in description_text for k in _sr['haybittle_peto']):
        stopping_rules = 'Haybittle-Peto boundary'
    elif any(k in description_text for k in _sr['generic']):
        stopping_rules = 'Specified (details not available from text)'
    
    interim_analysis = any(k in description_text for k in CONFIG['interim_analysis_keywords'])
    
    has_adaptive = len(adaptive_types) > 0
    
    if has_adaptive:
        desc_parts = ['Adaptive design detected:']
        desc_parts.append(f"Types identified: {', '.join(adaptive_types)}.")
        if interim_analysis:
            desc_parts.append('Interim analyses specified.')
        if stopping_rules != 'Not mentioned':
            desc_parts.append(f'Stopping rule: {stopping_rules}.')
        description = ' '.join(desc_parts)
    else:
        description = 'Standard fixed-design trial. No adaptive features detected.'
    
    # Detect dose-escalation method for Phase 1 trials
    _de = CONFIG['dose_escalation_keywords']
    dose_method = None
    if is_phase1:
        if any(k in description_text for k in _de['crm']):
            dose_method = 'Continual Reassessment Method (CRM)'
        elif any(k in description_text for k in _de['bayesian']):
            dose_method = 'Bayesian dose-escalation'
        elif any(k in description_text for k in _de['traditional_3plus3']):
            dose_method = 'Traditional 3+3'
        elif any(k in description_text for k in _de['rolling_six']):
            dose_method = 'Rolling Six design'
        else:
            dose_method = 'Standard dose-escalation (not explicitly specified)'
    
    return {
        'has_adaptive_features': has_adaptive,
        'adaptive_types': adaptive_types,
        'interim_analysis_mentioned': interim_analysis,
        'stopping_rules': stopping_rules,
        'dose_escalation_method': dose_method,
        'description': description
    }


def analyze_safety_adverse_events(protocol, endpoints):
    """Extract safety/AE reporting methods, known AE types, and stopping rules from protocol."""
    description_text = (
        protocol.get('descriptionModule', {}).get('briefSummary', '') + ' ' +
        (protocol.get('descriptionModule', {}).get('detailedDescription', '') or '') + ' ' +
        protocol.get('eligibilityModule', {}).get('eligibilityCriteria', '')
    ).lower()
    
    outcomes = protocol.get('outcomesModule', {})
    safety_outcomes = []
    for o in outcomes.get('secondaryOutcomes', []):
        text = o.get('measure', '')
        if any(k in text.lower() for k in CONFIG['safety_outcome_keywords']):
            safety_outcomes.append(o)
    
    # --- Item 1: Extract known AE types from protocol text ---
    general_ae_terms = CONFIG['general_ae_terms']
    
    _dce = CONFIG['drug_class_effects']
    ae_types_detected = []
    for term, label in general_ae_terms.items():
        if term in description_text:
            ae_types_detected.append(label)
    
    class_effects = []
    for drug_class, class_terms in _dce.items():
        for term, label in class_terms.items():
            if term in description_text:
                class_effects.append(label)
    
    # --- Item 3: Categorize AE reporting method ---
    _srk = CONFIG['safety_reporting_keywords']
    has_meddra = any(k in description_text for k in _srk['meddra'])
    has_ctcae = any(k in description_text for k in _srk['ctcae'])
    has_elicited = any(k in description_text for k in _srk['elicited'])
    has_volunteered = any(k in description_text for k in _srk['volunteered'])
    
    reporting_parts = []
    if has_meddra:
        reporting_parts.append('MedDRA (Medical Dictionary for Regulatory Activities)')
    if has_ctcae:
        reporting_parts.append('CTCAE severity grading')
    if not has_meddra and not has_ctcae:
        reporting_parts.append('Not explicitly specified')
    
    if has_elicited and has_volunteered:
        ascertainment = 'Elicited via checklist + volunteered spontaneous reports'
    elif has_elicited:
        ascertainment = 'Elicited via checklist at each visit'
    elif has_volunteered:
        ascertainment = 'Volunteered spontaneous reports (open-ended questioning)'
    else:
        ascertainment = 'Not explicitly described (assumed standard investigator reporting)'
    
    ae_reporting_method = ', '.join(reporting_parts) if reporting_parts else 'Standard AE reporting'
    
    # --- Item 4: SAE stopping rules and safety monitoring ---
    # Look for DSMB / Data Monitoring Committee
    has_dsmb = any(k in description_text for k in CONFIG['dsmb_keywords'])
    has_sae_stopping = any(k in description_text for k in CONFIG['sae_stopping_keywords'])
    
    # Try to extract the specific stopping rule language
    sae_stopping_rules = 'Not specified in protocol text'
    for kw in ['discontinuation', 'withdrawn', 'dose modification', 'dose reduction', 'permanent discontinuation']:
        if kw in description_text:
            idx = description_text.find(kw)
            sae_stopping_rules = (
                f"Protocol mentions '{kw}' in safety context: "
                f"...{description_text[max(0, idx-60):idx+120]}..."
            )
            break
    
    safety_monitoring = 'Not specified'
    if has_dsmb:
        safety_monitoring = 'Data Safety Monitoring Board (DSMB) with scheduled reviews'
    else:
        safety_monitoring = 'Investigator-reported with sponsor oversight (no DSMB mentioned)'
    
    # Extract safety outcome endpoint text for inclusion
    safety_endpoint_text = [o.get('measure', '') for o in safety_outcomes]
    
    return {
        'ae_reporting_method': ae_reporting_method,
        'ae_ascertainment': ascertainment,
        'ae_types_detected': list(set(ae_types_detected)),
        'class_effects_known': list(set(class_effects)),
        'safety_endpoints': safety_endpoint_text,
        'sae_stopping_rules': sae_stopping_rules if sae_stopping_rules != 'Not specified in protocol text' else sae_stopping_rules,
        'safety_monitoring': safety_monitoring
    }


# ==============================================================================
# GWAS CATALOG INTEGRATION
# ==============================================================================
# Textbook Ch 9 (Pharmacogenetics, p. 172):
# "Collection of biologic samples at baseline in large, long-term trials has emerged
# as a rich source for pharmacogenetic studies. In participants with or without specific
# genotypes, one would in subgroup analysis compare treatment responses."
#
# "The strength by which common variants can influence the risk determination ranges
# from a several-fold increased risk compared to those without the variant to a
# 1,000-fold increase."
#
# The GWAS Catalog provides curated SNP-trait associations from published GWAS,
# enabling identification of known genetic variants relevant to a trial's indication,
# drug target, or safety profile.

GWAS_API_BASE = CONFIG['gwas_api_base_url']
PGX_CONFIG = CONFIG['pharmacogenetic_assessment']
PGX_DRUGS = CONFIG['pharmacogenetic_drugs']


def query_gwas_efo_trait(trait_name):
    """Look up EFO trait from GWAS Catalog by free-text search.
    
    Returns dict with efo_id, efo_trait, uri if found, else None.
    Prefers exact match on trait name, then substring match, then first result.
    """
    url = f"{GWAS_API_BASE}/v2/efo-traits"
    params = {'efo_trait': trait_name, 'size': 15}
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            traits = data.get('_embedded', {}).get('efo_traits', [])
            if traits:
                # Exact match (case-insensitive)
                for t in traits:
                    if t.get('efo_trait', '').lower() == trait_name.lower():
                        return {
                            'efo_id': t['efo_id'],
                            'efo_trait': t['efo_trait'],
                            'uri': t['uri']
                        }
                # Word-boundary match: trait_name appears as a whole word
                for t in traits:
                    trait_lower = t.get('efo_trait', '').lower()
                    if re.search(r'\b' + re.escape(trait_name.lower()) + r'\b', trait_lower):
                        return {
                            'efo_id': t['efo_id'],
                            'efo_trait': t['efo_trait'],
                            'uri': t['uri']
                        }
                # Substring match: trait_name is a substring of the trait
                for t in traits:
                    if trait_name.lower() in t.get('efo_trait', '').lower():
                        return {
                            'efo_id': t['efo_id'],
                            'efo_trait': t['efo_trait'],
                            'uri': t['uri']
                        }
                # Fallback to first result
                t = traits[0]
                return {
                    'efo_id': t['efo_id'],
                    'efo_trait': t['efo_trait'],
                    'uri': t['uri']
                }
    except requests.RequestException:
        pass
    return None


def query_gwas_associations(efo_trait=None, efo_id=None, max_results=None):
    """Fetch GWAS associations for a given trait.
    
    Returns list of association dicts with p-value, OR, mapped genes, SNP info.
    """
    if max_results is None:
        max_results = PGX_CONFIG['max_associations_per_query']
    
    url = f"{GWAS_API_BASE}/v2/associations"
    params = {'size': min(max_results, 500)}
    if efo_id:
        params['efo_id'] = efo_id
    elif efo_trait:
        params['efo_trait'] = efo_trait
    else:
        return []
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('_embedded', {}).get('associations', [])
    except requests.RequestException:
        pass
    return []


def extract_genetic_biomarkers_from_text(text):
    """Extract known pharmacogenetic signals from free text.
    
    Two-pass detection:
    1. First detects drug class by matching drug compound names in protocol text
    2. Then returns the relevant genes/effects for each detected drug class
    
    Returns dict: gene_name -> {'drug_class': str, 'known_effects': list}
    Includes a special '_detected_drug_classes' key listing matched drug classes.
    """
    text_lower = text.lower()
    detected_drug_classes = set()
    
    for drug_class, info in PGX_DRUGS.items():
        for drug_name in info.get('drug_names', []):
            if drug_name.lower() in text_lower:
                detected_drug_classes.add(drug_class)
                break
    
    genes_found = {}
    for drug_class in detected_drug_classes:
        info = PGX_DRUGS[drug_class]
        for gene, effects in info.get('genes', {}).items():
            genes_found[gene] = {
                'drug_class': drug_class,
                'known_effects': effects
            }
    
    genes_found['_detected_drug_classes'] = list(detected_drug_classes)
    return genes_found


def extract_genetic_biomarkers(protocol):
    """Extract genetic biomarker mentions from protocol description and eligibility text."""
    description = (
        protocol.get('descriptionModule', {}).get('briefSummary', '') + ' ' +
        (protocol.get('descriptionModule', {}).get('detailedDescription', '') or '') + ' ' +
        protocol.get('eligibilityModule', {}).get('eligibilityCriteria', '') + ' ' +
        protocol.get('identificationModule', {}).get('briefTitle', '') + ' ' +
        ' '.join(o.get('measure', '') for o in
                  protocol.get('outcomesModule', {}).get('primaryOutcomes', []) + 
                  protocol.get('outcomesModule', {}).get('secondaryOutcomes', []))
    )
    return extract_genetic_biomarkers_from_text(description)


# Patterns to detect genetic biomarker requirements in eligibility criteria.
# Keys map to genetic_biomarker_prevalence in config.
GENETIC_BIOMARKER_PATTERNS = [
    (r'\bkras\s*p?\.?g12c\b', 'KRAS_G12C'),
    (r'\bkras\s*g12c\b', 'KRAS_G12C'),
    (r'\b(kras|ras)\s*p?\.?g12d\b', 'KRAS_G12D'),
    (r'\b(kras|ras)\s*g12d\b', 'KRAS_G12D'),
    (r'\b(kras|nras|hras)\s*(mutation|mutant|mut)\b', 'RAS_mutation_any'),
    (r'\b(mutation|mutant|mut)\s+in\s+(kras|nras|hras)\b', 'RAS_mutation_any'),
    (r'\bpan.?ras\b', 'RAS_mutation_any'),
    (r'\bcodons?\s*(12|13|61)\b', 'RAS_mutation_any'),
    (r'\bdmmr\b', 'dMMR_MSI_H'),
    (r'\bmsi-h\b', 'dMMR_MSI_H'),
    (r'\bmsi\s*high\b', 'dMMR_MSI_H'),
    (r'\bmicrosatellite\s*instability\b', 'dMMR_MSI_H'),
    (r'\begfr\s*exon\s*19\b', 'EGFR_ex19del'),
    (r'\begfr\s*l858r\b', 'EGFR_L858R'),
    (r'\bbraf\s*v600e?\b', 'BRAF_V600E'),
    (r'\bher2\s*positive\b', 'HER2_amplification'),
    (r'\bher2\s*amplif', 'HER2_amplification'),
    (r'\berbb2\s*amplif', 'HER2_amplification'),
]


def detect_genetic_biomarker_requirements(text):
    """Scan eligibility criteria for genetic biomarker requirements.
    
    Returns list of dicts: {biomarker_key, prevalence, screen_fail_rate, matched_text}
    """
    text_lower = text.lower()
    prevalence_map = PGX_CONFIG['genetic_biomarker_prevalence']
    found = []
    seen = set()
    for pattern, key in GENETIC_BIOMARKER_PATTERNS:
        match = re.search(pattern, text_lower)
        if match and key not in seen:
            seen.add(key)
            prevalence = prevalence_map.get(key, 0.5)
            found.append({
                'biomarker_key': key,
                'population_prevalence': prevalence,
                'estimated_screen_failure_rate': round(1.0 - prevalence, 3),
                'matched_text': match.group()
            })
    return found


def detect_genetic_biomarker_requirements_from_protocol(protocol):
    """Extract genetic biomarker requirement mentions from eligibility criteria."""
    return detect_genetic_biomarker_requirements(
        protocol.get('eligibilityModule', {}).get('eligibilityCriteria', '')
    )


def analyze_pharmacogenetics(protocol, indication):
    """GWAS-powered pharmacogenetic subgroup analysis.
    
    Textbook framework (Ch. 9, p. 172-174):
    1. Identifies genes mentioned in the protocol (drug targets, biomarkers, safety genes)
    2. Cross-references against GWAS Catalog for known SNP-trait associations
    3. Identifies potential pharmacogenetic subgroups for:
       - Differential treatment response (efficacy) — e.g., EGFR mutations for gefitinib
       - Differential adverse event risk (safety) — e.g., SLCO1B1 for statin myopathy
    4. Assesses whether genotype-stratified randomization or pre-planned subgroup analysis
       is warranted per the textbook's pharmacogenetics framework
    """
    result = {
        'genetic_biomarkers_mentioned': [],
        'genetic_screen_failure': [],
        'genetic_screen_failure_summary': None,
        'gwas_associations_found': [],
        'pharmacogenetic_subgroups': [],
        'stratification_opportunity': None,
        'safety_pharmacogenetics': [],
        'summary': 'No pharmacogenetic analysis performed'
    }
    
    biomarkers = extract_genetic_biomarkers(protocol)
    detected_classes = biomarkers.pop('_detected_drug_classes', [])
    
    if detected_classes:
        result['detected_drug_classes'] = detected_classes
    
    result['genetic_biomarkers_mentioned'] = [
        {'gene': g, 'drug_class': info['drug_class'], 'known_effects': info['known_effects']}
        for g, info in biomarkers.items()
    ]
    
    if not biomarkers and not detected_classes:
        result['summary'] = 'No known pharmacogenetic drug classes or genes detected in protocol text.'
        return result
    
    if not biomarkers:
        result['summary'] = (
            f'Drug class detected ({", ".join(detected_classes)}) but no specific pharmacogenetic '
            f'genes configured for it.'
        )
        return result
    
    # Genetic screen failure estimation: detect biomarker-based eligibility criteria
    # and estimate what fraction of screened patients would fail genetic requirements.
    eligibility_text = protocol.get('eligibilityModule', {}).get('eligibilityCriteria', '')
    genetic_requirements = detect_genetic_biomarker_requirements(eligibility_text)
    result['genetic_screen_failure'] = genetic_requirements
    
    if genetic_requirements:
        max_fail = max(r['estimated_screen_failure_rate'] for r in genetic_requirements)
        result['genetic_screen_failure_summary'] = (
            f"Detected {len(genetic_requirements)} genetic biomarker requirement(s) in eligibility: "
            + "; ".join(
                f"{r['biomarker_key']} (pop. prevalence ~{r['population_prevalence']:.0%}, "
                f"~{r['estimated_screen_failure_rate']:.0%} screen fail)"
                for r in genetic_requirements
            )
            + f". Worst-case screen failure rate from genetic criteria: ~{max_fail:.0%}."
        )
    
    if indication:
        efo_info = query_gwas_efo_trait(indication)
        if efo_info:
            associations = query_gwas_associations(efo_id=efo_info['efo_id'])
            gene_names = [g.lower() for g in biomarkers.keys()]
            
            relevant = []
            seen_snps = set()
            for assoc in associations:
                mapped_genes = [g.lower() for g in (assoc.get('mapped_genes', []) or [])]
                matching = [g for g in mapped_genes if g in gene_names]
                if not matching:
                    continue
                
                p_mantissa = assoc.get('pvalue_mantissa')
                p_exponent = assoc.get('pvalue_exponent')
                pvalue = f"{p_mantissa}e{p_exponent}" if p_mantissa is not None and p_exponent is not None else None
                
                snp_info = assoc.get('snp_allele', [{}])[0] if assoc.get('snp_allele') else {}
                rs_id = snp_info.get('rs_id', 'N/A')
                
                if rs_id in seen_snps:
                    continue
                seen_snps.add(rs_id)
                
                relevant.append({
                    'snp': rs_id,
                    'pvalue': pvalue,
                    'or_per_copy': assoc.get('or_per_copy_num'),
                    'ci_range': assoc.get('range'),
                    'risk_frequency': assoc.get('risk_frequency'),
                    'mapped_genes': assoc.get('mapped_genes', []),
                    'trait': assoc.get('reported_trait', ['N/A'])[0],
                    'pubmed_id': assoc.get('pubmed_id'),
                    'accession_id': assoc.get('accession_id')
                })
            
            result['gwas_associations_found'] = relevant
            
            # Build pharmacogenetic subgroup recommendations
            subgroups = []
            safety_pgx = []
            for gene_info in result['genetic_biomarkers_mentioned']:
                gene = gene_info['gene']
                effects = gene_info['known_effects']
                gwas_hits = [a for a in relevant if gene.lower() in [g.lower() for g in (a.get('mapped_genes', []) or [])]]
                
                subgroup = {
                    'gene': gene,
                    'drug_class': gene_info['drug_class'],
                    'known_effects': effects,
                    'gwas_associations_count': len(gwas_hits),
                    'recommended_subgroup_analysis': any('response' in e.lower() for e in effects),
                    'recommended_safety_monitoring': any('safety' in e.lower() for e in effects),
                }
                subgroups.append(subgroup)
                
                # Textbook Ch 9: GWAS can identify SNPs linked to adverse drug reactions
                if subgroup['recommended_safety_monitoring']:
                    safety_pgx.append({
                        'gene': gene,
                        'rationale': (
                            f"GWAS-identified variants in {gene} may predict differential AE risk. "
                            f"Per textbook Ch. 9 (p. 173): 'Genetic variants associated with serious "
                            f"adverse events [...] prior to initiation of treatment.'"
                        )
                    })
            
            result['pharmacogenetic_subgroups'] = subgroups
            result['safety_pharmacogenetics'] = safety_pgx
            
            # Assess stratification opportunity
            if any(s['recommended_subgroup_analysis'] for s in subgroups):
                result['stratification_opportunity'] = (
                    'Yes — genotype-stratified randomization or pre-planned subgroup analysis '
                    'warranted. Per textbook Ch. 9: "one would in subgroup analysis compare '
                    'treatment responses such as serious adverse events."'
                )
            elif subgroups:
                result['stratification_opportunity'] = (
                    'Possible — genes mentioned but limited GWAS validation for stratification.'
                )
            else:
                result['stratification_opportunity'] = 'No — no pharmacogenetic biomarkers detected.'
            
            n_assocs = len(relevant)
            n_subs = len(subgroups)
            n_genetic = len(genetic_requirements)
            screen_part = f" {n_genetic} genetic screen requirement(s) detected." if n_genetic else ""
            result['summary'] = (
                f"Found {n_assocs} GWAS association(s) relevant to {n_subs} pharmacogenetic subgroup(s) "
                f"in {efo_info['efo_trait']}.{screen_part} "
                f"{'Stratification opportunity identified.' if result['stratification_opportunity'].startswith('Yes') else 'No clear stratification signal.'}"
            )
        else:
            result['summary'] = (
                f'Genes detected ({", ".join(biomarkers.keys())}) but could not map indication '
                f'"{indication}" to a GWAS EFO trait. Try alternative trait name.'
            )
    else:
        result['summary'] = (
            f'Genes detected ({", ".join(biomarkers.keys())}) but indication is unknown. '
            'Cannot query GWAS without indication.'
        )
    
    return result

def analyze_trial(nct_id):
    """Full pipeline: fetch, classify design from API, then LLM-classify eligibility."""
    
    # Fetch trial data using local database + API fallback
    protocol = fetch_trial(nct_id)
    
    ident = protocol['identificationModule']
    design_mod = protocol['designModule']
    title = ident.get('briefTitle', 'N/A')
    phase = design_mod.get('phases', ['N/A'])[0] if design_mod.get('phases') else 'N/A'
    
    # --- STEP 1: Classify design from API ---
    api_design = classify_design_from_api(protocol)
    
    print(f"\n{'='*80}")
    print(f"TRIAL: {nct_id} - {title[:60]}...")
    print(f"{'='*80}")
    print(f"API-Derived Design:")
    print(f"  Design Type: {api_design['design_type']}")
    print(f"  Control: {api_design['control_type']}")
    print(f"  Superiority: {api_design['superiority_type']}")
    print(f"  Allocation: {api_design['allocation']}")
    print(f"  Model: {api_design['intervention_model']}")
    print(f"  Phases: {api_design['phases']}")
    
    # --- STEP 0a: Randomization analysis ---
    randomization = analyze_randomization(protocol)
    print(f"  Randomization: {randomization['randomization_type']}")
    print(f"  Allocation Ratio: {randomization['allocation_ratio']}")
    if randomization['stratification_factors']:
        print(f"  Stratification Factors: {', '.join(randomization['stratification_factors'][:5])}")
    
    # --- STEP 0b: Extract and classify endpoints from API ---
    outcomes_mod = protocol.get('outcomesModule', {})
    endpoints = []
    
    def classify_endpoint_type(measure, description):
        text = (measure + ' ' + (description or '')).lower()
        _ek = CONFIG['endpoint_keywords']
        safety_keywords = _ek['safety']
        qol_keywords = _ek['patient_reported']
        clinical_keywords = _ek['clinical']
        biomarker_keywords = _ek['biomarker']
        surrogate_keywords = _ek['surrogate']
        composite_keywords = _ek['composite']
        
        if any(k in text for k in safety_keywords):
            return 'Safety'
        elif any(k in text for k in composite_keywords):
            return 'Composite'
        elif any(k in text for k in clinical_keywords):
            return 'Clinical'
        elif any(k in text for k in qol_keywords):
            return 'Patient-Reported'
        elif any(k in text for k in biomarker_keywords):
            return 'Biomarker'
        elif any(k in text for k in surrogate_keywords):
            return 'Surrogate'
        else:
            return 'Surrogate'
    
    for outcome in outcomes_mod.get('primaryOutcomes', []):
        endpoints.append({
            'text': outcome['measure'],
            'endpoint_type': classify_endpoint_type(outcome['measure'], outcome.get('description', '')),
            'timeframe': outcome.get('timeFrame', 'N/A'),
            'is_primary': True
        })
    
    for outcome in outcomes_mod.get('secondaryOutcomes', []):
        endpoints.append({
            'text': outcome['measure'],
            'endpoint_type': classify_endpoint_type(outcome['measure'], outcome.get('description', '')),
            'timeframe': outcome.get('timeFrame', 'N/A'),
            'is_primary': False
        })
    
    print(f"\nEndpoints: {sum(1 for e in endpoints if e['is_primary'])} primary, {sum(1 for e in endpoints if not e['is_primary'])} secondary")
    endpoint_types = Counter(e['endpoint_type'] for e in endpoints)
    for etype, count in endpoint_types.most_common():
        print(f"  {etype}: {count}")
    
    # --- STEP 1b: Analyze study population ---
    population = analyze_study_population(protocol)
    print(f"\nPopulation:")
    print(f"  Sex: {population['sex']}")
    print(f"  Age: {population['age_range']}")
    print(f"  Age Restrictiveness: {population['age_restrictiveness']}")
    print(f"  Competing Risk Exclusions: {population['has_competing_risk_exclusions']}")
    print(f"  Recruitment Yield: {population['recruitment_yield_estimate']}")
    print(f"  Enrollment: {population['enrollment_count']} ({population['enrollment_type']})")
    
    # --- STEP 1c: Sample size / power analysis (indication-parameterized) ---
    indication = infer_indication(protocol)
    indication_key = INDICATION_ALIASES.get(indication, indication)
    if indication_key and indication_key in INDICATION_PARAMS:
        indication_params = INDICATION_PARAMS[indication_key]
        print(f"\n  Indication: {indication_key} (via LLM: '{indication}', using indication-specific power params)")
    else:
        indication_params = DEFAULT_INDICATION_PARAMS
        if indication is None:
            print(f"\n  Indication: unknown (using default power params)")
        else:
            print(f"\n  Indication: {indication} (not in lookup, using default power params)")
    
    sample_size = analyze_sample_size(protocol, endpoints, indication_params=indication_params)
    if sample_size:
        pa = sample_size['power_analysis']
        print(f"\nSample Size / Power:")
        print(f"  Enrollment: {sample_size['enrollment_actual']} ({sample_size['num_arms']} arms, ~{sample_size['estimated_n_per_arm']}/arm)")
        print(f"  Endpoint: {sample_size['primary_endpoint_type']}")
        if pa.get('detectable_hazard_ratio'):
            print(f"  Test: {pa['test_type']}")
            print(f"  Detectable HR at {pa['power_target']:.0%} power: {pa['detectable_hazard_ratio']} ({pa.get('hr_reduction', '?')} risk reduction)")
            print(f"  Expected events: {pa['expected_events']}")
            print(f"  Control median: {pa['control_median_months']}mo → treatment median: {pa['implied_treatment_median_months']}mo")
            print(f"  Implied median improvement: {pa['median_improvement_months']} months")
            print(f"  Assessment: {pa['assessment']}")
        elif pa.get('detectable_absolute_difference'):
            print(f"  Detectable Δ at {pa['power_target']:.0%} power: {pa['detectable_absolute_difference']:.0%}")
            print(f"  Power for 20% improvement: {pa['estimated_power_for_20pct_improvement']:.0%}")
            print(f"  Assessment: {pa['assessment']}")
        else:
            print(f"  Assessment: {pa['assessment']}")
    
    # --- STEP 1d: Adaptive design analysis ---
    adaptive = analyze_adaptive_design(protocol, api_design)
    print(f"\nAdaptive Designs:")
    print(f"  Has adaptive features: {adaptive['has_adaptive_features']}")
    print(f"  Types: {', '.join(adaptive['adaptive_types']) if adaptive['adaptive_types'] else 'None'}")
    print(f"  Dose-escalation method: {adaptive['dose_escalation_method'] or 'N/A'}")
    print(f"  Interim analysis: {adaptive['interim_analysis_mentioned']}")
    print(f"  Stopping rules: {adaptive['stopping_rules']}")
    
    # --- STEP 1e: Safety / Adverse Event analysis ---
    safety_ae = analyze_safety_adverse_events(protocol, endpoints)
    print(f"\nSafety / Adverse Events:")
    print(f"  AE Reporting: {safety_ae['ae_reporting_method']}")
    print(f"  Ascertainment: {safety_ae['ae_ascertainment']}")
    print(f"  AE types detected: {', '.join(safety_ae['ae_types_detected'][:5]) if safety_ae['ae_types_detected'] else 'None detected in text'}")
    print(f"  Class-specific effects: {', '.join(safety_ae['class_effects_known'][:5]) if safety_ae['class_effects_known'] else 'None detected'}")
    print(f"  Safety monitoring: {safety_ae['safety_monitoring']}")
    
    # --- STEP 1f: Pharmacogenetic / GWAS subgroup analysis ---
    # Textbook Ch. 9 (p. 172-174): GWAS enables identification of genetic subgroups
    # for differential treatment response or adverse event risk.
    # Textbook examples: imatinib/BCR-ABL, trastuzumab/HER2, gefitinib/EGFR for efficacy;
    # SLCO1B1 rs4149056 for statin-induced myopathy safety.
    pharmacogenetics = analyze_pharmacogenetics(protocol, indication)
    print(f"\nPharmacogenetics (GWAS):")
    print(f"  Genes detected: {[g['gene'] for g in pharmacogenetics['genetic_biomarkers_mentioned']] or 'None'}")
    print(f"  GWAS associations found: {len(pharmacogenetics['gwas_associations_found'])}")
    print(f"  Pharmacogenetic subgroups: {len(pharmacogenetics['pharmacogenetic_subgroups'])}")
    if pharmacogenetics.get('genetic_screen_failure'):
        for gs in pharmacogenetics['genetic_screen_failure']:
            print(f"  Genetic screen: {gs['biomarker_key']} → pop. prevalence ~{gs['population_prevalence']:.0%}, ~{gs['estimated_screen_failure_rate']:.0%} fail rate")
    print(f"  Stratification opportunity: {pharmacogenetics['stratification_opportunity']}")
    print(f"  Summary: {pharmacogenetics['summary']}")
    
    # --- STEP 2: LLM classification of eligibility (batched) ---
    eligibility_text = protocol['eligibilityModule']['eligibilityCriteria']
    eligibility = classify_eligibility_criteria(protocol, api_design, eligibility_text)
    criteria_total = len(eligibility)
    criteria_classified = len(eligibility)
    num_batches = math.ceil(criteria_total / CONFIG['llm']['batch_size']) if criteria_total > 0 else 0
    BATCH_SIZE = CONFIG['llm']['batch_size']
    
    # --- Normalize LLM output (handle typos, variant field names) ---
    competing_keywords = CONFIG['competing_keywords']
    for item in eligibility:
        # Normalize reasoning_category field
        for key in list(item.keys()):
            if 'reason' in key.lower() and 'categor' in key.lower() and key != 'reasoning_category':
                item['reasoning_category'] = item.pop(key)
            elif 'justific' in key.lower() and key != 'justification':
                item['justification'] = item.pop(key)
            # Handle 'justigation' typo
            elif 'justig' in key.lower():
                item['justification'] = item.pop(key)
        
        # Normalize category values
        cat = item.get('reasoning_category', 'Unknown')
        cat_lower = cat.lower()
        if 'feasib' in cat_lower or 'operational' in cat_lower:
            item['reasoning_category'] = 'Feasibility'
        elif 'statistical' in cat_lower or 'power' in cat_lower or 'efficacy' in cat_lower:
            item['reasoning_category'] = 'Statistical Power'
        elif 'safety' in cat_lower or 'patient protection' in cat_lower:
            item['reasoning_category'] = 'Safety'
        else:
            item['reasoning_category'] = 'Unknown'
        
        # Add competing_risk flag based on keyword detection in text
        text_lower = item.get('text', '').lower()
        item['competing_risk'] = any(k in text_lower for k in competing_keywords)
    
    # --- STEP 3: Build final output ---
    categories = Counter([
        item.get('reasoning_category', 'Unknown')
        for item in eligibility
    ])
    
    # Normalize masking to conventional textbook terms
    raw_masking = design_mod.get('designInfo', {}).get('maskingInfo', {}).get('masking', 'NONE')
    masking_map = CONFIG['masking_map']
    trial_integrity = {
        "masking_level": masking_map.get(raw_masking, raw_masking.title()),
        "blinding_validation_method": design_mod.get('designInfo', {}).get('maskingInfo', {}).get('maskingDescription', 'Not specified'),
        "concomitant_therapy_controls": "Standardized background care"
    }
    
    final_output = {
        "nct_id": nct_id,
        "title": title,
        "phase": phase,
        "eligibility": eligibility,
        "criteria_metadata": {
            "total_parsed": criteria_total,
            "classified": criteria_classified,
            "batches": num_batches,
            "batch_size": BATCH_SIZE
        },
        "population": population,
        "sample_size": sample_size,
        "endpoints": endpoints,
        "trial_integrity": trial_integrity,
        "trial_design": {
            "design_type": api_design['design_type'],
            "control_type": api_design['control_type'],
            "superiority_type": api_design['superiority_type']
        },
        "indication": indication,
        "randomization": randomization,
        "adaptive_designs": adaptive,
        "safety_adverse_events": safety_ae,
        "pharmacogenetics": pharmacogenetics,
        "summary": dict(categories)
    }
    
    # Save
    output_file = f"analysis_json/{nct_id}_analysis.json"
    with open(output_file, 'w') as f:
        json.dump(final_output, indent=2, fp=f)
    print(f"\n✓ Saved to {output_file}")
    
    # Print summary
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"Design: {api_design['design_type']}")
    print(f"Control: {api_design['control_type']}")
    print(f"Superiority: {api_design['superiority_type']}")
    print(f"Masking: {trial_integrity['masking_level']}")
    print(f"Randomization: {randomization['randomization_type']} ({randomization['allocation_ratio']})")
    if randomization['stratification_factors']:
        print(f"  Stratified by: {', '.join(randomization['stratification_factors'][:4])}")
    if sample_size:
        pa = sample_size['power_analysis']
        print(f"Power: {pa['assessment']}")
    print(f"Safety: {safety_ae['ae_reporting_method']} | AE types found: {len(safety_ae['ae_types_detected'])}")
    sf = pharmacogenetics.get('genetic_screen_failure', [])
    sf_parts = []
    for g in sf:
        bk = g['biomarker_key']
        sr = g['estimated_screen_failure_rate']
        sf_parts.append(f"{bk} ~{sr:.0%}")
    sf_str = f" | Screen fail: {', '.join(sf_parts)}" if sf_parts else ""
    print(f"Pharmacogenetics: {len(pharmacogenetics['gwas_associations_found'])} GWAS hits | {len(pharmacogenetics['pharmacogenetic_subgroups'])} subgroups{sf_str} | Stratification: {pharmacogenetics['stratification_opportunity'][:40] if pharmacogenetics['stratification_opportunity'] else 'N/A'}...")
    print(f"\nEligibility Classification:")
    for cat, count in categories.most_common():
        print(f"  {cat}: {count}")
    
    print(f"\nSample classifications:")
    for item in eligibility[:3]:
        cat = item.get('reasoning_category', 'Unknown')
        just = item.get('justification', 'N/A')
        print(f"\n  • {item['text'][:50]}...")
        print(f"    → {cat}: {just}")
    
    return final_output


# ==============================================================================
# POWER VISUALIZATION
# ==============================================================================

# Power plotting functions imported from clintrial_agent.reporting


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Clinical trial design analysis pipeline')
    parser.add_argument('--trials', nargs='+', help='NCT IDs to analyze (space-separated)')
    parser.add_argument('--comparison-name', default=None, help='Name for comparison JSON file')
    args = parser.parse_args()
    
    trials = args.trials or CONFIG['default_trials']
    comparison_name = args.comparison_name or CONFIG.get('default_comparison_name', 'portfolio')
    
    print("=" * 80)
    print("CLINICAL TRIAL DESIGN ANALYSIS")
    print("=" * 80)
    
    all_results = []
    for entry in trials:
        if isinstance(entry, dict):
            nct_id, drug = entry['nct_id'], entry.get('drug')
        elif isinstance(entry, tuple):
            nct_id, drug = entry
        else:
            nct_id, drug = entry, None
        result = analyze_trial(nct_id)
        result['drug'] = drug or result.get('drug', nct_id)
        all_results.append(result)
    
    print("\n" + "=" * 80)
    print("POWER COMPARISON")
    print("=" * 80)
    print(f"\n{'Drug':<30} {'Enroll':<8} {'Arms':<6} {'N/Arm':<6} {'Detect Δ':<10} {'Power@20%':<10} {'Assessment':<20}")
    print("-" * 100)
    for r in all_results:
        ss = r.get('sample_size')
        if ss and ss.get('power_analysis'):
            pa = ss['power_analysis']
            det = f"{pa['detectable_absolute_difference']:.0%}" if pa.get('detectable_absolute_difference') else 'N/A'
            pwr = f"{pa['estimated_power_for_20pct_improvement']:.0%}" if pa.get('estimated_power_for_20pct_improvement') else 'N/A'
        else:
            det, pwr = 'N/A', 'N/A'
        print(f"{r.get('drug', '')[:28]:<30} {ss['enrollment_actual'] if ss else 0:<8} {ss['num_arms'] if ss else 0:<6} {ss['estimated_n_per_arm'] if ss else 0:<6} {det:<10} {pwr:<10} {pa['assessment'] if ss else 'N/A':<20}")
    
    comparison = {r['nct_id']: r for r in all_results}
    comparison_path = f'analysis_json/{comparison_name}_comparison.json'
    with open(comparison_path, 'w') as f:
        json.dump(comparison, indent=2, fp=f)
    print(f"\n✓ Detailed comparison saved to {comparison_path}")
    
    print("\n" + "=" * 80)
    print("POWER VISUALIZATION")
    print("=" * 80)
    generate_power_plots(all_results)
