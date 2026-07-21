import re
from typing import List, Literal, Optional
from pydantic import BaseModel

class Constraint(BaseModel):
    variable: Literal['age_min', 'age_max', 'ecog_max', 'hb_min', 'platelets_min', 'anc_min', 'bilirubin_max', 'transaminase_max']
    operator: Literal['ge', 'le']
    value: float
    unit: Optional[str] = None
    raw_text: str

def parse_constraints(text: str) -> List[Constraint]:
    """
    Parse numerical criteria boundaries from free-text eligibility protocols.
    Returns a list of structured Constraint Pydantic models with standardized units.
    """
    constraints = []
    lines = text.split('\n')
    
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        line_lower = line_clean.lower()
        
        # 1. Parse Age range / limits
        range_match = re.search(r'(?:age|aged)\s*(?:between|of)?\s*(\d+)\s*(?:to|and|-)\s*(\d+)\s*(?:years|yrs|yo)', line_lower)
        if range_match:
            val_min = float(range_match.group(1))
            val_max = float(range_match.group(2))
            constraints.append(Constraint(variable='age_min', operator='ge', value=val_min, unit='years', raw_text=line_clean))
            constraints.append(Constraint(variable='age_max', operator='le', value=val_max, unit='years', raw_text=line_clean))
            continue
            
        min_age_match = re.search(r'(?:age|aged)\s*(?:>=|≥|is\s*at\s*least|of\s*at\s*least)\s*(\d+)', line_lower)
        if not min_age_match:
            min_age_match = re.search(r'(\d+)\s*(?:years|yrs|yo)\s*(?:or\s*older|and\s*older|of\s*age|\+)', line_lower)
        if min_age_match:
            val = float(min_age_match.group(1))
            constraints.append(Constraint(variable='age_min', operator='ge', value=val, unit='years', raw_text=line_clean))
                
        max_age_match = re.search(r'(?:age|aged)\s*(?:<=|≤|is\s*at\s*most|of\s*at\s*most|up\s*to|<)\s*(\d+)', line_lower)
        if not max_age_match:
            max_age_match = re.search(r'maximum\s*age\s*(?:of)?\s*(\d+)', line_lower)
        if max_age_match:
            val = float(max_age_match.group(1))
            if val > 0:
                constraints.append(Constraint(variable='age_max', operator='le', value=val, unit='years', raw_text=line_clean))

        # 2. ECOG Performance Status
        ecog_match = re.search(r'ecog\s*(?:performance\s*status)?\s*(?:of)?\s*([0-4])\s*(?:or|-|to)\s*([0-4])', line_lower)
        if not ecog_match:
            ecog_match = re.search(r'ecog\s*(?:performance\s*status)?\s*(?:<=|≤|=)?\s*([0-4])', line_lower)
        if ecog_match:
            val = float(ecog_match.groups()[-1])
            constraints.append(Constraint(variable='ecog_max', operator='le', value=val, raw_text=line_clean))

        # 3. Hemoglobin (Hb) — Explicit unit matching (g/dL vs g/L)
        hb_match = re.search(r'(?:hemoglobin|hb)\s*(?:>=|≥)\s*(\d+(?:\.\d+)?)\s*(g/dl|g/l|g/dl)?', line_lower)
        if hb_match:
            val = float(hb_match.group(1))
            unit_str = (hb_match.group(2) or '').strip()
            
            # Explicit unit conversion based on matched unit string
            if unit_str == 'g/l' or (not unit_str and val > 40):
                val = val / 10.0  # Convert g/L to g/dL
            
            constraints.append(Constraint(variable='hb_min', operator='ge', value=round(val, 2), unit='g/dL', raw_text=line_clean))

        # 4. Platelets — Explicit unit matching (10^9/L vs /mm3 vs /uL)
        plt_match = re.search(r'(?:platelets|plt|platelet\s*count)\s*(?:>=|≥)\s*(\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?)\s*(x?\s*10\^?9/l|x?\s*10\^9|/mm3|/ul|/ul)?', line_lower)
        if plt_match:
            val_str = plt_match.group(1).replace(',', '')
            val = float(val_str)
            unit_str = (plt_match.group(2) or '').strip()
            
            # Standardize unit to /mm3 (where 100 x10^9/L = 100,000 /mm3)
            if '10^9' in unit_str or 'g/l' in unit_str or val < 1000:
                val = val * 1000.0
                
            constraints.append(Constraint(variable='platelets_min', operator='ge', value=round(val), unit='/mm3', raw_text=line_clean))

        # 5. Neutrophils (ANC)
        anc_match = re.search(r'(?:neutrophils|anc|absolute\s*neutrophil\s*count)\s*(?:>=|≥)\s*(\d+(?:\.\d+)?(?:,\d{3})*)\s*(x?\s*10\^?9/l|x?\s*10\^9|/mm3|/ul|/ul)?', line_lower)
        if anc_match:
            val_str = anc_match.group(1).replace(',', '')
            val = float(val_str)
            unit_str = (anc_match.group(2) or '').strip()
            
            if '10^9' in unit_str or val < 50:
                val = val * 1000.0
                
            constraints.append(Constraint(variable='anc_min', operator='ge', value=round(val), unit='/mm3', raw_text=line_clean))

        # 6. Bilirubin
        bili_match = re.search(r'(?:bilirubin|total\s*bilirubin)\s*(?:<=|≤)\s*(\d+(?:\.\d+)?)\s*(x?\s*uln|times\s*uln|mg/dl)?', line_lower)
        if bili_match:
            val = float(bili_match.group(1))
            unit_str = (bili_match.group(2) or '').strip()
            unit = 'mg/dL' if 'mg' in unit_str else 'xULN'
            constraints.append(Constraint(variable='bilirubin_max', operator='le', value=val, unit=unit, raw_text=line_clean))

        # 7. AST / ALT (Transaminases)
        ast_match = re.search(r'(?:ast|alt|transaminases|sgot|sgpt)\s*(?:<=|≤)\s*(\d+(?:\.\d+)?)\s*(x?\s*uln|times\s*uln|u/l)?', line_lower)
        if ast_match:
            val = float(ast_match.group(1))
            unit_str = (ast_match.group(2) or '').strip()
            unit = 'U/L' if 'u/l' in unit_str else 'xULN'
            constraints.append(Constraint(variable='transaminase_max', operator='le', value=val, unit=unit, raw_text=line_clean))

    return constraints
