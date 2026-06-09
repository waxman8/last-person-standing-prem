import requests
import os
import json

API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
BASE_URL = "https://api.football-data.org/v4"

def get_wc_teams():
    if not API_KEY:
        print("FOOTBALL_DATA_API_KEY not set")
        return
        
    headers = {"X-Auth-Token": API_KEY}
    url = f"{BASE_URL}/competitions/WC/teams"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            teams = response.json().get("teams", [])
            mapping = {team["name"]: team["id"] for team in teams}
            # Also common variations
            for team in teams:
                name = team["name"]
                tid = team["id"]
                if name == "USA": mapping["United States"] = tid
                if name == "United States": mapping["USA"] = tid
                if name == "Korea Republic": mapping["South Korea"] = tid
                
            print(json.dumps(mapping, indent=4))
        else:
            print(f"Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    get_wc_teams()
