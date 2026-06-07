import requests
import json

# Search ClinicalTrials.gov API for TYK2 inhibitor trials
search_url = "https://clinicaltrials.gov/api/v2/studies"

params = {
    "query.term": "TYK2 inhibitor OR deucravacitinib OR BMS-986165",
    "filter.overallStatus": "RECRUITING,ACTIVE_NOT_RECRUITING,COMPLETED",
    "pageSize": 50
}

print("Searching ClinicalTrials.gov for TYK2 inhibitor trials...")
print("=" * 80)

response = requests.get(search_url, params=params)
data = response.json()

trials = data.get('studies', [])
print(f"\nFound {len(trials)} TYK2 inhibitor trials\n")

# Extract key information
trial_list = []
for study in trials:
    protocol = study.get('protocolSection', {})
    ident = protocol.get('identificationModule', {})
    status_mod = protocol.get('statusModule', {})
    design = protocol.get('designModule', {})
    conditions = protocol.get('conditionsModule', {})
    interventions = protocol.get('armsInterventionsModule', {})
    
    nct_id = ident.get('nctId', 'N/A')
    title = ident.get('briefTitle', 'N/A')
    phase = design.get('phases', ['N/A'])[0] if design.get('phases') else 'N/A'
    status = status_mod.get('overallStatus', 'N/A')
    condition_list = conditions.get('conditions', [])
    
    # Get intervention names
    intervention_list = [i.get('name', '') for i in interventions.get('interventions', [])]
    
    trial_info = {
        'nct_id': nct_id,
        'title': title,
        'phase': phase,
        'status': status,
        'conditions': condition_list,
        'interventions': intervention_list
    }
    
    trial_list.append(trial_info)
    
    print(f"NCT ID: {nct_id}")
    print(f"  Title: {title[:80]}...")
    print(f"  Phase: {phase}")
    print(f"  Status: {status}")
    print(f"  Conditions: {', '.join(condition_list[:3])}")
    if intervention_list:
        print(f"  Interventions: {', '.join(intervention_list[:2])}")
    print()

# Save to file
with open('tyk2_trials.json', 'w') as f:
    json.dump(trial_list, indent=2, fp=f)

print("=" * 80)
print(f"Saved {len(trial_list)} trials to tyk2_trials.json")

# Identify key trials
print("\n" + "=" * 80)
print("KEY TRIALS TO ANALYZE:")
print("=" * 80)

# Look for deucravacitinib (approved TYK2 inhibitor - SOTYKTU)
deuc_trials = [t for t in trial_list if any('deucravacitinib' in i.lower() for i in t['interventions'])]
if deuc_trials:
    print("\n✓ APPROVED: Deucravacitinib (SOTYKTU) trials:")
    for t in deuc_trials[:3]:
        print(f"  - {t['nct_id']}: {t['title'][:60]}... [{t['phase']}]")

# Look for other TYK2 inhibitors
other_trials = [t for t in trial_list if not any('deucravacitinib' in i.lower() for i in t['interventions'])]
if other_trials:
    print("\n✓ INVESTIGATIONAL TYK2 inhibitors:")
    for t in other_trials[:3]:
        print(f"  - {t['nct_id']}: {t['title'][:60]}... [{t['phase']}]")
