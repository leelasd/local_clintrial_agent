from pathlib import Path
import yaml
import logging

logger = logging.getLogger(__name__)

_DEFAULT_MINIMAL_CONFIG = {
    'alpha': 0.05,
    'power_target': 0.80,
    'calculation_mode': 'R-exact',
    'indication_params': {},
    'indication_aliases': {},
    'default_indication_params': {
        'control_rate_dichotomous': 0.10,
        'median_pfs_months': 6.0,
        'median_os_months': 12.0,
        'event_rate': 0.70
    },
    'llm': {'model': 'gemma4:latest', 'batch_size': 10, 'temperature': 0.1, 'num_predict': 512},
    'survival_keywords': ['survival', 'pfs', 'os', 'time to', 'hazard'],
    'dichotomous_keywords': ['rate', 'response', 'proportion', 'percentage', 'orrs', 'sri'],
    'competing_keywords': ['death', 'toxicity', 'withdrawal', 'discontinuation'],
    'endpoint_keywords': {
        'safety': ['adverse', 'safety', 'toxicity', 'tolerability'],
        'patient_reported': ['qol', 'quality of life', 'prom', 'pain'],
        'clinical': ['survival', 'response', 'remission', 'cure'],
        'biomarker': ['gene', 'expression', 'level', 'titer'],
        'surrogate': ['marker', 'clearance', 'level'],
        'composite': ['composite', 'sri-4', 'bicla', 'mda']
    },
    'survival_defaults': {'control_median_pfs_months': 6.0, 'control_median_os_months': 12.0, 'event_rate': 0.70},
    'dichotomous_power_assessment': {'adequately_powered': 0.10, 'borderline': 0.15, 'underpowered': 0.25},
    'survival_power_assessment': {'adequately_powered': 0.75, 'borderline': 0.85, 'underpowered': 0.90},
    'realistic_improvement_absolute': 0.20,
    'masking_map': {'QUADRUPLE': 'Double-blind', 'TRIPLE': 'Double-blind', 'DOUBLE': 'Double-blind', 'SINGLE': 'Single-blind', 'NONE': 'Open-label'}
}

_CONFIG_CACHE = None

def load_config(config_path=None):
    """Load configuration from pipeline_config.yaml, with graceful fallback."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and config_path is None:
        return _CONFIG_CACHE

    if config_path is None:
        possible_paths = [
            Path(__file__).parent.parent / 'pipeline_config.yaml',
            Path.cwd() / 'pipeline_config.yaml',
        ]
        for p in possible_paths:
            if p.exists():
                config_path = p
                break

    if config_path and Path(config_path).exists():
        try:
            with open(config_path, 'r') as f:
                _CONFIG_CACHE = yaml.safe_load(f)
                return _CONFIG_CACHE
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}. Using minimal fallback.")
    else:
        logger.warning(f"pipeline_config.yaml not found at {config_path}. Using minimal fallback.")

    _CONFIG_CACHE = _DEFAULT_MINIMAL_CONFIG.copy()
    return _CONFIG_CACHE

def __getattr__(name):
    """Lazy module-level attribute lookup for CONFIG, INDICATION_PARAMS, etc."""
    cfg = load_config()
    if name == 'CONFIG':
        return cfg
    elif name == 'INDICATION_PARAMS':
        return cfg.get('indication_params', {})
    elif name == 'INDICATION_ALIASES':
        return cfg.get('indication_aliases', {})
    elif name == 'DEFAULT_INDICATION_PARAMS':
        return cfg.get('default_indication_params', {})
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
