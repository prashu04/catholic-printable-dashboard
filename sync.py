import os
import re
import csv
import io
import requests
from datetime import datetime, timezone
from supabase import create_client, Client

# ==============================================================================
# 1. CLIENT & CREDENTIAL CONFIGURATION
# ==============================================================================
api_key = os.environ.get('ETSY_API_KEY', '').strip()
shared_secret = os.environ.get('ETSY_SHARED_SECRET', '').strip()
refresh_token = os.environ.get('ETSY_REFRESH_TOKEN', '').strip()
shop_id = os.environ.get('ETSY_SHOP_ID', '').strip()

raw_supabase_url = os.environ.get('SUPABASE_URL', '').strip()
# Sanitize URL to avoid PGRST125 path errors
SUPABASE_URL = raw_supabase_url.split('/rest/v1')[0].rstrip('/')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '').strip()

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==============================================================================
# 2. HELPER FUNCTIONS FOR SANITIZATION & NORMALIZATION
# ==============================================================================
def clean_numeric(val, default=0.0):
    if val is None or val == '':
        return default
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = re.sub(r"[^0-9.-]", "", str(val))
    try:
        return float(cleaned) if cleaned else default
    except ValueError:
        return default

def find_column(fieldnames, candidates):
    for f in fieldnames:
        if not f:
            continue
        cleaned_f = f.strip().lower()
        if any(c.lower() == cleaned_f for c in candidates) or any(c.lower() in cleaned_f for c in candidates):
            return f
    return None

def calculate_fees(grandtotal):
    # Standard Etsy fee model: 6.5% trans + 5% proc + ₹25 fixed + 0.29% reg + ₹18 listing
    return round((grandtotal * 0.065) + (grandtotal * 0.05) + 25.0 + (grandtotal * 0.0029) + 18.0, 2)

def clean_title(raw_title):
    return str(raw_title or 'Digital Download').replace('—', '-').split('-')[0].split('|')[0].strip()[:100]

# Master record containers (keyed by receipt_id for deduplication)
orders_map = {}
items_list = []

# ==============================================================================
# 3. LOAD & PARSE 2025 & 2026 ORDER CSVs
# ==============================================================================
order_csv_files = ["EtsySoldOrders2025.csv", "EtsySoldOrders2026.csv"]

for file_path in order_csv_files:
    if not os.path.exists(file_path):
        print(f"Notice: File {file_path} not found in workspace, skipping.")
        continue

    print(f"Ingesting orders from {file_path}...")
    with open(file_path, 'rb') as f:
        raw_bytes = f.read()

    # Handle multi-encoding formats from Etsy exports
    text_content = None
    for enc in ['utf-8-sig', 'utf-16', 'latin-1', 'cp1252']:
        try:
            text_content = raw_bytes.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if not text_content:
        continue

    sanitized_csv = text_content.replace('\x00', '')
    lines = [line for line in sanitized_csv.splitlines() if line.strip()]
    reader = csv.DictReader(lines)
    fields = reader.fieldnames or []

    col_id = find_column(fields, ["Order ID", "Receipt ID", "order_id", "receipt_id"])
    col_date = find_column(fields, ["Sale Date", "Date", "Created", "order_timestamp"])
    col_buyer = find_column(fields, ["Buyer", "Name", "User ID", "buyer_name", "Ship Name"])
    col_total = find_column(fields, ["Order Value", "Order Total", "Net", "Adjusted Order Total", "grandtotal"])

    for row in reader:
        raw_id = row.get(col_id)
        if not raw_id:
            continue
        try:
            rid = int(float(str(raw_id).strip()))
        except ValueError:
            continue

        raw_date = row.get(col_date, '')
        dt = None
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw_date.strip(), fmt)
                if not dt.tzinfo:
                    dt = dt.replace(tzinfo=timezone.utc)
                break
            except Exception:
                pass
        if not dt:
            dt = datetime.now(timezone.utc)

        buyer = str(row.get(col_buyer, 'Etsy Buyer')).strip()
        grandtotal = round(clean_numeric(row.get(col_total, 0.0)), 2)
        est_fees = calculate_fees(grandtotal)

        orders_map[rid] = {
            "receipt_id": rid,
            "order_timestamp": dt.isoformat(),
            "buyer_name": buyer,
            "grandtotal": grandtotal,
            "estimated_fees": est_fees,
            "day_of_week": (dt.weekday() + 1) % 7,  # 0 = Sunday
            "month_index": dt.month - 1              # 0 = January
        }

# ==============================================================================
# 4. LOAD & PARSE 2025 & 2026 ORDER ITEMS CSVs
# ==============================================================================
item_csv_files = ["EtsySoldOrderItems2025.csv", "EtsySoldOrderItems2026.csv"]

for file_path in item_csv_files:
    if not os.path.exists(file_path):
        print(f"Notice: File {file_path} not found in workspace, skipping.")
        continue

    print(f"Ingesting line items from {file_path}...")
    with open(file_path, 'rb') as f:
        raw_bytes = f.read()

    text_content = None
    for enc in ['utf-8-sig', 'utf-16', 'latin-1', 'cp1252']:
        try:
            text_content = raw_bytes.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if not text_content:
        continue

    sanitized_csv = text_content.replace('\x00', '')
    lines = [line for line in sanitized_csv.splitlines() if line.strip()]
    reader = csv.DictReader(lines)
    fields = reader.fieldnames or []

    col_id = find_column(fields, ["Order ID", "Receipt ID", "order_id", "receipt_id"])
    col_title = find_column(fields, ["Item Name", "Title", "Listing Title", "item_title"])
    col_qty = find_column(fields, ["Quantity", "qty"])
    col_price = find_column(fields, ["Price", "Item Total", "item_price"])

    for row in reader:
        raw_id = row.get(col_id)
        if not raw_id:
            continue
        try:
            rid = int(float(str(raw_id).strip()))
        except ValueError:
            continue

        title = clean_title(row.get(col_title))
        qty = max(1, int(clean_numeric(row.get(col_qty, 1), default=1)))
        price = round(clean_numeric(row.get(col_price, 0.0)), 2)
        total = round(price * qty, 2)

        items_list.append({
            "receipt_id": rid,
            "item_title": title,
            "quantity": qty,
            "price": price,
            "item_total": total
        })

# ==============================================================================
# 5. PULL LIVE RECEIPTS FROM ETSY API (MERGE RECENT INFLOW)
# ==============================================================================
if api_key and refresh_token and shop_id:
    try:
        print("Fetching recent live receipts from Etsy API v3...")
        token_url = "https://api.etsy.com/v3/public/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "client_id": api_key,
            "refresh_token": refresh_token
        }
        resp = requests.post(token_url, data=payload)
        resp.raise_for_status()
        access_token = resp.json()['access_token']

        headers = {
            'x-api-key': f'{api_key}:{shared_secret}' if shared_secret else api_key,
            'Authorization': f'Bearer {access_token}'
        }
        url = f"https://api.etsy.com/v3/application/shops/{shop_id}/receipts?limit=100"
        receipts_resp = requests.get(url, headers=headers)
        receipts_resp.raise_for_status()

        live_receipts = receipts_resp.json().get('results', [])
        print(f"Fetched {len(live_receipts)} live receipts from API.")

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

            orders_map[rid] = {
                "receipt_id": rid,
                "order_timestamp": order_dt.isoformat(),
                "buyer_name": buyer,
                "grandtotal": round(grandtotal, 2),
                "estimated_fees": est_fees,
                "day_of_week": (order_dt.weekday() + 1) % 7,
                "month_index": order_dt.month - 1
            }

            for tx in receipt.get('transactions', []):
                short_title = clean_title(tx.get('title'))
                qty = tx.get('quantity') or 1
                price = 0.0
                if tx.get('price'):
                    price = (tx['price'].get('amount') or 0.0) / (tx['price'].get('divisor') or 1)

                items_list.append({
                    "receipt_id": rid,
                    "item_title": short_title,
                    "quantity": qty,
                    "price": round(price, 2),
                    "item_total": round(price * qty, 2)
                })

    except Exception as e:
        print(f"Notice: Live API receipt sync failed ({e}). Continuing with CSV records.")

# ==============================================================================
# 6. BATCH UPSERT ORDERS INTO SUPABASE
# ==============================================================================
final_orders = list(orders_map.values())
valid_receipt_ids = set(orders_map.keys())

print(f"Preparing to upsert {len(final_orders)} orders into 'orders' table...")
order_batch_size = 200
for i in range(0, len(final_orders), order_batch_size):
    batch = final_orders[i:i + order_batch_size]
    supabase.table("orders").upsert(batch, on_conflict="receipt_id").execute()

print("Orders table successfully populated.")

# ==============================================================================
# 7. BATCH INSERT ORDER ITEMS INTO SUPABASE
# ==============================================================================
# Filter order items to only include receipts present in the orders table
sanitized_items = [item for item in items_list if item["receipt_id"] in valid_receipt_ids]

# Deduplicate identical items under the same receipt
unique_items_map = {}
for it in sanitized_items:
    key = (it["receipt_id"], it["item_title"], it["quantity"], it["price"])
    unique_items_map[key] = it
final_items = list(unique_items_map.values())

print(f"Preparing to reload {len(final_items)} line items into 'order_items' table...")

# Clear existing order items for these receipts to avoid duplicated lines on re-runs
receipt_id_batches = list(valid_receipt_ids)
delete_batch_size = 500
for i in range(0, len(receipt_id_batches), delete_batch_size):
    b_ids = receipt_id_batches[i:i + delete_batch_size]
    supabase.table("order_items").delete().in_("receipt_id", b_ids).execute()

# Insert fresh item rows
item_batch_size = 200
for i in range(0, len(final_items), item_batch_size):
    batch = final_items[i:i + item_batch_size]
    supabase.table("order_items").insert(batch).execute()

print("Order items successfully reloaded into Supabase.")
print(f"Full reload complete: {len(final_orders)} orders and {len(final_items)} order items synced!")
