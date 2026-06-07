import requests
import json
import ollama

# Fetch trial data from ClinicalTrials.gov API
nct_id = "NCT06864013"
url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
response = requests.get(url)
data = response.json()

# Extract eligibility criteria text
eligibility_text = data['protocolSection']['eligibilityModule']['eligibilityCriteria']

# Load the agent prompt
with open('agent_prompt.txt', 'r') as f:
    agent_prompt = f.read()

# Parse criteria into a list
criteria_lines = []
for line in eligibility_text.split('\n'):
    clean_line = line.strip().lstrip('1234567890*- ')
    if clean_line and len(clean_line) > 10 and not clean_line.endswith(':'):
        criteria_lines.append(clean_line)

print(f"Processing NCT ID: {nct_id}")
print(f"Total criteria to classify: {len(criteria_lines)}")
print("=" * 80)

# Create a SINGLE prompt with ALL criteria
batch_prompt = f"""{agent_prompt}

Now classify ALL of the following eligibility criteria from a clinical trial.

For each criterion, determine if it is:
- **Safety**: Protects patient from harm
- **Statistical Power**: Maximizes treatment effect detection
- **Feasibility**: Operational/data quality reasons

CRITERIA LIST:
"""

for i, criterion in enumerate(criteria_lines[:20], 1):  # Process first 20 for speed
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

print("Sending batch request to Gemma3:1B model...")
response = ollama.chat(
    model='gemma3:1b',
    messages=[
        {
            'role': 'user',
            'content': batch_prompt
        }
    ],
    options={
        'temperature': 0.1,
        'num_predict': 4096,  # Allow longer response
    }
)

# Parse the LLM response
response_text = response['message']['content'].strip()
print("\n" + "=" * 80)
print("LLM Response:")
print(response_text[:500] + "..." if len(response_text) > 500 else response_text)
print("=" * 80)

# Try to extract JSON from response
try:
    # Look for JSON content
    if '```json' in response_text:
        start = response_text.find('```json') + 7
        end = response_text.find('```', start)
        json_text = response_text[start:end].strip()
    elif '```' in response_text:
        start = response_text.find('```') + 3
        end = response_text.find('```', start)
        json_text = response_text[start:end].strip()
    elif response_text.startswith('['):
        json_text = response_text
    else:
        # Try to find JSON array in the text
        start = response_text.find('[')
        end = response_text.rfind(']') + 1
        json_text = response_text[start:end]
    
    # Fix common LLM output issues
    json_text = json_text.replace('\\^', '^')  # Fix escape issues
    json_text = json_text.replace('\\<', '<')
    json_text = json_text.replace('\\>', '>')
        
    eligibility = json.loads(json_text)
    print(f"\n✓ Successfully parsed {len(eligibility)} classifications")
    
except json.JSONDecodeError as e:
    print(f"\n✗ Failed to parse LLM response as JSON: {e}")
    print("Raw response saved to debug.txt")
    with open('debug.txt', 'w') as f:
        f.write(response_text)
    eligibility = []

# Extract Trial Integrity from designModule
design = data['protocolSection']['designModule']
trial_integrity = {
    "masking_level": design.get('designInfo', {}).get('maskingInfo', {}).get('masking', 'None'),
    "blinding_validation_method": "Not specified",
    "concomitant_therapy_controls": "Standardized background care"
}

# Consolidate final output
final_output = {
    "nct_id": nct_id,
    "eligibility": eligibility,
    "trial_integrity": trial_integrity
}

# Save to file
output_file = f"{nct_id}_llm_analysis.json"
with open(output_file, 'w') as f:
    json.dump(final_output, indent=2, fp=f)

print(f"\n✓ Analysis saved to {output_file}")

if eligibility:
    print("\nSummary by category:")
    from collections import Counter
    # Handle both spelling variants
    categories = Counter([
        item.get('reasoning_category') or item.get('reasonging_category', 'Unknown') 
        for item in eligibility
    ])
    for category, count in categories.items():
        print(f"  {category}: {count}")
    
    print("\nSample classifications:")
    for item in eligibility[:3]:
        category = item.get('reasoning_category') or item.get('reasonging_category', 'Unknown')
        justification = item.get('justification') or item.get('justificación') or item.get('justificação', 'N/A')
        print(f"\n  • {item['text'][:60]}...")
        print(f"    Category: {category}")
        print(f"    Why: {justification}")
