import math
from scipy import stats
from clintrial_agent.config import CONFIG, DEFAULT_INDICATION_PARAMS

def analyze_sample_size(protocol, endpoints, indication_params=None):
    """Compute sample size and power analysis using actual enrollment and primary endpoint.
    
    Args:
        protocol: Protocol section from ClinicalTrials.gov API / DB adapter
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
    """Power analysis for time-to-event (survival) endpoints using Schoenfeld formula."""
    is_os = any(k in primary_text.lower() for k in ['overall survival', 'os'])
    endpoint_label = 'OS (Overall Survival)' if is_os else 'PFS (Progression-Free Survival)'
    
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
    detectable_hr = math.exp(-log_hr)
    
    _thresh = CONFIG['survival_power_assessment']
    if detectable_hr <= _thresh['adequately_powered']:
        assessment = 'Adequately Powered'
    elif detectable_hr <= _thresh['borderline']:
        assessment = 'Borderline'
    elif detectable_hr <= _thresh['underpowered']:
        assessment = 'Underpowered'
    else:
        assessment = 'Severely Underpowered'
    
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

def _dichotomous_power_curve(n_per_arm, control_rate, delta, alpha=0.05):
    """Compute power for a dichotomous endpoint at a given absolute difference."""
    p1 = control_rate + delta
    phat = (control_rate + p1) / 2
    se = math.sqrt(2 * phat * (1 - phat) / n_per_arm)
    if se == 0:
        return 0
    z = delta / se
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    return stats.norm.cdf(z - z_alpha)

def _survival_power_curve(n_per_arm, num_arms, hr, event_rate, alpha=0.05):
    """Compute power for a survival endpoint at a given hazard ratio (Schoenfeld)."""
    expected_events = n_per_arm * num_arms * event_rate
    p_alloc = 1.0 / num_arms
    denom = expected_events * p_alloc * (1 - p_alloc)
    if denom <= 0:
        return 0
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_hr = math.log(hr)
    z = abs(z_hr) * math.sqrt(denom)
    return stats.norm.cdf(z - z_alpha)
