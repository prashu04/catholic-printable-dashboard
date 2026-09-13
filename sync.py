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
resp = requests.post(token_url, data=payload)
resp.raise_for_status()  # This will expose the real error if authentication fails
token_data = resp.json()
access_token = token_data['access_token']

# 2. Extract User ID directly from the token and get Shop ID
# Etsy v3 access tokens are formatted as: {user_id}.{jwt_string}
user_id = access_token.split('.')[0]

headers = {'x-api-key': api_key, 'Authorization': f'Bearer {access_token}'}

# Get your shop details using your user_id
shop_resp = requests.get(f"https://api.etsy.com/v3/application/users/{user_id}/shops", headers=headers)
shop_resp.raise_for_status()
shop_id = shop_resp.json()['shop_id']

# 3. Pull latest receipts 
receipts_resp = requests.get(f"https://api.etsy.com/v3/application/shops/{shop_id}/receipts", headers=headers)
receipts_resp.raise_for_status()
receipts = receipts_resp.json()

# 4. Save data directly to the repository
with open('data.json', 'w') as f:
    json.dump(receipts, f)
