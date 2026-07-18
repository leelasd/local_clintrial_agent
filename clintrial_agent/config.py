from pathlib import Path
import yaml

def _load_config(config_path=None):
    if config_path is None:
        # Resolve config from the project root relative to this file
        config_path = Path(__file__).parent.parent / 'pipeline_config.yaml'
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

CONFIG = _load_config()
INDICATION_PARAMS = CONFIG['indication_params']
INDICATION_ALIASES = CONFIG.get('indication_aliases', {})
DEFAULT_INDICATION_PARAMS = CONFIG['default_indication_params']
