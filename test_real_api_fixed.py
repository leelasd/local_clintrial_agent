import requests
import json

# Correct v2 API endpoint for a specific ID
nct_id = "NCT06864013" # Using the LARC trial ID we know works
url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"

try:
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        print(f"Successfully fetched trial: {data['protocolSection']['identificationModule']['briefTitle']}")
        # Print a small part of the structure
        print("Keys found in protocolSection:", list(data['protocolSection'].keys()))
    else:
        print(f"Failed to fetch data. Status code: {response.status_code}")
except Exception as e:
    print(f"An error occurred: {e}")
