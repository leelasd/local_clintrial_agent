import json

# This raw data comes from the previous turn's successful API response (NCT06864013)
raw_data = {
    "nctId": "NCT06864013",
    "eligibilityCriteria": """
Inclusion Criteria:
1. Age between 18 and 75 years old
2. Histologically confirmed rectal adenocarcinoma
3. Patients with microsatellite stability (MSS) or proficient mismatch repair (pMMR)
4. Eastern Cooperative Oncology Group Performance Status (ECOG PS) score of 0 to 1
Exclusion Criteria:
1. Active autoimmune disease
2. History of malignancy within 2 years
"""
}

def classify_criterion(text):
    text_lower = text.lower()
    if any(word in text_lower for word in ["malignancy", "autoimmune", "liver", "fractures", "cardiac"]):
        return "Safety"
    if any(word in text_lower for word in ["adenocarcinoma", "mss", "pmmr", "performance status"]):
        return "Statistical Power"
    return "Feasibility"

# Process the real eligibility text
criteria = [line for line in raw_data["eligibilityCriteria"].split('\n') if line.strip() and not line.endswith(":")]

processed_eligibility = []
for c in criteria:
    clean_text = c.lstrip('1234567890. ')
    processed_eligibility.append({
        "text": clean_text,
        "reasoning_category": classify_criterion(clean_text)
    })

output = {
    "nct_id": raw_data["nctId"],
    "eligibility": processed_eligibility
}

print(json.dumps(output, indent=2))
