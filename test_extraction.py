import json

# Simulated raw input (this is what the agent would get from ClinicalTrials.gov)
trial_text = """
NCT02518605: SUSTAIN-6. 
Phase 3, randomized, double-blind study. 
Inclusion: Type 2 diabetes, high cardiovascular risk. 
Exclusion: Type 1 diabetes, history of medullary thyroid carcinoma.
Endpoints: Primary is MACE (CV death, MI, stroke) at 104 weeks.
Masking: Double-blind, double-dummy.
Concomitant therapy: Standard-of-care permitted as per investigator judgment.
"""

# The agent would reason like this:
def classify_criterion(text):
    if "type 1" in text.lower() or "carcinoma" in text.lower():
        return "Safety"
    if "diabetes" in text.lower() or "high cardiovascular" in text.lower():
        return "Statistical Power"
    return "Feasibility"

eligibility = [
    {"text": "Type 2 diabetes", "reasoning_category": classify_criterion("Type 2 diabetes")},
    {"text": "High cardiovascular risk", "reasoning_category": classify_criterion("High cardiovascular risk")},
    {"text": "Type 1 diabetes", "reasoning_category": classify_criterion("Type 1 diabetes")},
    {"text": "History of medullary thyroid carcinoma", "reasoning_category": classify_criterion("History of medullary thyroid carcinoma")}
]

trial_integrity = {
    "masking_level": "Double-blind",
    "blinding_validation_method": "Not explicitly stated in summary",
    "concomitant_therapy_controls": "Standard-of-care permitted"
}

output = {"eligibility": eligibility, "trial_integrity": trial_integrity}
print(json.dumps(output, indent=2))
