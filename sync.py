import os
import requests
from datetime import datetime, timezone
from supabase import create_client, Client

# ==============================================================================
# 1. CREDENTIALS & INITIALIZATION
# ==============================================================================
api_key = os.environ.get('ETSY_API_KEY', '').strip()
shared_secret = os.environ.get('ETSY_SHARED_SECRET', '').strip()
refresh_token = os.environ.get('ETSY_REFRESH_TOKEN', '').strip()
shop_id = os.environ.get('ETSY_SHOP_ID', '').strip()

raw_supabase_url = os.environ.get('SUPABASE_URL', '').strip()
SUPABASE_URL = raw_supabase_url.split('/rest/v1')[0].rstrip('/')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '').strip()

if not all([api_key, refresh_token, shop_id, SUPABASE_URL, SUPABASE_KEY]):
    raise ValueError("Missing required Etsy or Supabase environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==============================================================================
# 2. HELPER FUNCTIONS
# ==============================================================================
def calculate_fees(grandtotal):
    # Standard fee model: 6.5% trans + 5% proc + ₹25 fixed + 0.29% reg + ₹18 listing
    return round((grandtotal * 0.065) + (grandtotal * 0.05) + 25.0 + (grandtotal * 0.0029) + 18.0, 2)

def clean_title(raw_title):
    return str(raw_title or 'Digital Download').replace('—', '-').split('-')[0].split('|')[0].strip()[:100]

# ==============================================================================
# 3. ETSY OAUTH REFRESH & FETCH LIVE RECEIPTS
# ==============================================================================
print("Exchanging OAuth refresh token...")
token_url = "https://api.etsy.com/v3/public/oauth/token"
token_payload = {
    "grant_type": "refresh_token",
    "client_id": api_key,
    "refresh_token": refresh_token
}
token_resp = requests.post(token_url, data=token_payload)
token_resp.raise_for_status()
access_token = token_resp.json()['access_token']

headers = {
    'x-api-key': f'{api_key}:{shared_secret}' if shared_secret else api_key,
    'Authorization': f'Bearer {access_token}'
}

# Fetch up to 100 recent live receipts
receipts_url = f"https://api.etsy.com/v3/application/shops/{shop_id}/receipts?limit=100"
print(f"Fetching recent receipts for shop {shop_id}...")
resp = requests.get(receipts_url, headers=headers)
resp.raise_for_status()

live_receipts = resp.json().get('results', [])
print(f"Found {len(live_receipts)} receipts from live API.")

if not live_receipts:
    print("No recent receipts found. Exiting sync cleanly.")
    exit(0)

# ==============================================================================
# 4. PROCESS ORDERS & ORDER ITEMS
# ==============================================================================
orders_to_upsert = []
items_to_insert = []
seen_receipt_ids = []

for receipt in live_receipts:
    rid = receipt.get('receipt_id')
    ts = receipt.get('created_timestamp') or receipt.get('creation_tsz')
    if not rid or not ts:
        continue

    order_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    grandtotal = 0.0
    if receipt.get('grandtotal'):
        grandtotal = (receipt['grandtotal'].get('amount') or 0.0) / (receipt['grandtotal'].get('divisor') or 1)

    est_fees = calculate_fees(grandtotal)
    buyer = str(receipt.get('name') or receipt.get('buyer_email') or 'Etsy Buyer').strip()

    orders_to_upsert.append({
        "receipt_id": rid,
        "order_timestamp": order_dt.isoformat(),
        "buyer_name": buyer,
        "grandtotal": round(grandtotal, 2),
        "estimated_fees": est_fees,
        "day_of_week": (order_dt.weekday() + 1) % 7,  # 0 = Sunday
        "month_index": order_dt.month - 1              # 0 = January
    })
    seen_receipt_ids.append(rid)

    for tx in receipt.get('transactions', []):
        short_title = clean_title(tx.get('title'))
        qty = tx.get('quantity') or 1
        price = 0.0
        if tx.get('price'):
            price = (tx['price'].get('amount') or 0.0) / (tx['price'].get('divisor') or 1)

        items_to_insert.append({
            "receipt_id": rid,
            "item_title": short_title,
            "quantity": qty,
            "price": round(price, 2),
            "item_total": round(price * qty, 2)
        })

# ==============================================================================
# 5. UPSERT INTO SUPABASE
# ==============================================================================
print(f"Upserting {len(orders_to_upsert)} orders into 'orders'...")
order_batch_size = 100
for i in range(0, len(orders_to_upsert), order_batch_size):
    batch = orders_to_upsert[i:i + order_batch_size]
    supabase.table("orders").upsert(batch, on_conflict="receipt_id").execute()

print(f"Refreshing line items for {len(seen_receipt_ids)} synced receipts...")
# Clear existing line items only for these synced receipts to prevent duplicates on rerun
delete_batch_size = 200
for i in range(0, len(seen_receipt_ids), delete_batch_size):
    b_ids = seen_receipt_ids[i:i + delete_batch_size]
    supabase.table("order_items").delete().in_("receipt_id", b_ids).execute()

# Insert fresh line items
item_batch_size = 100
for i in range(0, len(items_to_insert), item_batch_size):
    batch = items_to_insert[i:i + item_batch_size]
    supabase.table("order_items").insert(batch).execute()

print(f"Sync complete: {len(orders_to_upsert)} orders and {len(items_to_insert)} items successfully processed.")
