import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Any
from clintrial_agent.eligibility.constraints import Constraint

logger = logging.getLogger(__name__)

def generate_synthetic_cohort(size: int = 10000, seed: int = 42) -> pd.DataFrame:
    """
    Generate a synthetic patient clinical cohort of size N with realistic
    physiological and demographic distributions.
    """
    np.random.seed(seed)
    
    # 1. Age: normally distributed (bound [18, 90])
    age = np.random.normal(loc=55.0, scale=12.0, size=size)
    age = np.clip(age, 18.0, 90.0)
    
    # 2. ECOG: categorical [0, 1, 2, 3, 4] representing oncology/fitness distribution
    ecog_choices = [0, 1, 2, 3, 4]
    ecog_probs = [0.40, 0.45, 0.12, 0.02, 0.01]
    ecog = np.random.choice(ecog_choices, p=ecog_probs, size=size)
    
    # 3. Hemoglobin (hb): normally distributed (bound [6, 18])
    hb = np.random.normal(loc=11.5, scale=1.5, size=size)
    hb = np.clip(hb, 6.0, 18.0)
    
    # 4. Platelets: normally distributed (bound [20000, 800000])
    platelets = np.random.normal(loc=250000.0, scale=75000.0, size=size)
    platelets = np.clip(platelets, 20000.0, 800000.0)
    
    # 5. ANC (neutrophils): normally distributed (bound [500, 12000])
    anc = np.random.normal(loc=3500.0, scale=1200.0, size=size)
    anc = np.clip(anc, 500.0, 12000.0)
    
    # 6. Bilirubin (xULN ratio): lognormally distributed (median ~ 0.8 x ULN)
    bilirubin = np.random.lognormal(mean=np.log(0.8), sigma=0.3, size=size)
    
    # 7. Transaminases (AST/ALT xULN ratio): lognormally distributed (median ~ 0.6 x ULN)
    transaminases = np.random.lognormal(mean=np.log(0.6), sigma=0.4, size=size)
    
    df = pd.DataFrame({
        'age': age,
        'ecog': ecog,
        'hb': hb,
        'platelets': platelets,
        'anc': anc,
        'bilirubin': bilirubin,
        'transaminases': transaminases
    })
    return df

def evaluate_patient_pass(df: pd.DataFrame, constraints: List[Constraint]) -> pd.Series:
    """Return a boolean Series indicating which patients pass all constraints."""
    passed = pd.Series(True, index=df.index)
    
    # Map constraint variables to dataframe columns
    var_map = {
        'age_min': 'age',
        'age_max': 'age',
        'ecog_max': 'ecog',
        'hb_min': 'hb',
        'platelets_min': 'platelets',
        'anc_min': 'anc',
        'bilirubin_max': 'bilirubin',
        'transaminase_max': 'transaminases'
    }
    
    for c in constraints:
        col = var_map.get(c.variable)
        if not col or col not in df.columns:
            continue
            
        if c.operator == 'ge':
            passed &= (df[col] >= c.value)
        elif c.operator == 'le':
            passed &= (df[col] <= c.value)
            
    return passed

def simulate_relaxation(df: pd.DataFrame, constraints: List[Constraint]) -> Dict[str, Any]:
    """
    Simulate relaxation of constraints individually and return baseline yield
    and new yield multipliers.
    """
    if not constraints:
        return {
            'baseline_yield': 1.0,
            'relaxations': []
        }

    baseline_pass = evaluate_patient_pass(df, constraints)
    baseline_yield = float(baseline_pass.sum() / len(df))
    
    relaxation_results = []
    
    # Define relaxation rules
    for i, c in enumerate(constraints):
        relaxed_constraints = constraints.copy()
        
        # Determine relaxed value
        relaxed_value = c.value
        description = ""
        
        if c.variable == 'age_min':
            relaxed_value = max(12.0, c.value - 5.0)
            description = f"Decrease minimum age from {c.value:.0f} to {relaxed_value:.0f} years"
        elif c.variable == 'age_max':
            relaxed_value = min(100.0, c.value + 5.0)
            description = f"Increase maximum age from {c.value:.0f} to {relaxed_value:.0f} years"
        elif c.variable == 'ecog_max':
            relaxed_value = min(4.0, c.value + 1.0)
            description = f"Increase ECOG ceiling from {c.value:.0f} to {relaxed_value:.0f}"
        elif c.variable == 'hb_min':
            relaxed_value = max(8.0, c.value - 1.0)
            description = f"Lower Hb minimum from {c.value:.1f} to {relaxed_value:.1f} g/dL"
        elif c.variable == 'platelets_min':
            relaxed_value = max(50000.0, c.value - 25000.0)
            description = f"Lower Platelets minimum from {c.value:,.0f} to {relaxed_value:,.0f}/mm3"
        elif c.variable == 'anc_min':
            relaxed_value = max(500.0, c.value - 500.0)
            description = f"Lower ANC minimum from {c.value:,.0f} to {relaxed_value:,.0f}/mm3"
        elif c.variable == 'bilirubin_max':
            relaxed_value = c.value + 0.5
            description = f"Raise total Bilirubin maximum from {c.value:.1f} to {relaxed_value:.1f} x ULN"
        elif c.variable == 'transaminase_max':
            relaxed_value = c.value + 1.0
            description = f"Raise transaminase (AST/ALT) maximum from {c.value:.1f} to {relaxed_value:.1f} x ULN"
            
        relaxed_constraints[i] = Constraint(
            variable=c.variable,
            operator=c.operator,
            value=relaxed_value,
            unit=c.unit,
            raw_text=c.raw_text
        )
        
        # Evaluate with relaxed constraint
        relaxed_pass = evaluate_patient_pass(df, relaxed_constraints)
        relaxed_yield = float(relaxed_pass.sum() / len(df))
        
        # Calculate yield multiplier
        multiplier = relaxed_yield / baseline_yield if baseline_yield > 0.0 else 1.0
        
        relaxation_results.append({
            'variable': c.variable,
            'original_value': c.value,
            'relaxed_value': relaxed_value,
            'description': description,
            'new_yield': round(relaxed_yield, 3),
            'multiplier': round(multiplier, 3),
            'raw_text': c.raw_text
        })
        
    return {
        'baseline_yield': round(baseline_yield, 3),
        'relaxations': relaxation_results
    }
