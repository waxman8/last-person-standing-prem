import requests

def trigger_sync():
    login_url = "http://localhost:8000/login"
    sync_url = "http://localhost:8000/admin/sync-fixtures"
    
    # 1. Login
    try:
        res = requests.post(login_url, data={"username": "admin", "password": "99999"})
        if res.status_code != 200:
            print(f"Login failed: {res.status_code} - {res.text}")
            return
        
        token = res.json().get("access_token")
        print(f"Logged in, token obtained")
        
        # 2. Sync
        headers = {"Authorization": f"Bearer {token}"}
        res = requests.post(sync_url, headers=headers)
        if res.status_code == 200:
            print("Sync triggered successfully")
            print(res.json())
        else:
            print(f"Sync failed: {res.status_code} - {res.text}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    trigger_sync()
