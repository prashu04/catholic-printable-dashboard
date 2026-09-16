import os, requests, json, csv
from datetime import datetime

api_key = os.environ.get('ETSY_API_KEY', '').strip()
shared_secret = os.environ.get('ETSY_SHARED_SECRET', '').strip()
refresh_token = os.environ.get('ETSY_REFRESH_TOKEN', '').strip()
shop_id = os.environ.get('ETSY_SHOP_ID', '').strip()

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

# 4. Ingest Historical Order Items CSV
historical_products = {}
historical_buyers = {}
historical_heatmap = [[0 for _ in range(12)] for _ in range(7)]
historical_baskets = {}

csv_file_path = 'historical_order_items.csv'

if os.path.exists(csv_file_path):
    with open(csv_file_path, 'rb') as f:
        raw_bytes = f.read()

    text_content = None
    for enc in ['utf-8-sig', 'utf-16', 'latin-1', 'cp1252']:
        try:
            text_content = raw_bytes.decode(enc)
            break
        except Exception:
            continue

    if text_content:
        clean_text = text_content.replace('\x00', '')
        lines = [l for l in clean_text.splitlines() if l.strip()]
        reader = csv.DictReader(lines)

        for row in reader:
            if not row: continue

            title_key = next((k for k in row if k and ('item name' in k.lower() or 'title' in k.lower())), None)
            qty_key = next((k for k in row if k and 'quantity' in k.lower()), None)
            price_key = next((k for k in row if k and ('item total' in k.lower() or 'price' in k.lower())), None)
            buyer_key = next((k for k in row if k and ('buyer' in k.lower() or 'name' in k.lower())), None)
            order_id_key = next((k for k in row if k and 'order id' in k.lower()), None)
            date_key = next((k for k in row if k and ('sale date' in k.lower() or 'date' in k.lower())), None)

            if not title_key or not row.get(title_key):
                continue

            raw_title = str(row[title_key]).strip()
            short_title = raw_title.replace('—', '-').split('-')[0].split('|')[0].strip()[:50]

            def clean_num(v):
                if not v: return 0.0
                return float(str(v).replace('₹', '').replace('$', '').replace(',', '').strip() or 0)

            qty = int(clean_num(row.get(qty_key, 1))) if qty_key else 1
            rev = clean_num(row.get(price_key, 0)) if price_key else 0.0

            # Aggregate Products
            if short_title not in historical_products:
                historical_products[short_title] = {"title": short_title, "qty": 0, "revenue": 0.0}
            historical_products[short_title]["qty"] += qty
            historical_products[short_title]["revenue"] += rev

            # Track Order Baskets
            order_id = str(row.get(order_id_key, '')).strip() if order_id_key else ''
            if order_id:
                if order_id not in historical_baskets:
                    historical_baskets[order_id] = []
                historical_baskets[order_id].append(short_title)

            # Aggregate Buyers
            if buyer_key and row.get(buyer_key):
                buyer = str(row[buyer_key]).strip()
                if buyer not in historical_buyers:
                    historical_buyers[buyer] = {"id": buyer, "orders": set(), "spend": 0.0}
                if order_id:
                    historical_buyers[buyer]["orders"].add(order_id)
                historical_buyers[buyer]["spend"] += rev

            # Aggregate Date for Heatmap
            if date_key and row.get(date_key):
                try:
                    d_val = row[date_key].strip()
                    dt = None
                    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
                        try:
                            dt = datetime.strptime(d_val, fmt)
                            break
                        except ValueError:
                            pass
                    if dt:
                        d_idx = (dt.weekday() + 1) % 7 # Sun = 0
                        m_idx = dt.month - 1
                        historical_heatmap[d_idx][m_idx] += 1
                except Exception:
                    pass

    # Convert sets for JSON export
    historical_buyers = {
        k: {"id": v["id"], "orders": max(1, len(v["orders"])), "spend": round(v["spend"], 2)}
        for k, v in historical_buyers.items()
    }

# Calculate basket pairs
pair_counts = {}
for items in historical_baskets.values():
    if len(items) > 1:
        u_items = list(set(items))
        for i in range(len(u_items)):
            for j in range(i + 1, len(u_items)):
                pair = " + ".join(sorted([u_items[i], u_items[j]]))
                pair_counts[pair] = pair_counts.get(pair, 0) + 1

market_baskets = [{"pair": k, "count": v} for k, v in sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:5]]

# 5. Output Unified Payload
payload_data = {
    "historical_months": historical_months,
    "historical_products": list(historical_products.values()),
    "historical_buyers": list(historical_buyers.values()),
    "historical_heatmap": historical_heatmap,
    "historical_baskets": market_baskets,
    "results": live_receipts if isinstance(live_receipts, list) else []
}

with open('data.json', 'w') as f:
    json.dump(payload_data, f)

print("Unified data.json generated successfully.")
