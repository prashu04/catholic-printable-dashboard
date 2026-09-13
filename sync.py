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

# 2. Pull latest receipts with the new keystring:secret header format
headers = {
    'x-api-key': f'{api_key}:{shared_secret}', 
    'Authorization': f'Bearer {access_token}'
}
url = f"https://api.etsy.com/v3/application/shops/{shop_id}/receipts"
receipts_resp = requests.get(url, headers=headers)
receipts_resp.raise_for_status()
receipts = receipts_resp.json()

# 3. Save data directly to the repository
with open('data.json', 'w') as f:
    json.dump(receipts, f)
