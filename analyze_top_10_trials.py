import requests
import json
import ollama
from collections import Counter
import time

def analyze_trial(nct_id, agent_prompt):
    """
    Fetch trial data and analyze eligibility criteria using LLM
    """
    try:
        print(f"\nAnalyzing {nct_id}...")
        
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
        
        # Extract eligibility criteria
        eligibility_text = protocol['eligibilityModule']['eligibilityCriteria']
        
        # Parse criteria into a list
        criteria_lines = []
        for line in eligibility_text.split('\n'):
            clean_line = line.strip().lstrip('1234567890*- ')
            if clean_line and len(clean_line) > 10 and not clean_line.endswith(':'):
                criteria_lines.append(clean_line)
        
        # Create batch prompt (first 15 criteria for speed)
        batch_prompt = f"""{agent_prompt}

Now classify ALL of the following eligibility criteria from a clinical trial.

For each criterion, determine if it is:
- **Safety**: Protects patient from harm
- **Statistical Power**: Maximizes treatment effect detection
- **Feasibility**: Operational/data quality reasons

CRITERIA LIST:
"""
        
        for i, criterion in enumerate(criteria_lines[:15], 1):
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
            eligibility = json.loads(json_text)
            print(f"  ✓ Parsed {len(eligibility)} criteria")
            
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON parse error: {e}")
            eligibility = []
        
        # Extract trial integrity
        trial_integrity = {
            "masking_level": design.get('designInfo', {}).get('maskingInfo', {}).get('masking', 'None'),
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
            'summary': dict(categories),
            'masking': trial_integrity['masking_level'],
            'total_criteria': len(criteria_lines),
            'analyzed_criteria': len(eligibility)
        }
        
        return result
        
    except Exception as e:
        print(f"  ✗ Error analyzing {nct_id}: {e}")
        return {
            'nct_id': nct_id,
            'error': str(e)
        }


# Load top 10 trials
with open('top_10_tyk2_trials.json', 'r') as f:
    top_10 = json.load(f)

# Load agent prompt
with open('agent_prompt.txt', 'r') as f:
    agent_prompt = f.read()

print("="*80)
print("ANALYZING TOP 10 TYK2 INHIBITOR TRIALS")
print("="*80)

results = []
for i, trial in enumerate(top_10, 1):
    nct_id = trial['nct_id']
    drug = trial['drug']
    
    print(f"\n[{i}/10] {nct_id} - {drug}")
    result = analyze_trial(nct_id, agent_prompt)
    result['drug'] = drug
    result['indication'] = ', '.join(trial['conditions'][:2])
    results.append(result)
    
    # Small delay to avoid overwhelming Ollama
    time.sleep(1)

# Save results
with open('top_10_analysis_results.json', 'w') as f:
    json.dump(results, indent=2, fp=f)

print("\n" + "="*80)
print("SUMMARY: TOP 10 TYK2 TRIALS")
print("="*80)

# Create summary table
print(f"\n{'NCT ID':<15} {'Drug':<20} {'Phase':<10} {'Safety':<8} {'StatPwr':<8} {'Feas':<8} {'Masking':<12}")
print("-" * 90)

for r in results:
    if 'error' not in r:
        safety = r['summary'].get('Safety', 0)
        stat = r['summary'].get('Statistical Power', 0)
        feas = r['summary'].get('Feasibility', 0)
        print(f"{r['nct_id']:<15} {r['drug']:<20} {r['phase']:<10} {safety:<8} {stat:<8} {feas:<8} {r['masking']:<12}")

# Aggregate insights
print("\n" + "="*80)
print("AGGREGATE INSIGHTS:")
print("="*80)

# By drug
drug_stats = {}
for r in results:
    if 'error' not in r:
        drug = r['drug']
        if drug not in drug_stats:
            drug_stats[drug] = {'count': 0, 'safety': 0, 'stat_power': 0, 'feasibility': 0}
        drug_stats[drug]['count'] += 1
        drug_stats[drug]['safety'] += r['summary'].get('Safety', 0)
        drug_stats[drug]['stat_power'] += r['summary'].get('Statistical Power', 0)
        drug_stats[drug]['feasibility'] += r['summary'].get('Feasibility', 0)

print("\nAverage Criteria by Drug:")
for drug, stats in drug_stats.items():
    count = stats['count']
    print(f"\n{drug} ({count} trials):")
    print(f"  Avg Safety: {stats['safety']/count:.1f}")
    print(f"  Avg Statistical Power: {stats['stat_power']/count:.1f}")
    print(f"  Avg Feasibility: {stats['feasibility']/count:.1f}")

# By masking level
print("\nTrials by Masking Level:")
masking_counts = Counter([r.get('masking', 'Unknown') for r in results if 'error' not in r])
for masking, count in masking_counts.items():
    print(f"  {masking}: {count} trials")

# By indication
print("\nTrials by Indication:")
indication_counts = Counter([r.get('indication', 'Unknown') for r in results if 'error' not in r])
for indication, count in indication_counts.most_common():
    print(f"  {indication}: {count} trials")

print("\n" + "="*80)
print("✓ Analysis complete!")
print("  - top_10_analysis_results.json")
print("="*80)
