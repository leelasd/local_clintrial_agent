import requests
import logging
from clintrial_agent.config import CONFIG
from clintrial_agent.data.db import fetch_trial_from_db

logger = logging.getLogger(__name__)

def fetch_trial(nct_id: str) -> dict:
    """
    Retrieve clinical trial details by NCT ID.
    First attempts to retrieve from the local PostgreSQL database.
    If not found or DB fails, falls back to fetching via the ClinicalTrials.gov API.
    """
    # 1. Attempt database fetch
    protocol = fetch_trial_from_db(nct_id)
    if protocol:
        return protocol
        
    # 2. Fall back to API
    url = f"{CONFIG['api_base_url']}/{nct_id}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        protocol = data.get('protocolSection')
        if not protocol:
            raise ValueError("API response missing 'protocolSection'")
        return protocol
    except Exception as e:
        logger.error(f"Error fetching {nct_id} from API: {e}")
        raise
