import os, requests, json, csv

api_key = os.environ['ETSY_API_KEY'].strip()
shared_secret = os.environ['ETSY_SHARED_SECRET'].strip()
refresh_token = os.environ['ETSY_REFRESH_TOKEN'].strip()
shop_id = os.environ['ETSY_SHOP_ID'].strip()

# 1. Exchange refresh token for access token
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
raw_data = receipts_resp.json()
live_receipts = raw_data.get('results', raw_data)

# 3. Verified Historical Baseline Months (Oct 2025 – Aug 2026)
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

# 4. Ingest Historical Order Items CSV (if present)
historical_products = {}
historical_buyers = {}

csv_file_path = 'historical_order_items.csv'
if os.path.exists(csv_file_path):
    with open(csv_file_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            title_key = next((k for k in row if 'item name' in k.lower() or 'title' in k.lower()), None)
            qty_key = next((k for k in row if 'quantity' in k.lower()), None)
            price_key = next((k for k in row if 'item total' in k.lower() or 'price' in k.lower()), None)
            buyer_key = next((k for k in row if 'buyer' in k.lower() or 'name' in k.lower()), None)
            order_id_key = next((k for k in row if 'order id' in k.lower()), None)

            if not title_key or not row[title_key]:
                continue

            raw_title = row[title_key].strip()
            short_title = raw_title.replace('—', '-').split('-')[0].split('|')[0].strip()[:50]

            def clean_num(v):
                if not v: return 0.0
                return float(str(v).replace('₹', '').replace('$', '').replace(',', '').strip() or 0)

            qty = int(clean_num(row.get(qty_key, 1))) if qty_key else 1
            rev = clean_num(row.get(price_key, 0)) if price_key else 0.0

            if short_title not in historical_products:
                historical_products[short_title] = {"title": short_title, "qty": 0, "revenue": 0.0}
            historical_products[short_title]["qty"] += qty
            historical_products[short_title]["revenue"] += rev

            if buyer_key and row.get(buyer_key):
                buyer = row[buyer_key].strip()
                order_id = row.get(order_id_key, '').strip()
                if buyer not in historical_buyers:
                    historical_buyers[buyer] = {"id": buyer, "orders": set(), "spend": 0.0}
                if order_id:
                    historical_buyers[buyer]["orders"].add(order_id)
                historical_buyers[buyer]["spend"] += rev

    # Convert buyer order sets to integer counts for JSON serialization
    historical_buyers = {
        k: {"id": v["id"], "orders": max(1, len(v["orders"])), "spend": round(v["spend"], 2)}
        for k, v in historical_buyers.items()
    }

# 5. Output Unified Payload
payload_data = {
    "historical_months": historical_months,
    "historical_products": list(historical_products.values()),
    "historical_buyers": list(historical_buyers.values()),
    "results": live_receipts if isinstance(live_receipts, list) else []
}

with open('data.json', 'w') as f:
    json.dump(payload_data, f)

print("Unified data.json successfully updated.")
