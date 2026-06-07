import requests
import json
import ollama
from collections import Counter

def analyze_trial(nct_id, agent_prompt, model_name):
    """
    Fetch trial data and analyze eligibility criteria using LLM
    """
    print(f"\nAnalyzing {nct_id} with {model_name}...")
    
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

Do not use escape characters. Write the JSON directly.
"""
    
    response = ollama.chat(
        model=model_name,
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
        'masking': trial_integrity['masking_level']
    }
    
    return result


# Load agent prompt
with open('agent_prompt.txt', 'r') as f:
    agent_prompt = f.read()

# Three trials to compare
trials = [
    ('NCT04167462', 'Deucravacitinib (Approved)'),
    ('NCT06220604', 'JNJ-77242113'),
    ('NCT06088043', 'Zasocitinib')
]

print("="*80)
print("MODEL COMPARISON: gemma2:2b-instruct vs gemma3:1b-it-qat")
print("="*80)

results_gemma2 = []
results_gemma3 = []

# Test with Gemma2:2b-instruct
print("\n" + "="*80)
print("TESTING WITH: gemma2:2b-instruct-q4_K_M")
print("="*80)

for nct_id, drug in trials:
    result = analyze_trial(nct_id, agent_prompt, 'gemma2:2b-instruct-q4_K_M')
    result['drug'] = drug
    results_gemma2.append(result)

# Test with Gemma3:1b-it-qat
print("\n" + "="*80)
print("TESTING WITH: gemma3:1b-it-qat")
print("="*80)

for nct_id, drug in trials:
    result = analyze_trial(nct_id, agent_prompt, 'gemma3:1b-it-qat')
    result['drug'] = drug
    results_gemma3.append(result)

# Comparison
print("\n" + "="*80)
print("SIDE-BY-SIDE COMPARISON")
print("="*80)

print(f"\n{'Trial':<30} {'Model':<25} {'Safety':<8} {'StatPwr':<8} {'Feas':<8} {'Total':<8}")
print("-" * 95)

for i, (nct_id, drug) in enumerate(trials):
    r2 = results_gemma2[i]
    r3 = results_gemma3[i]
    
    # Gemma2 results
    s2 = r2['summary'].get('Safety', 0)
    p2 = r2['summary'].get('Statistical Power', 0)
    f2 = r2['summary'].get('Feasibility', 0)
    t2 = s2 + p2 + f2
    
    # Gemma3 results
    s3 = r3['summary'].get('Safety', 0)
    p3 = r3['summary'].get('Statistical Power', 0)
    f3 = r3['summary'].get('Feasibility', 0)
    t3 = s3 + p3 + f3
    
    print(f"{drug[:28]:<30} {'gemma2:2b-instruct':<25} {s2:<8} {p2:<8} {f2:<8} {t2:<8}")
    print(f"{'':<30} {'gemma3:1b-it-qat':<25} {s3:<8} {p3:<8} {f3:<8} {t3:<8}")
    
    # Difference
    diff_s = s3 - s2
    diff_p = p3 - p2
    diff_f = f3 - f2
    diff_t = t3 - t2
    
    print(f"{'':<30} {'DIFFERENCE':<25} {diff_s:+d}        {diff_p:+d}        {diff_f:+d}        {diff_t:+d}")
    print()

# Summary
print("="*80)
print("KEY FINDINGS:")
print("="*80)

# Calculate averages
avg_gemma2 = {
    'safety': sum(r['summary'].get('Safety', 0) for r in results_gemma2) / len(results_gemma2),
    'stat': sum(r['summary'].get('Statistical Power', 0) for r in results_gemma2) / len(results_gemma2),
    'feas': sum(r['summary'].get('Feasibility', 0) for r in results_gemma2) / len(results_gemma2)
}

avg_gemma3 = {
    'safety': sum(r['summary'].get('Safety', 0) for r in results_gemma3) / len(results_gemma3),
    'stat': sum(r['summary'].get('Statistical Power', 0) for r in results_gemma3) / len(results_gemma3),
    'feas': sum(r['summary'].get('Feasibility', 0) for r in results_gemma3) / len(results_gemma3)
}

print(f"\nAverage Criteria per Trial:")
print(f"{'Model':<30} {'Safety':<10} {'Stat Power':<12} {'Feasibility':<12}")
print("-" * 65)
print(f"{'gemma2:2b-instruct':<30} {avg_gemma2['safety']:<10.1f} {avg_gemma2['stat']:<12.1f} {avg_gemma2['feas']:<12.1f}")
print(f"{'gemma3:1b-it-qat':<30} {avg_gemma3['safety']:<10.1f} {avg_gemma3['stat']:<12.1f} {avg_gemma3['feas']:<12.1f}")
print(f"{'DIFFERENCE':<30} {avg_gemma3['safety']-avg_gemma2['safety']:+.1f}       {avg_gemma3['stat']-avg_gemma2['stat']:+.1f}         {avg_gemma3['feas']-avg_gemma2['feas']:+.1f}")

# Conclusion
print("\n" + "="*80)
print("CONCLUSION:")
print("="*80)

total_diff = abs(avg_gemma3['safety']-avg_gemma2['safety']) + abs(avg_gemma3['stat']-avg_gemma2['stat']) + abs(avg_gemma3['feas']-avg_gemma2['feas'])

if total_diff < 1.0:
    print("✓ MINIMAL DIFFERENCE: Both models produce very similar results.")
    print("  Conclusions about TYK2 inhibitor competitive landscape remain VALID.")
elif total_diff < 2.0:
    print("⚠ MODERATE DIFFERENCE: Some variation in classification but overall patterns similar.")
    print("  Core conclusions likely remain valid with minor adjustments.")
else:
    print("✗ SIGNIFICANT DIFFERENCE: Models classify criteria differently.")
    print("  Conclusions should be re-evaluated based on gemma3:1b-it-qat results.")

# Save comparison
comparison_data = {
    'gemma2_results': results_gemma2,
    'gemma3_results': results_gemma3,
    'averages': {
        'gemma2': avg_gemma2,
        'gemma3': avg_gemma3
    },
    'total_difference': total_diff
}

with open('model_comparison.json', 'w') as f:
    json.dump(comparison_data, indent=2, fp=f)

print(f"\n✓ Detailed comparison saved to model_comparison.json")
