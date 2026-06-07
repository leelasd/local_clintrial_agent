import requests
import json
import ollama
from collections import Counter

def analyze_trial(nct_id, agent_prompt):
    """
    Fetch trial data and analyze eligibility criteria using LLM
    """
    print(f"\n{'='*80}")
    print(f"ANALYZING: {nct_id}")
    print(f"{'='*80}")
    
    # Fetch trial data
    url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
    response = requests.get(url)
    data = response.json()
    
    # Extract trial metadata
    protocol = data['protocolSection']
    ident = protocol['identificationModule']
    design = protocol['designModule']
    
    title = ident.get('briefTitle', 'N/A')
    phase = design.get('phases', ['N/A'])[0] if design.get('phases') else 'N/A'
    
    print(f"Title: {title}")
    print(f"Phase: {phase}")
    
    # Extract eligibility criteria
    eligibility_text = protocol['eligibilityModule']['eligibilityCriteria']
    
    # Parse criteria into a list
    criteria_lines = []
    for line in eligibility_text.split('\n'):
        clean_line = line.strip().lstrip('1234567890*- ')
        if clean_line and len(clean_line) > 10 and not clean_line.endswith(':'):
            criteria_lines.append(clean_line)
    
    print(f"Total criteria: {len(criteria_lines)}")
    
    # Create batch prompt (first 20 criteria for speed)
    batch_prompt = f"""{agent_prompt}

Now classify ALL of the following eligibility criteria from a clinical trial.

For each criterion, determine if it is:
- **Safety**: Protects patient from harm
- **Statistical Power**: Maximizes treatment effect detection
- **Feasibility**: Operational/data quality reasons

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

Do not use escape characters like \\^ or \\<. Write the JSON directly.
"""
    
    print("Sending to LLM...")
    response = ollama.chat(
        model='gemma3:1b',
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
        eligibility = json.loads(json_text)
        print(f"✓ Parsed {len(eligibility)} classifications")
        
    except json.JSONDecodeError as e:
        print(f"✗ JSON parse error: {e}")
        eligibility = []
    
    # Extract trial integrity
    trial_integrity = {
        "masking_level": design.get('designInfo', {}).get('maskingInfo', {}).get('masking', 'None'),
        "blinding_validation_method": "Not specified",
        "concomitant_therapy_controls": "Standardized background care"
    }
    
    # Categorize
    categories = Counter([
        item.get('reasoning_category') or item.get('reasonging_category', 'Unknown') 
        for item in eligibility
    ])
    
    result = {
        'nct_id': nct_id,
        'title': title,
        'phase': phase,
        'eligibility': eligibility,
        'trial_integrity': trial_integrity,
        'summary': dict(categories)
    }
    
    print("\nCategory Summary:")
    for cat, count in categories.items():
        print(f"  {cat}: {count}")
    
    return result


# Load agent prompt
with open('agent_prompt.txt', 'r') as f:
    agent_prompt = f.read()

# Trial 1: NCT04167462 - Deucravacitinib (APPROVED - SOTYKTU) Phase 3 psoriasis
trial1 = analyze_trial('NCT04167462', agent_prompt)

# Trial 2: NCT06220604 - JNJ-77242113 (INVESTIGATIONAL) Phase 3 psoriasis
trial2 = analyze_trial('NCT06220604', agent_prompt)

# Save individual results
with open(f"{trial1['nct_id']}_analysis.json", 'w') as f:
    json.dump(trial1, indent=2, fp=f)

with open(f"{trial2['nct_id']}_analysis.json", 'w') as f:
    json.dump(trial2, indent=2, fp=f)

# Create comparison
print(f"\n{'='*80}")
print("COMPARISON: APPROVED vs INVESTIGATIONAL TYK2 INHIBITOR")
print(f"{'='*80}")

comparison = {
    'approved_trial': {
        'nct_id': trial1['nct_id'],
        'title': trial1['title'],
        'phase': trial1['phase'],
        'category_counts': trial1['summary']
    },
    'investigational_trial': {
        'nct_id': trial2['nct_id'],
        'title': trial2['title'],
        'phase': trial2['phase'],
        'category_counts': trial2['summary']
    },
    'comparison_insights': {}
}

print(f"\n1. APPROVED: Deucravacitinib (SOTYKTU)")
print(f"   NCT ID: {trial1['nct_id']}")
print(f"   Phase: {trial1['phase']}")
print(f"   Category breakdown:")
for cat, count in trial1['summary'].items():
    print(f"     {cat}: {count}")

print(f"\n2. INVESTIGATIONAL: JNJ-77242113")
print(f"   NCT ID: {trial2['nct_id']}")
print(f"   Phase: {trial2['phase']}")
print(f"   Category breakdown:")
for cat, count in trial2['summary'].items():
    print(f"     {cat}: {count}")

# Calculate differences
print(f"\n{'='*80}")
print("KEY DIFFERENCES:")
print(f"{'='*80}")

for category in ['Safety', 'Statistical Power', 'Feasibility']:
    count1 = trial1['summary'].get(category, 0)
    count2 = trial2['summary'].get(category, 0)
    diff = count2 - count1
    
    if diff != 0:
        direction = "more" if diff > 0 else "fewer"
        print(f"\n{category}:")
        print(f"  Investigational trial has {abs(diff)} {direction} {category.lower()} criteria")
        print(f"  ({count1} → {count2})")

# Save comparison
with open('tyk2_comparison.json', 'w') as f:
    json.dump(comparison, indent=2, fp=f)

print(f"\n{'='*80}")
print("✓ Analysis complete!")
print(f"  - {trial1['nct_id']}_analysis.json")
print(f"  - {trial2['nct_id']}_analysis.json")
print(f"  - tyk2_comparison.json")
print(f"{'='*80}")
