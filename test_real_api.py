import requests
import json

# Using the recommended v2 API structure
base_url = "https://clinicaltrials.gov/api/v2/studies"
nct_id = "NCT02518605"

try:
    response = requests.get(f"{base_url}/{nct_id}")
    if response.status_code == 200:
        data = response.json()
        # Save a snippet to verify we have the real data
        with open("nct_real_data.json", "w") as f:
            json.dump(data, f, indent=2)
        print("Successfully fetched real trial data from ClinicalTrials.gov API.")
        print(f"Study title: {data.get('protocolSection', {}).get('identificationModule', {}).get('officialTitle', 'N/A')}")
    else:
        print(f"Failed to fetch data. Status code: {response.status_code}")
except Exception as e:
    print(f"An error occurred: {e}")
