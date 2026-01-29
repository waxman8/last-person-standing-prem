import requests
import os
from datetime import datetime
from typing import List, Dict

API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
BASE_URL = "https://api.football-data.org/v4"

def get_pl_fixtures() -> List[Dict]:
    """Fetch Premier League fixtures for the current season."""
    if not API_KEY:
        print("Warning: FOOTBALL_DATA_API_KEY not set")
        return []
        
    headers = {"X-Auth-Token": API_KEY}
    url = f"{BASE_URL}/competitions/PL/matches"
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("matches", [])
    else:
        print(f"Error fetching fixtures: {response.status_code} - {response.text}")
        return []

def get_current_gameweek_number() -> int:
    """Fetch current gameweek number from competition info."""
    if not API_KEY:
        return 1
    headers = {"X-Auth-Token": API_KEY}
    url = f"{BASE_URL}/competitions/PL"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("currentSeason", {}).get("currentMatchday", 1)
    return 1
