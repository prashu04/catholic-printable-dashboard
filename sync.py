import os, requests, json

api_key = os.environ['ETSY_API_KEY']
refresh_token = os.environ['ETSY_REFRESH_TOKEN']

# 1. Exchange refresh token for a live access token
token_url = "https://api.etsy.com/v3/public/oauth/token"
payload = {
    "grant_type": "refresh_token",
    "client_id": api_key,
    "refresh_token": refresh_token
}
resp = requests.post(token_url, data=payload).json()
access_token = resp['access_token']

# 2. Retrieve Shop ID
headers = {'x-api-key': api_key, 'Authorization': f'Bearer {access_token}'}
me = requests.get("https://api.etsy.com/v3/application/users/me", headers=headers).json()
shop_id = me['shop_id']

# 3. Pull latest receipts 
receipts = requests.get(f"https://api.etsy.com/v3/application/shops/{shop_id}/receipts", headers=headers).json()

# 4. Save data directly to the repository
with open('data.json', 'w') as f:
    json.dump(receipts, f)
