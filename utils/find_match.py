import requests
import os
import json

API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
BASE_URL = "https://api.football-data.org/v4"

def find_match(team1, team2):
    if not API_KEY:
        print("Error: FOOTBALL_DATA_API_KEY environment variable is not set")
        return
        
    headers = {"X-Auth-Token": API_KEY}
    url = f"{BASE_URL}/competitions/WC/matches"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            matches = response.json().get("matches", [])
            for m in matches:
                home = m.get("homeTeam", {}).get("name")
                away = m.get("awayTeam", {}).get("name")
                if (team1 in home and team2 in away) or (team2 in home and team1 in away):
                    print(f"Found Match: {m['id']} - {home} vs {away}")
                    print(json.dumps(m, indent=2))
        else:
            print(f"API Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_match("Colombia", "Ghana")
