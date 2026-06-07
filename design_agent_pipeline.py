import requests
import json
import ollama
from collections import Counter

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
        "endpoints": endpoints,
        "trial_integrity": trial_integrity,
        "trial_design": {
            "design_type": api_design['design_type'],
            "control_type": api_design['control_type'],
            "superiority_type": api_design['superiority_type']
        },
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
    # Test on Zasocitinib (TAK-279) trial
    result = analyze_trial('NCT06088043')
