import requests
import json

url = "https://nfl-api-data.p.rapidapi.com/nfl-team-listing/v1/data"

headers = {
    "x-rapidapi-key": "0e72ee213amshe68ca7ce87a72c6p1fc079jsna9a45b742de5",
    "x-rapidapi-host": "nfl-api-data.p.rapidapi.com"
}

try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()  # Raises an HTTPError for bad responses
    
    data = response.json()
    print(json.dumps(data, indent=2))  # Pretty print the JSON
    
except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")
except json.JSONDecodeError as e:
    print(f"Failed to decode JSON: {e}")