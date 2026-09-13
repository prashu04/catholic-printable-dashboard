import os, requests, json

api_key = os.environ['ETSY_API_KEY'].strip()
shared_secret = os.environ['ETSY_SHARED_SECRET'].strip()
refresh_token = os.environ['ETSY_REFRESH_TOKEN'].strip()
shop_id = os.environ['ETSY_SHOP_ID'].strip()

# 1. Exchange refresh token for a live access token
token_url = "https://api.etsy.com/v3/public/oauth/token"
payload = {
    "grant_type": "refresh_token",
    "client_id": api_key,
    "refresh_token": refresh_token
}
resp = requests.post(token_url, data=payload)
resp.raise_for_status() 
access_token = resp.json()['access_token']

# 2. Pull live receipts from Etsy API v3
headers = {
    'x-api-key': f'{api_key}:{shared_secret}', 
    'Authorization': f'Bearer {access_token}'
}
url = f"https://api.etsy.com/v3/application/shops/{shop_id}/receipts"
receipts_resp = requests.get(url, headers=headers)
receipts_resp.raise_for_status()
live_receipts = receipts_resp.json().get('results', receipts_resp.json())

# 3. Define Historical Baseline Receipts (Oct 2025 – Aug 2026)
# These UNIX timestamps and receipt structures seed your established timeline.
historical_baseline = [
    # Example historical baseline entry mapping (or add your structured ledger receipts here)
]

# Combine historical baseline with live API receipts
combined_receipts = historical_baseline + (live_receipts if isinstance(live_receipts, list) else [])

# 4. Save combined dataset to data.json
with open('data.json', 'w') as f:
    json.dump({"results": combined_receipts}, f)

print(f"Successfully synced {len(combined_receipts)} total records to data.json")
