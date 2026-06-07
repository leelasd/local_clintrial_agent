import requests
import json
import math
import ollama
from collections import Counter
from scipy import stats

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
    elif allocation != 'RANDOMIZED' and intervention_model == 'PARALLEL':
        design_type = 'Nonrandomized Concurrent Control'
    elif intervention_model == 'PARALLEL':
        design_type = 'Parallel RCT'
    else:
        design_type = 'Other'
    
    # Determine superiority_type from phase and purpose
    # Noninferiority/equivalence trials are more common in Phase 3 with active comparators
    if control_type == 'Active Comparator' and 'PHASE3' in phases:
        superiority_type = 'Noninferiority'
    elif control_type == 'Placebo':
        superiority_type = 'Superiority'
    elif control_type == 'None (Single-Arm)':
        superiority_type = 'Unclear'
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
    competing_keywords = ['cancer', 'malignancy', 'neoplasm', 'tumor', 'liver disease', 
                          'renal disease', 'kidney disease', 'organ failure', 'transplant',
                          'hiv', 'aids', 'hepatitis', 'cirrhosis', 'dialysis']
    has_competing_risks = any(k in criteria_text for k in competing_keywords)
    
    # Estimate recruitment yield based on restrictiveness
    restrictive_count = 0
    if sex != 'ALL':
        restrictive_count += 1
    if max_age != 'N/A' or min_age != 'N/A':
        restrictive_count += 1
    if healthy_vol:
        restrictive_count -= 1  # healthy volunteers are LESS restrictive
    
    if restrictive_count >= 2:
        recruitment_yield = 'Low (<5% screen-to-enroll)'
    elif restrictive_count >= 1:
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

def analyze_sample_size(protocol, endpoints):
    """Compute sample size and power analysis using actual enrollment and primary endpoint."""
    design_mod = protocol.get('designModule', {})
    arms = protocol.get('armsInterventionsModule', {})
    arm_groups = arms.get('armGroups', [])
    enrollment_info = design_mod.get('enrollmentInfo', {})
    enrollment = enrollment_info.get('count', 0)
    
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
    
    # Check if dichotomous (proportion-based endpoint)
    dichotomous_keywords = ['percentage', 'proportion', 'number of', 'achieving', 'response', 'rate']
    is_dichotomous = any(k in primary_text.lower() for k in dichotomous_keywords)
    
    # For psoriasis trials, typical placebo response rate for sPGA/PASI is ~10-15%
    estimated_control_rate = 0.10
    alpha = 0.05
    power_target = 0.80
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power_target)
    
    if is_dichotomous and n_per_arm > 1:
        # Compute minimum detectable absolute difference at target power
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
        p1_realistic = estimated_control_rate + 0.20
        phat_realistic = (estimated_control_rate + p1_realistic) / 2
        se_realistic = math.sqrt(2 * phat_realistic * (1 - phat_realistic) / n_per_arm)
        z_realistic = 0.20 / se_realistic if se_realistic > 0 else 0
        power_realistic = stats.norm.cdf(z_realistic - z_alpha)
        
        # Assessment
        if detectable_diff is None:
            assessment = 'Cannot determine'
        elif detectable_diff <= 0.10:
            assessment = 'Adequately Powered'
        elif detectable_diff <= 0.15:
            assessment = 'Borderline'
        elif detectable_diff <= 0.25:
            assessment = 'Underpowered'
        else:
            assessment = 'Severely Underpowered'
        
        return {
            'enrollment_actual': enrollment,
            'estimated_n_per_arm': n_per_arm,
            'num_arms': num_arms,
            'primary_endpoint_type': 'Dichotomous (Proportion)',
            'estimated_control_event_rate': estimated_control_rate,
            'power_analysis': {
                'alpha': alpha,
                'power_target': power_target,
                'test_type': 'Two-sided',
                'detectable_absolute_difference': round(detectable_diff, 3) if detectable_diff else None,
                'estimated_power_for_20pct_improvement': round(power_realistic, 3),
                'assessment': assessment
            }
        }
    
    # Non-dichotomous endpoint — just report enrollment
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
            'assessment': 'Power analysis requires dichotomous endpoint'
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
    factor_keywords = [
        'site', 'center', 'study site', 'study center',
        'region', 'geographic',
        'baseline', 'disease severity', 'pasi', 'psoriasis severity',
        'body weight', 'bmi',
        'prior biologic', 'prior treatment', 'previous therapy',
        'age', 'sex', 'gender',
        'smoking',
    ]
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
    adaptive_signals = {
        'Group Sequential': [
            'group sequential', 'interim analysis', 'interim look', 'interim monitoring',
            'dsmb', 'data safety monitoring board', 'data monitoring committee',
            'stopping rule', 'stopping boundary', 'early stopping', 'early termination',
            'obrien', 'pocock', 'lan-demets'
        ],
        'Sample Size Re-estimation': [
            'sample size re-estimation', 'sample size reestimation', 'sample size adjustment',
            're-estimate sample size', 'adaptive sample size', 'event-driven', 'event driven',
            'number of events', 'target number of events'
        ],
        'Response-Adaptive Randomization': [
            'response-adaptive', 'response adaptive', 'adaptive randomization',
            'outcome-adaptive', 'play the winner', 'minimization'
        ],
        'Basket Trial': [
            'basket trial', 'basket design', 'histology-independent', 'tumor-agnostic',
            'multiple tumor types', 'multiple indications', 'same genetic'
        ],
        'Umbrella Trial': [
            'umbrella trial', 'umbrella design', 'multiple study drugs',
            'multiple targeted therapies', 'subtype-matched'
        ],
        'Platform Trial': [
            'platform trial', 'platform design', 'master protocol', 'basket/umbrella platform',
            'add new arms', 'drop arm', 'add experimental arm', 'shared control',
            'permanently open'
        ],
        'Dose-Finding / Phase I': [
            '3+3', '3 plus 3', 'rolling six', 'bayesian', 'continual reassessment',
            'crm design', 'dose escalation', 'dose de-escalation', 'dose finding',
            'mtd', 'maximum tolerated dose'
        ],
        'Seamless Phase 2/3': [
            'seamless phase 2', 'seamless phase 2/3', 'adaptive seamless',
            'phase 2/3 adaptive', 'phase 2/3 seamless'
        ],
    }
    
    adaptive_types = []
    for design_type, keywords in adaptive_signals.items():
        if any(k in description_text for k in keywords):
            adaptive_types.append(design_type)
    
    # Also flag from API: SEQUENTIAL model always means adaptive
    if intervention_model == 'SEQUENTIAL' and 'Group Sequential' not in adaptive_types:
        adaptive_types.append('Group Sequential')
    
    # Phase 1 trials are inherently dose-finding (adaptive)
    is_phase1 = any('PHASE1' in p for p in phases)
    if is_phase1 and 'Dose-Finding / Phase I' not in adaptive_types:
        adaptive_types.append('Dose-Finding / Phase I')
    
    # Look for specific stopping rules
    stopping_rules = 'Not mentioned'
    if any(k in description_text for k in ['obrien', 'obrien-fleming', 'obrien fleming', "o'brien"]):
        stopping_rules = "O'Brien-Fleming boundary"
    elif any(k in description_text for k in ['pocock']):
        stopping_rules = 'Pocock boundary'
    elif any(k in description_text for k in ['lan-demets', 'lan demets']):
        stopping_rules = "Lan-DeMets alpha spending function"
    elif any(k in description_text for k in ['haybittle-peto', 'haybittle peto']):
        stopping_rules = 'Haybittle-Peto boundary'
    elif any(k in description_text for k in ['stopping rule', 'stopping boundary']):
        stopping_rules = 'Specified (details not available from text)'
    
    interim_analysis = any(k in description_text for k in [
        'interim analysis', 'interim look', 'interim monitoring', 'interim data'
    ])
    
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
    
    return {
        'has_adaptive_features': has_adaptive,
        'adaptive_types': adaptive_types,
        'interim_analysis_mentioned': interim_analysis,
        'stopping_rules': stopping_rules,
        'description': description
    }

def analyze_trial(nct_id):
    """Full pipeline: fetch, classify design from API, then LLM-classify eligibility."""
    
    # Fetch trial data
    url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
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
        safety_keywords = ['adverse event', 'tolerability', 'safety', 'clinically significant', 'laboratory', 'ecg', 'vital sign']
        qol_keywords = ['quality of life', 'qol', 'patient-reported', 'questionnaire', 'sf-36', 'eq-5d', 'dlqi', 'pssd', 'wpai']
        clinical_keywords = ['death', 'mortality', 'survival', 'stroke', 'infarction', 'hospitalization', 'fracture']
        biomarker_keywords = ['concentration', 'level', 'biomarker', 'gene', 'genetic', 'pcr', 'assay']
        composite_keywords = ['composite', 'mace', 'combined', 'major adverse']
        
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
    
    # --- STEP 1c: Sample size / power analysis ---
    sample_size = analyze_sample_size(protocol, endpoints)
    if sample_size:
        pa = sample_size['power_analysis']
        print(f"\nSample Size / Power:")
        print(f"  Enrollment: {sample_size['enrollment_actual']} ({sample_size['num_arms']} arms, ~{sample_size['estimated_n_per_arm']}/arm)")
        print(f"  Endpoint: {sample_size['primary_endpoint_type']}")
        if pa['detectable_absolute_difference']:
            print(f"  Detectable Δ at {pa['power_target']:.0%} power: {pa['detectable_absolute_difference']:.0%}")
            print(f"  Power for 20% improvement: {pa['estimated_power_for_20pct_improvement']:.0%}")
            print(f"  Assessment: {pa['assessment']}")
    
    # --- STEP 1d: Adaptive design analysis ---
    adaptive = analyze_adaptive_design(protocol, api_design)
    print(f"\nAdaptive Designs:")
    print(f"  Has adaptive features: {adaptive['has_adaptive_features']}")
    print(f"  Types: {', '.join(adaptive['adaptive_types']) if adaptive['adaptive_types'] else 'None'}")
    print(f"  Interim analysis: {adaptive['interim_analysis_mentioned']}")
    print(f"  Stopping rules: {adaptive['stopping_rules']}")
    
    # --- STEP 2: LLM classification of eligibility ---
    eligibility_text = protocol['eligibilityModule']['eligibilityCriteria']
    
    with open('agent_prompt.txt', 'r') as f:
        agent_prompt = f.read()
    
    # Parse criteria into a list
    criteria_lines = []
    for line in eligibility_text.split('\n'):
        clean_line = line.strip().lstrip('1234567890*- ')
        if clean_line and len(clean_line) > 10 and not clean_line.endswith(':'):
            criteria_lines.append(clean_line)
    
    print(f"\nTotal criteria: {len(criteria_lines)}")
    
    # Create batch prompt with design context included
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
    
    for i, criterion in enumerate(criteria_lines[:20], 1):
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
    
    print("\nSending batch to LLM for eligibility classification...")
    response = ollama.chat(
        model='gemma2:2b-instruct-q4_K_M',
        messages=[{'role': 'user', 'content': batch_prompt}],
        options={'temperature': 0.1, 'num_predict': 4096}
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
        # Strip any remaining stray backslashes that would break JSON
        json_text = json_text.replace('\\', '/')
        eligibility = json.loads(json_text)
        print(f"  ✓ Parsed {len(eligibility)} criteria")
        
    except json.JSONDecodeError as e:
        print(f"  ✗ JSON parse error: {e}")
        print(f"  Problem text (first 200 chars): {json_text[:200]}")
        eligibility = []
    
    # --- Normalize LLM output (handle typos, variant field names) ---
    competing_keywords = ['cancer', 'malignancy', 'neoplasm', 'tumor', 'liver disease', 
                          'renal disease', 'kidney disease', 'organ failure', 'transplant',
                          'hiv', 'aids', 'hepatitis', 'cirrhosis', 'dialysis']
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
    masking_map = {
        'NONE': 'Open-label',
        'SINGLE': 'Single-blind',
        'DOUBLE': 'Double-blind',
        'TRIPLE': 'Double-blind',
        'QUADRUPLE': 'Double-blind',
    }
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
        "population": population,
        "sample_size": sample_size,
        "endpoints": endpoints,
        "trial_integrity": trial_integrity,
        "trial_design": {
            "design_type": api_design['design_type'],
            "control_type": api_design['control_type'],
            "superiority_type": api_design['superiority_type']
        },
        "randomization": randomization,
        "adaptive_designs": adaptive,
        "summary": dict(categories)
    }
    
    # Save
    output_file = f"{nct_id}_analysis.json"
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
    trials = [
        ('NCT06088043', 'Zasocitinib (TAK-279)'),
        ('NCT04167462', 'Deucravacitinib (BMS-986165)'),
        ('NCT06220604', 'JNJ-77242113'),
    ]
    
    print("=" * 80)
    print("TYK2 INHIBITOR TRIAL ANALYSIS")
    print("=" * 80)
    
    all_results = []
    for nct_id, drug in trials:
        result = analyze_trial(nct_id)
        result['drug'] = drug
        all_results.append(result)
    
    print("\n" + "=" * 80)
    print("POWER COMPARISON ACROSS TYK2 TRIALS")
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
    
    # Save combined comparison
    comparison = {r['nct_id']: r for r in all_results}
    with open('tyk2_comparison.json', 'w') as f:
        json.dump(comparison, indent=2, fp=f)
    print(f"\n✓ Detailed comparison saved to tyk2_comparison.json")
