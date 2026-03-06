import requests
import os
from datetime import datetime
from typing import List, Dict

API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
BASE_URL = "https://api.football-data.org/v4"

def get_pl_fixtures() -> List[Dict]:
    """Fetch Premier League fixtures for the current season."""
    if not API_KEY:
        raise Exception("FOOTBALL_DATA_API_KEY environment variable is not set")
        
    headers = {"X-Auth-Token": API_KEY}
    url = f"{BASE_URL}/competitions/PL/matches"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            matches = response.json().get("matches", [])
            if not matches:
                raise Exception("API returned 200 OK but the 'matches' list is empty. This could mean the competition ID is wrong or no matches are scheduled.")
            return matches
        else:
            raise Exception(f"API Error {response.status_code}: {response.text}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Connection error to Football API: {str(e)}")

def get_current_gameweek_number() -> int:
    """Fetch current gameweek number from competition info."""
    if not API_KEY:
        return 1
    headers = {"X-Auth-Token": API_KEY}
    url = f"{BASE_URL}/competitions/PL"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get("currentSeason", {}).get("currentMatchday", 1)
    except:
        pass
    return 1
