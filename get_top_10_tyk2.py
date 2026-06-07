import requests
import json
from datetime import datetime, timedelta

# Search for TYK2 trials from last 2 years
search_url = "https://clinicaltrials.gov/api/v2/studies"

# Calculate date 2 years ago
two_years_ago = datetime.now() - timedelta(days=730)
date_filter = two_years_ago.strftime("%Y-%m-%d")

params = {
    "query.term": "TYK2 inhibitor OR deucravacitinib OR BMS-986165 OR zasocitinib OR TAK-279 OR JNJ-77242113",
    "filter.overallStatus": "RECRUITING,ACTIVE_NOT_RECRUITING,COMPLETED,NOT_YET_RECRUITING",
    "pageSize": 50
}

print("Searching for TYK2 inhibitor trials from last 2 years...")
print("=" * 80)

response = requests.get(search_url, params=params)
data = response.json()

trials = data.get('studies', [])
print(f"Found {len(trials)} total TYK2 inhibitor trials\n")

# Already analyzed trials
analyzed = ['NCT04167462', 'NCT06220604', 'NCT06088043']

# Filter and rank trials
trial_list = []
for study in trials:
    protocol = study.get('protocolSection', {})
    ident = protocol.get('identificationModule', {})
    status_mod = protocol.get('statusModule', {})
    design = protocol.get('designModule', {})
    conditions = protocol.get('conditionsModule', {})
    interventions = protocol.get('armsInterventionsModule', {})
    
    nct_id = ident.get('nctId', 'N/A')
    
    # Skip already analyzed
    if nct_id in analyzed:
        continue
    
    title = ident.get('briefTitle', 'N/A')
    phase = design.get('phases', ['N/A'])[0] if design.get('phases') else 'N/A'
    status = status_mod.get('overallStatus', 'N/A')
    condition_list = conditions.get('conditions', [])
    
    # Get start date
    start_date_struct = status_mod.get('startDateStruct', {})
    start_date = start_date_struct.get('date', 'N/A')
    
    # Get intervention names
    intervention_list = [i.get('name', '') for i in interventions.get('interventions', [])]
    
    # Determine drug
    drug = 'Unknown'
    if any('deucravacitinib' in i.lower() or 'bms-986165' in i.lower() for i in intervention_list):
        drug = 'Deucravacitinib'
    elif any('zasocitinib' in i.lower() or 'tak-279' in i.lower() for i in intervention_list):
        drug = 'Zasocitinib'
    elif any('jnj-77242113' in i.lower() for i in intervention_list):
        drug = 'JNJ-77242113'
    
    # Score for ranking (Phase 3 > Phase 2 > Phase 1, Recruiting > Completed)
    score = 0
    if phase == 'PHASE3':
        score += 30
    elif phase == 'PHASE2':
        score += 20
    elif phase == 'PHASE1':
        score += 10
    
    if status == 'RECRUITING':
        score += 15
    elif status == 'ACTIVE_NOT_RECRUITING':
        score += 12
    elif status == 'COMPLETED':
        score += 8
    elif status == 'NOT_YET_RECRUITING':
        score += 5
    
    # Bonus for interesting indications
    if any(cond.lower() in ['psoriatic arthritis', 'ulcerative colitis', 'crohn disease', 'lupus'] 
           for cond in condition_list):
        score += 10
    
    trial_info = {
        'nct_id': nct_id,
        'title': title,
        'phase': phase,
        'status': status,
        'conditions': condition_list,
        'interventions': intervention_list,
        'drug': drug,
        'start_date': start_date,
        'score': score
    }
    
    trial_list.append(trial_info)

# Sort by score
trial_list.sort(key=lambda x: x['score'], reverse=True)

# Get top 10
top_10 = trial_list[:10]

print("TOP 10 TYK2 INHIBITOR TRIALS (Excluding already analyzed):\n")
print("=" * 80)

for i, trial in enumerate(top_10, 1):
    print(f"{i}. NCT ID: {trial['nct_id']}")
    print(f"   Drug: {trial['drug']}")
    print(f"   Title: {trial['title'][:70]}...")
    print(f"   Phase: {trial['phase']} | Status: {trial['status']}")
    print(f"   Conditions: {', '.join(trial['conditions'][:2])}")
    print(f"   Start Date: {trial['start_date']}")
    print(f"   Score: {trial['score']}")
    print()

# Save to file
with open('top_10_tyk2_trials.json', 'w') as f:
    json.dump(top_10, indent=2, fp=f)

print("=" * 80)
print(f"✓ Saved top 10 trials to top_10_tyk2_trials.json")

# Print summary by drug
print("\nBreakdown by Drug:")
from collections import Counter
drug_counts = Counter([t['drug'] for t in top_10])
for drug, count in drug_counts.items():
    print(f"  {drug}: {count} trials")

# Print summary by phase
print("\nBreakdown by Phase:")
phase_counts = Counter([t['phase'] for t in top_10])
for phase, count in phase_counts.items():
    print(f"  {phase}: {count} trials")

# Print summary by indication
print("\nKey Indications:")
all_conditions = []
for t in top_10:
    all_conditions.extend(t['conditions'])
condition_counts = Counter(all_conditions)
for condition, count in condition_counts.most_common(5):
    print(f"  {condition}: {count} trials")
