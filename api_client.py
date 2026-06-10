import requests
import os
from datetime import datetime
from typing import List, Dict

API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
BASE_URL = "https://api.football-data.org/v4"

def get_fixtures(competition_code: str = "WC") -> List[Dict]:
    """Fetch fixtures for a specific competition."""
    if not API_KEY:
        raise Exception("FOOTBALL_DATA_API_KEY environment variable is not set")
        
    headers = {"X-Auth-Token": API_KEY}
    url = f"{BASE_URL}/competitions/{competition_code}/matches"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            matches = response.json().get("matches", [])
            if not matches and competition_code == "PL":
                 # Some competitions might genuinely have no matches scheduled yet
                 raise Exception(f"API returned 200 OK but the 'matches' list for {competition_code} is empty.")
            return matches
        else:
            raise Exception(f"API Error {response.status_code}: {response.text}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Connection error to Football API: {str(e)}")

def get_pl_fixtures() -> List[Dict]:
    return get_fixtures("PL")

def get_wc_fixtures() -> List[Dict]:
    return get_fixtures("WC")

def get_current_matchday(competition_code: str = "WC") -> int:
    """Fetch current matchday/gameweek number from competition info."""
    if not API_KEY:
        return 1
    headers = {"X-Auth-Token": API_KEY}
    url = f"{BASE_URL}/competitions/{competition_code}"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # For tournaments, currentMatchday might be null, so we check season or stages
            return data.get("currentSeason", {}).get("currentMatchday") or 1
    except:
        pass
    return 1

def get_current_gameweek_number() -> int:
    return get_current_matchday("PL")
