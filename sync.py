import os, requests, json

api_key = os.environ['ETSY_API_KEY'].strip()
refresh_token = os.environ['ETSY_REFRESH_TOKEN'].strip()
shop_id = os.environ['ETSY_SHOP_ID'].strip()

print("--- DIAGNOSTIC INITIATED ---")
print(f"Targeting Shop ID: {shop_id}")

# 1. Exchange refresh token
token_url = "https://api.etsy.com/v3/public/oauth/token"
payload = {
    "grant_type": "refresh_token",
    "client_id": api_key,
    "refresh_token": refresh_token
}
resp = requests.post(token_url, data=payload)

if resp.status_code != 200:
    print("Token Generation Failed:", resp.text)
    exit(1)
    
access_token = resp.json()['access_token']
user_id = access_token.split('.')[0]
print(f"Token Authorized For User ID: {user_id}")

# 2. Pull receipts and catch the raw Etsy error
headers = {'x-api-key': api_key, 'Authorization': f'Bearer {access_token}'}
url = f"https://api.etsy.com/v3/application/shops/{shop_id}/receipts"
receipts_resp = requests.get(url, headers=headers)

if receipts_resp.status_code != 200:
    print("\n--- RAW ETSY API ERROR ---")
    print(receipts_resp.text)
    print("--------------------------\n")
    exit(1)

# 3. Save if successful
with open('data.json', 'w') as f:
    json.dump(receipts_resp.json(), f)
print("Data successfully pulled!")
