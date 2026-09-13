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

# 3. Verified Historical Baseline (Oct 2025 – Aug 2026)
historical_months = [
    { "month": "2025-10", "orders": 0, "sales": 0, "fees": -224, "adFees": 0, "refunds": 0, "profit": -224 },
    { "month": "2025-11", "orders": 2, "sales": 64, "fees": -135, "adFees": 0, "refunds": 0, "profit": -71 },
    { "month": "2025-12", "orders": 5, "sales": 288, "fees": -281, "adFees": 0, "refunds": 0, "profit": 7 },
    { "month": "2026-01", "orders": 12, "sales": 1129, "fees": -713, "adFees": 0, "refunds": 0, "profit": 416 },
    { "month": "2026-02", "orders": 12, "sales": 1389, "fees": -836, "adFees": 0, "refunds": 0, "profit": 553 },
    { "month": "2026-03", "orders": 7, "sales": 2123, "fees": -759, "adFees": -434, "refunds": -360, "profit": 570 },
    { "month": "2026-04", "orders": 11, "sales": 5187, "fees": -1428, "adFees": 0, "refunds": -500, "profit": 3259 },
    { "month": "2026-05", "orders": 5, "sales": 1191, "fees": -462, "adFees": 0, "refunds": 0, "profit": 729 },
    { "month": "2026-06", "orders": 15, "sales": 4096, "fees": -1418, "adFees": -36, "refunds": 0, "profit": 2642 },
    { "month": "2026-07", "orders": 19, "sales": 4762, "fees": -1659, "adFees": -167, "refunds": -326, "profit": 2610 },
    { "month": "2026-08", "orders": 21, "sales": 6994, "fees": -2374, "adFees": -152, "refunds": 0, "profit": 4468 }
]

# 4. Save combined payload to data.json
payload_data = {
    "historical_months": historical_months,
    "results": live_receipts if isinstance(live_receipts, list) else []
}

with open('data.json', 'w') as f:
    json.dump(payload_data, f)

print("Successfully synced historical baseline and live receipts to data.json")
