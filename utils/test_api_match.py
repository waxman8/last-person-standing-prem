import requests
import os
import json

API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
BASE_URL = "https://api.football-data.org/v4"
MATCH_ID = 537428

def inspect_match(match_id):
    if not API_KEY:
        print("Error: FOOTBALL_DATA_API_KEY environment variable is not set")
        return
        
    headers = {"X-Auth-Token": API_KEY}
    url = f"{BASE_URL}/matches/{match_id}"
    
    print(f"Fetching match {match_id} from {url}...")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print("\nMatch Data:")
            print(json.dumps(data, indent=2))
            
            score = data.get("score", {})
            winner = score.get("winner")
            duration = score.get("duration")
            full_time = score.get("fullTime", {})
            extra_time = score.get("extraTime", {})
            penalties = score.get("penalties", {})
            
            print(f"\nSummary:")
            print(f"Status: {data.get('status')}")
            print(f"Winner: {winner}")
            print(f"Duration: {duration}")
            print(f"Full Time: {full_time.get('home')} - {full_time.get('away')}")
            print(f"Extra Time: {extra_time.get('home')} - {extra_time.get('away')}")
            print(f"Penalties: {penalties.get('home')} - {penalties.get('away')}")
            
        else:
            print(f"API Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_match(MATCH_ID)
