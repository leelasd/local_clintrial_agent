import requests
import json
import math
import ollama
import argparse
from pathlib import Path
from collections import Counter
from scipy import stats
import yaml


def _load_config(config_path=None):
    if config_path is None:
        config_path = Path(__file__).parent / 'pipeline_config.yaml'
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


CONFIG = _load_config()

INDICATION_PARAMS = CONFIG['indication_params']

DEFAULT_INDICATION_PARAMS = CONFIG['default_indication_params']


def infer_indication(protocol):
    """Infer therapeutic indication from protocol conditions and title."""
    conditions = protocol.get('conditionModule', {}).get('conditions', [])
    title = protocol.get('identificationModule', {}).get('briefTitle', '')
    combined = ' '.join(conditions + [title]).lower()

    indication_keywords = CONFIG['indication_keywords']

    for indication, keywords in indication_keywords.items():
        if any(k in combined for k in keywords):
            return indication

    return None


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

def analyze_sample_size(protocol, endpoints, indication_params=None):
    """Compute sample size and power analysis using actual enrollment and primary endpoint.
    
    Args:
        protocol: Protocol section from ClinicalTrials.gov API
        endpoints: List of classified endpoints
        indication_params: Dict with keys like 'control_rate_dichotomous',
            'median_os_months', 'median_pfs_months', 'event_rate'.
            If None, falls back to DEFAULT_INDICATION_PARAMS.
    """
    if indication_params is None:
        indication_params = DEFAULT_INDICATION_PARAMS
    
    design_mod = protocol.get('designModule', {})
    arms = protocol.get('armsInterventionsModule', {})
    arm_groups = arms.get('armGroups', [])
    enrollment_info = design_mod.get('enrollmentInfo', {})
    enrollment = enrollment_info.get('count', 0)
    phases = design_mod.get('phases', [])
    
    if not enrollment:
        return None
    
    # Phase 1 dose-escalation trials are not powered for efficacy
    is_phase1 = any('PHASE1' in p for p in phases)
    if is_phase1:
        interventional_arms = [a for a in arm_groups if a.get('type') != 'NO_INTERVENTION']
        num_arms = len(interventional_arms)
        n_per_arm = max(1, enrollment // num_arms) if num_arms > 0 else enrollment
        return {
            'enrollment_actual': enrollment,
            'estimated_n_per_arm': n_per_arm,
            'num_arms': num_arms,
            'primary_endpoint_type': 'Safety / Dose-Finding',
            'power_analysis': {
                'alpha': None,
                'power_target': None,
                'test_type': 'N/A (Phase 1 dose-escalation)',
                'detectable_absolute_difference': None,
                'estimated_power_for_20pct_improvement': None,
                'assessment': 'N/A — Phase 1 trial, not powered for efficacy'
            }
        }
    
    if not enrollment:
        return None
    
    # Count interventional arms (exclude NO_INTERVENTION)
    interventional_arms = [a for a in arm_groups if a.get('type') != 'NO_INTERVENTION']
    num_arms = len(interventional_arms)
    n_per_arm = max(1, enrollment // num_arms) if num_arms > 0 else enrollment
    
    # Determine primary endpoint type
    primary_endpoints = [e for e in endpoints if e.get('is_primary')]
    primary_text = primary_endpoints[0]['text'] if primary_endpoints else ''
    primary_type = primary_endpoints[0]['endpoint_type'] if primary_endpoints else 'Unknown'
    
    # Common parameters
    alpha = CONFIG['alpha']
    power_target = CONFIG['power_target']
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power_target)
    
    # Check if survival/time-to-event endpoint (PFS, OS)
    # Use word-boundary matching to avoid false positives (e.g. "os" matching inside "close")
    primary_lower = primary_text.lower() + ' '
    survival_keywords = CONFIG['survival_keywords']
    is_survival = any(k in primary_lower for k in survival_keywords)
    
    dichotomous_keywords = CONFIG['dichotomous_keywords']
    is_dichotomous = any(k in primary_text.lower() for k in dichotomous_keywords)
    
    if is_survival and n_per_arm > 1:
        is_os = any(k in primary_text.lower() for k in ['overall survival', 'os'])
        median_key = 'median_os_months' if is_os else 'median_pfs_months'
        return _analyze_survival_power(primary_text, enrollment, n_per_arm, num_arms,
                                       alpha, power_target, z_alpha, z_beta,
                                       control_median_months=indication_params.get(median_key),
                                       event_rate=indication_params.get('event_rate'))
    
    if is_dichotomous and n_per_arm > 1:
        return _analyze_dichotomous_power(primary_text, enrollment, n_per_arm, num_arms,
                                           alpha, power_target, z_alpha, z_beta, primary_type,
                                           estimated_control_rate=indication_params.get('control_rate_dichotomous', CONFIG['default_control_rate_dichotomous']))
    
    # Non-dichotomous, non-survival endpoint
    return {
        'enrollment_actual': enrollment,
        'estimated_n_per_arm': n_per_arm,
        'num_arms': num_arms,
        'primary_endpoint_type': primary_type,
        'estimated_control_event_rate': None,
        'power_analysis': {
            'alpha': alpha,
            'power_target': power_target,
            'test_type': 'Two-sided',
            'detectable_absolute_difference': None,
            'estimated_power_for_20pct_improvement': None,
            'assessment': 'Power analysis uses dichotomous or survival endpoints'
        }
    }


def _analyze_dichotomous_power(primary_text, enrollment, n_per_arm, num_arms,
                                alpha, power_target, z_alpha, z_beta, primary_type,
                                estimated_control_rate=CONFIG['default_control_rate_dichotomous']):
    """Power analysis for dichotomous (proportion-based) endpoints."""
    
    def compute_detectable_diff(n, p0, za, zb):
        for delta_p in [x / 100 for x in range(1, 50)]:
            p1 = p0 + delta_p
            phat = (p0 + p1) / 2
            se = math.sqrt(2 * phat * (1 - phat) / n)
            if se == 0:
                continue
            z = delta_p / se
            est_power = stats.norm.cdf(z - za)
            if est_power >= power_target:
                return delta_p
        return None
    
    detectable_diff = compute_detectable_diff(n_per_arm, estimated_control_rate, z_alpha, z_beta)
    
    # Estimate power for a realistic 20% absolute improvement
    _realistic = CONFIG['realistic_improvement_absolute']
    p1_realistic = estimated_control_rate + _realistic
    phat_realistic = (estimated_control_rate + p1_realistic) / 2
    se_realistic = math.sqrt(2 * phat_realistic * (1 - phat_realistic) / n_per_arm)
    z_realistic = _realistic / se_realistic if se_realistic > 0 else 0
    power_realistic = stats.norm.cdf(z_realistic - z_alpha)
    
    # Assessment
    _thresh = CONFIG['dichotomous_power_assessment']
    if detectable_diff is None:
        assessment = 'Cannot determine'
    elif detectable_diff <= _thresh['adequately_powered']:
        assessment = 'Adequately Powered'
    elif detectable_diff <= _thresh['borderline']:
        assessment = 'Borderline'
    elif detectable_diff <= _thresh['underpowered']:
        assessment = 'Underpowered'
    else:
        assessment = 'Severely Underpowered'
    
    return {
        'enrollment_actual': enrollment,
        'estimated_n_per_arm': n_per_arm,
        'num_arms': num_arms,
        'primary_endpoint_type': 'Dichotomous (Proportion)',
        'estimated_control_event_rate': estimated_control_rate,
        'indication_params_used': {'control_rate_dichotomous': estimated_control_rate},
        'power_analysis': {
            'alpha': alpha,
            'power_target': power_target,
            'test_type': 'Two-sided',
            'detectable_absolute_difference': round(detectable_diff, 3) if detectable_diff else None,
            'estimated_power_for_20pct_improvement': round(power_realistic, 3),
            'assessment': assessment
        }
    }


def _analyze_survival_power(primary_text, enrollment, n_per_arm, num_arms,
                             alpha, power_target, z_alpha, z_beta,
                             control_median_months=None, event_rate=None):
    """Power analysis for time-to-event (survival) endpoints using Schoenfeld formula.
    
    Uses the event-count based approach:
        D = (Z_alpha + Z_beta)^2 / [p(1-p) * ln(HR)^2]
    
    where D = required total number of events, p = proportion randomized to treatment.
    For power given fixed N, we estimate expected total events and solve for
    detectable hazard ratio: ln(HR) = sqrt((Zα+Zβ)² / [D * p(1-p)])
    """
    # Determine endpoint type from text
    is_os = any(k in primary_text.lower() for k in ['overall survival', 'os'])
    endpoint_label = 'OS (Overall Survival)' if is_os else 'PFS (Progression-Free Survival)'
    
    # Use provided values or fall back to defaults
    if control_median_months is None:
        control_median_months = CONFIG['survival_defaults']['control_median_os_months'] if is_os else CONFIG['survival_defaults']['control_median_pfs_months']
    if event_rate is None:
        event_rate = CONFIG['survival_defaults']['event_rate']

    p_alloc = 1.0 / num_arms
    
    expected_events = enrollment * event_rate
    denom = expected_events * p_alloc * (1 - p_alloc)
    
    if denom <= 0:
        return {
            'enrollment_actual': enrollment,
            'estimated_n_per_arm': n_per_arm,
            'num_arms': num_arms,
            'primary_endpoint_type': endpoint_label,
            'estimated_control_event_rate': event_rate,
            'power_analysis': {
                'alpha': alpha,
                'power_target': power_target,
                'test_type': 'Two-sided (log-rank)',
                'detectable_hazard_ratio': None,
                'expected_events': round(expected_events),
                'control_median_months': control_median_months,
                'assessment': 'Cannot compute (insufficient expected events)'
            }
        }
    
    log_hr = math.sqrt((z_alpha + z_beta) ** 2 / denom)
    # Take the negative root: treatment is expected to reduce hazard (HR < 1)
    detectable_hr = math.exp(-log_hr)
    
    # detectable_hr is the hazard ratio (treatment / control)
    # HR < 1 means treatment benefit; HR > 1 means control better
    # For a superiority trial, we want detectable_hr < 1
    
    _thresh = CONFIG['survival_power_assessment']
    if detectable_hr <= _thresh['adequately_powered']:
        assessment = 'Adequately Powered'
    elif detectable_hr <= _thresh['borderline']:
        assessment = 'Borderline'
    elif detectable_hr <= _thresh['underpowered']:
        assessment = 'Underpowered'
    else:
        assessment = 'Severely Underpowered'
    
    # Compute implied treatment median
    treatment_median = control_median_months / detectable_hr
    
    return {
        'enrollment_actual': enrollment,
        'estimated_n_per_arm': n_per_arm,
        'num_arms': num_arms,
        'primary_endpoint_type': endpoint_label,
        'estimated_control_event_rate': event_rate,
        'indication_params_used': {
            'control_median_months': control_median_months,
            'event_rate': event_rate,
        },
        'power_analysis': {
            'alpha': alpha,
            'power_target': power_target,
            'test_type': 'Two-sided (log-rank)',
            'detectable_hazard_ratio': round(detectable_hr, 3),
            'hr_reduction': f"{(1 - detectable_hr) * 100:.0f}%",
            'expected_events': round(expected_events),
            'control_median_months': control_median_months,
            'implied_treatment_median_months': round(treatment_median, 1),
            'median_improvement_months': round(treatment_median - control_median_months, 1),
            'assessment': assessment
        }
    }

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

def analyze_trial(nct_id):
    """Full pipeline: fetch, classify design from API, then LLM-classify eligibility."""
    
    # Fetch trial data
    url = f"{CONFIG['api_base_url']}/{nct_id}"
    response = requests.get(url)
    data = response.json()
    protocol = data['protocolSection']
    
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
    if indication and indication in INDICATION_PARAMS:
        indication_params = INDICATION_PARAMS[indication]
        print(f"\n  Indication detected: {indication} (using indication-specific power params)")
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
    
    # --- STEP 2: LLM classification of eligibility (batched) ---
    eligibility_text = protocol['eligibilityModule']['eligibilityCriteria']
    
    with open('agent_prompt.txt', 'r') as f:
        agent_prompt = f.read()
    
    # Parse criteria into a list
    criteria_lines = []
    for line in eligibility_text.split('\n'):
        clean_line = line.strip().lstrip('1234567890*- ')
        if clean_line and len(clean_line) > 10 and not clean_line.endswith(':'):
            criteria_lines.append(clean_line)
    
    criteria_total = len(criteria_lines)
    print(f"\nTotal criteria: {criteria_total}")
    
    # Build design context (shared across all batches)
    design_context = f"""
TRIAL DESIGN CONTEXT (extracted from structured API data):
- Design: {api_design['design_type']}
- Control: {api_design['control_type']}
- Superiority: {api_design['superiority_type']}
- Allocation: {api_design['allocation']}
- Intervention Model: {api_design['intervention_model']}
- Masking: {design_mod.get('designInfo', {}).get('maskingInfo', {}).get('masking', 'N/A')}
- Phases: {api_design['phases']}
"""

    BATCH_SIZE = CONFIG['llm']['batch_size']
    num_batches = math.ceil(criteria_total / BATCH_SIZE) if criteria_total > 0 else 0
    eligibility = []
    
    for batch_idx in range(num_batches):
        batch_start = batch_idx * BATCH_SIZE
        batch_end = min(batch_start + BATCH_SIZE, criteria_total)
        batch_criteria = criteria_lines[batch_start:batch_end]
        
        batch_prompt = f"""{agent_prompt}

{design_context}

Now classify ALL of the following eligibility criteria from this clinical trial.

For each criterion, determine if it is:
- **Safety**: Protects patient from harm
- **Statistical Power**: Maximizes treatment effect detection
- **Feasibility**: Operational/data quality reasons

Use the trial design context above to inform your classifications. For example:
- In a noninferiority trial, criteria that ensure the population matches historical placebo-controlled trials serve Statistical Power.
- In an active comparator trial, criteria excluding patients who cannot tolerate the comparator serve Safety.

CRITERIA LIST:
"""
        
        for i, criterion in enumerate(batch_criteria, 1):
            batch_prompt += f"{i}. {criterion}\n"
        
        batch_prompt += """
IMPORTANT: Respond ONLY in English. Use proper JSON syntax with no escape characters.

Respond with ONLY a valid JSON array. Each object must have:
- "text": the criterion text (copy exactly as provided)
- "reasoning_category": one of "Safety", "Statistical Power", or "Feasibility"
- "justification": brief 1-sentence explanation in English

Format:
[
  {"text": "...", "reasoning_category": "Safety", "justification": "..."},
  {"text": "...", "reasoning_category": "Statistical Power", "justification": "..."}
]

Do not use escape characters. Write the JSON directly.
"""
        
        batch_label = f"batch {batch_idx + 1}/{num_batches}" if num_batches > 1 else "batch"
        print(f"\nSending {batch_label} ({len(batch_criteria)} criteria) to LLM for eligibility classification...")
        response = ollama.chat(
            model=CONFIG['llm']['model'],
            messages=[{'role': 'user', 'content': batch_prompt}],
            options={'temperature': CONFIG['llm']['temperature'], 'num_predict': CONFIG['llm']['num_predict']}
        )
        
        response_text = response['message']['content'].strip()
        
        # Parse JSON
        try:
            if '```json' in response_text:
                start = response_text.find('```json') + 7
                end = response_text.find('```', start)
                json_text = response_text[start:end].strip()
            elif '```' in response_text:
                start = response_text.find('```') + 3
                end = response_text.find('```', start)
                json_text = response_text[start:end].strip()
            else:
                start = response_text.find('[')
                end = response_text.rfind(']') + 1
                json_text = response_text[start:end]
            
            json_text = json_text.replace('\\^', '^').replace('\\<', '<').replace('\\>', '>')
            json_text = json_text.replace('\\', '/')
            batch_results = json.loads(json_text)
            eligibility.extend(batch_results)
            print(f"  ✓ Parsed {len(batch_results)} criteria from {batch_label}")
            
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON parse error in {batch_label}: {e}")
            print(f"  Problem text (first 200 chars): {json_text[:200]}")
    
    criteria_classified = len(eligibility)
    if criteria_total != criteria_classified:
        print(f"\n  ⚠ Classified {criteria_classified}/{criteria_total} criteria ({criteria_total - criteria_classified} unclassified)")
    
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
