import json

# Simulated raw text for the Eligibility of NCT06864013
eligibility_text = """
Inclusion: Age 18-75, Histologically confirmed rectal adenocarcinoma, MSS/pMMR, ECOG 0-1.
Exclusion: MSI-H/dMMR, Active autoimmune disease, History of malignancy within 2 years.
"""

# Logic for our "Reasoning" agent
def get_reasoning(text):
    text_lower = text.lower()
    if any(word in text_lower for word in ["malignancy", "autoimmune", "age"]):
        return "Safety"
    if any(word in text_lower for word in ["adenocarcinoma", "mss", "pmmr", "evaluable lesion"]):
        return "Statistical Power"
    return "Feasibility"

# Process
eligibility = [
    {"text": "Age 18-75", "reasoning_category": "Safety"},
    {"text": "Histologically confirmed rectal adenocarcinoma", "reasoning_category": "Statistical Power"},
    {"text": "MSS/pMMR", "reasoning_category": "Statistical Power"},
    {"text": "Active autoimmune disease", "reasoning_category": "Safety"},
    {"text": "History of malignancy within 2 years", "reasoning_category": "Safety"}
]

output = {
    "eligibility": eligibility,
    "trial_integrity": {
        "masking_level": "None",
        "blinding_validation_method": "None",
        "concomitant_therapy_controls": "Standardized background care"
    },
    "feasibility_assessment": {
        "recruitment_bottlenecks": "Complex MSS/pMMR and resectability requirements",
        "estimated_enrollment_rate": "Moderate"
    }
}
print(json.dumps(output, indent=2))
