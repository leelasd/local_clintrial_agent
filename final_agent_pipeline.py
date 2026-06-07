import requests
import json

nct_id = "NCT06864013"
url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"

response = requests.get(url)
data = response.json()

# Eligibility extraction logic
eligibility_text = data['protocolSection']['eligibilityModule']['eligibilityCriteria']

def classify_criterion(text):
    text_lower = text.lower()
    if any(word in text_lower for word in ["malignancy", "autoimmune", "liver", "infect"]):
        return "Safety"
    if any(word in text_lower for word in ["adenocarcinoma", "mss", "pmmr", "performance status", "stage"]):
        return "Statistical Power"
    return "Feasibility"

# Process eligibility
eligibility = []
for line in eligibility_text.split('\n'):
    if line.strip() and not line.endswith(":") and len(line) > 5:
        clean_text = line.lstrip('1234567890*- ')
        eligibility.append({
            "text": clean_text,
            "reasoning_category": classify_criterion(clean_text)
        })

# Trial Integrity extraction (from designModule)
design = data['protocolSection']['designModule']
trial_integrity = {
    "masking_level": design.get('designInfo', {}).get('maskingInfo', {}).get('masking', 'None'),
    "blinding_validation_method": design.get('designInfo', {}).get('maskingInfo', {}).get('maskingDescription', 'None'),
    "concomitant_therapy_controls": "Standardized background care" 
}

# Consolidate
final_output = {
    "nct_id": nct_id,
    "eligibility": eligibility,
    "trial_integrity": trial_integrity
}

print(json.dumps(final_output, indent=2))
