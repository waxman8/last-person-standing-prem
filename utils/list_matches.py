import requests
import os
import json

API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
BASE_URL = "https://api.football-data.org/v4"

def list_team_matches(team_name):
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
                if team_name in (home or "") or team_name in (away or ""):
                    print(f"Match: {m['id']} - {home} vs {away} | Status: {m['status']} | Result: {m.get('score', {}).get('fullTime')}")
        else:
            print(f"API Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Colombia matches:")
    list_team_matches("Colombia")
    print("\nGhana matches:")
    list_team_matches("Ghana")
