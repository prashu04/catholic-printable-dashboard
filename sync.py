import os
import requests
from datetime import datetime, timezone
from supabase import create_client, Client

# 1. Fetch credentials from environment
api_key = os.environ['ETSY_API_KEY'].strip()
shared_secret = os.environ['ETSY_SHARED_SECRET'].strip()
refresh_token = os.environ['ETSY_REFRESH_TOKEN'].strip()
shop_id = os.environ['ETSY_SHOP_ID'].strip()

supabase_url = os.environ['SUPABASE_URL'].strip()
supabase_key = os.environ['SUPABASE_SERVICE_KEY'].strip()

# Initialize Supabase client
supabase: Client = create_client(supabase_url, supabase_key)

# 2. Exchange refresh token for access token
token_url = "https://api.etsy.com/v3/public/oauth/token"
payload = {
    "grant_type": "refresh_token",
    "client_id": api_key,
    "refresh_token": refresh_token
}
resp = requests.post(token_url, data=payload)
resp.raise_for_status()
access_token = resp.json()['access_token']

# 3. Pull live receipts from Etsy API v3
headers = {
    'x-api-key': f'{api_key}:{shared_secret}',
    'Authorization': f'Bearer {access_token}'
}
url = f"https://api.etsy.com/v3/application/shops/{shop_id}/receipts"
receipts_resp = requests.get(url, headers=headers)
receipts_resp.raise_for_status()
raw_data = receipts_resp.json()
live_receipts = raw_data.get('results', raw_data)

print(f"Fetched {len(live_receipts)} receipts from Etsy API.")

# 4. Upsert Receipts and Line Items into Supabase
orders_to_upsert = []
items_to_insert = []

for receipt in live_receipts:
    receipt_id = receipt.get('receipt_id')
    ts = receipt.get('created_timestamp') or receipt.get('creation_tsz')
    if not receipt_id or not ts:
        continue

    order_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    
    # Grand total extraction
    grandtotal = 0.0
    if receipt.get('grandtotal'):
        grandtotal = (receipt['grandtotal'].get('amount') or 0.0) / (receipt['grandtotal'].get('divisor') or 1)

    # Standard Etsy fee estimation (6.5% trans + 5% + ₹25 proc + ₹18 listing + 0.29% reg)
    est_fees = (grandtotal * 0.065) + (grandtotal * 0.05) + 25.0 + (grandtotal * 0.0029) + 18.0

    buyer = str(receipt.get('name') or receipt.get('buyer_email') or 'Etsy Buyer').strip()
    
    orders_to_upsert.append({
        "receipt_id": receipt_id,
        "order_timestamp": order_dt.isoformat(),
        "buyer_name": buyer,
        "grandtotal": round(grandtotal, 2),
        "estimated_fees": round(est_fees, 2),
        "day_of_week": (order_dt.weekday() + 1) % 7,  # Sunday = 0
        "month_index": order_dt.month - 1              # Jan = 0
    })

    # Line items parsing
    transactions = receipt.get('transactions', [])
    for tx in transactions:
        title = tx.get('title') or 'Digital Download'
        short_title = title.split('—')[0].split('-')[0].split('|')[0].strip()[:50]
        qty = tx.get('quantity') or 1
        
        price = 0.0
        if tx.get('price'):
            price = (tx['price'].get('amount') or 0.0) / (tx['price'].get('divisor') or 1)
        
        items_to_insert.append({
            "receipt_id": receipt_id,
            "item_title": short_title,
            "quantity": qty,
            "price": round(price, 2),
            "item_total": round(price * qty, 2)
        })

# 5. Push data to database
if orders_to_upsert:
    supabase.table("orders").upsert(orders_to_upsert, on_conflict="receipt_id").execute()
    print(f"Successfully upserted {len(orders_to_upsert)} orders.")

if items_to_insert:
    # Clear existing line items for these receipts to avoid duplicate entries on re-syncs
    receipt_ids = [o["receipt_id"] for o in orders_to_upsert]
    supabase.table("order_items").delete().in_("receipt_id", receipt_ids).execute()
    
    supabase.table("order_items").insert(items_to_insert).execute()
    print(f"Successfully inserted {len(items_to_insert)} line items.")

print("Sync completed successfully!")
