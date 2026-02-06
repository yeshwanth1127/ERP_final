"""
Simulated ERP schema and row data for demo/dashboard. No external DB or n8n.
"""
import random
from datetime import datetime, timedelta
from collections import defaultdict

# Fixed seed for reproducible data
random.seed(42)

# --- Schema (DDL-style text for query responses) ---
SCHEMA_DDL = """
-- ERP Schema (simulated)

CREATE TABLE customers (
  id INTEGER PRIMARY KEY,
  name VARCHAR(100),
  region VARCHAR(50),
  created_at DATE
);

CREATE TABLE products (
  id INTEGER PRIMARY KEY,
  name VARCHAR(100),
  category VARCHAR(50),
  unit_price DECIMAL(10,2)
);

CREATE TABLE orders (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER REFERENCES customers(id),
  order_date DATE,
  status VARCHAR(20)
);

CREATE TABLE order_items (
  id INTEGER PRIMARY KEY,
  order_id INTEGER REFERENCES orders(id),
  product_id INTEGER REFERENCES products(id),
  quantity INTEGER,
  unit_price DECIMAL(10,2),
  amount DECIMAL(12,2)
);

CREATE TABLE sales (
  id INTEGER PRIMARY KEY,
  order_id INTEGER,
  product_id INTEGER,
  amount DECIMAL(12,2),
  sale_date DATE,
  region VARCHAR(50)
);

CREATE TABLE inventory (
  id INTEGER PRIMARY KEY,
  product_id INTEGER,
  quantity INTEGER,
  warehouse VARCHAR(50),
  updated_at DATE
);
"""

TABLE_SCHEMAS = {
    'customers': 'customers(id, name, region, created_at)',
    'products': 'products(id, name, category, unit_price)',
    'orders': 'orders(id, customer_id, order_date, status)',
    'order_items': 'order_items(id, order_id, product_id, quantity, unit_price, amount)',
    'sales': 'sales(id, order_id, product_id, amount, sale_date, region)',
    'inventory': 'inventory(id, product_id, quantity, warehouse, updated_at)',
}

REGIONS = ['North', 'South', 'East', 'West', 'Central']
CATEGORIES = ['Electronics', 'Office', 'Furniture', 'Supplies', 'Services']
STATUSES = ['pending', 'shipped', 'delivered', 'cancelled']


def _gen_date(days_ago_max=365):
    d = datetime.now().date() - timedelta(days=random.randint(0, days_ago_max))
    return d.isoformat()


def _build_simulated_rows():
    """Generate deterministic simulated rows for all tables."""
    customers = []
    for i in range(1, 31):
        customers.append({
            'id': i,
            'name': f'Customer {i}',
            'region': random.choice(REGIONS),
            'created_at': _gen_date(400),
        })

    products = []
    for i in range(1, 21):
        products.append({
            'id': i,
            'name': f'Product {i}',
            'category': random.choice(CATEGORIES),
            'unit_price': round(random.uniform(10, 500), 2),
        })

    orders = []
    for i in range(1, 81):
        orders.append({
            'id': i,
            'customer_id': random.randint(1, 30),
            'order_date': _gen_date(180),
            'status': random.choice(STATUSES),
        })

    order_items = []
    idx = 1
    for o in orders:
        n_items = random.randint(1, 4)
        for _ in range(n_items):
            p = random.choice(products)
            qty = random.randint(1, 5)
            amt = round(p['unit_price'] * qty, 2)
            order_items.append({
                'id': idx,
                'order_id': o['id'],
                'product_id': p['id'],
                'quantity': qty,
                'unit_price': p['unit_price'],
                'amount': amt,
            })
            idx += 1

    sales = []
    for i, oi in enumerate(order_items[:120], 1):
        o = next((x for x in orders if x['id'] == oi['order_id']), None)
        c = next((x for x in customers if x['id'] == o['customer_id']), None) if o else None
        region = c['region'] if c else random.choice(REGIONS)
        sales.append({
            'id': i,
            'order_id': oi['order_id'],
            'product_id': oi['product_id'],
            'amount': oi['amount'],
            'sale_date': o['order_date'] if o else _gen_date(90),
            'region': region,
        })

    inventory = []
    for i, p in enumerate(products, 1):
        inventory.append({
            'id': i,
            'product_id': p['id'],
            'quantity': random.randint(0, 200),
            'warehouse': random.choice(['A', 'B', 'C']),
            'updated_at': _gen_date(30),
        })

    return {
        'customers': customers,
        'products': products,
        'orders': orders,
        'order_items': order_items,
        'sales': sales,
        'inventory': inventory,
    }


_SIMULATED_ROWS = _build_simulated_rows()


def get_schema_text():
    return SCHEMA_DDL.strip()


def get_schema_snippet(table_name):
    if table_name in TABLE_SCHEMAS:
        return f"Table: {TABLE_SCHEMAS[table_name]}"
    return get_schema_text()


def get_simulated_rows(table_name):
    return _SIMULATED_ROWS.get(table_name, [])


def query_simulated_data(sql_or_intent, seed=None):
    """
    Run a simple query over simulated data. Supports:
    - SELECT SUM(amount) FROM sales [WHERE ...]
    - SELECT COUNT(*) FROM orders [WHERE ...]
    - SELECT * FROM <table> LIMIT n
    - Intent keywords: total sales, revenue, orders count, etc.
    Returns list of dicts (rows) or single value for aggregations.
    """
    sql = (sql_or_intent or '').strip().upper()
    s = (seed or 0) % 1000
    random.seed(s)

    sales = _SIMULATED_ROWS['sales']
    orders = _SIMULATED_ROWS['orders']

    # Intent-based shortcuts
    if 'TOTAL' in sql or 'SUM' in sql or 'REVENUE' in sql or 'SALES' in sql:
        total = sum(r['amount'] for r in sales)
        variance = 1 + (s % 21 - 10) / 100  # -10% to +10%
        return [{'total': round(total * variance, 2)}]
    if 'COUNT' in sql and 'ORDER' in sql:
        n = len(orders)
        variance = (s % 7)  # 0 to 6 extra
        return [{'count': n + variance}]
    if 'REGION' in sql or 'BY REGION' in sql:
        by_region = defaultdict(float)
        for r in sales:
            by_region[r['region']] += r['amount']
        return [{'region': k, 'total': round(v * (1 + (hash(k) % 11 - 5) / 100), 2)} for k, v in sorted(by_region.items())]
    if 'CATEGORY' in sql or 'BY CATEGORY' in sql:
        products = _SIMULATED_ROWS['products']
        by_cat = defaultdict(float)
        for r in sales:
            p = next((x for x in products if x['id'] == r['product_id']), None)
            if p:
                by_cat[p['category']] += r['amount']
        return [{'category': k, 'total': round(v, 2)} for k, v in sorted(by_cat.items())]

    # Table scan with limit
    for t in _SIMULATED_ROWS:
        if t.upper() in sql:
            rows = _SIMULATED_ROWS[t][: 10 + (s % 5)]
            return rows

    # Default: total revenue with variance
    total = sum(r['amount'] for r in sales)
    return [{'total': round(total * (1 + (s % 15) / 100), 2)}]


def compute_analytics(period='month', metric='revenue', seed=None):
    """
    Compute summary and time series for dashboard.
    period: 'week' | 'month' | 'quarter'
    metric: 'revenue' | 'orders' | 'units'
    Returns { summary: { totalRevenue, totalOrders, topRegion }, series: [ { date, value }, ... ] }
    """
    s = (seed or 0) % 1000
    random.seed(s)
    sales = _SIMULATED_ROWS['sales']
    orders = _SIMULATED_ROWS['orders']

    days_back = {'week': 7, 'month': 30, 'quarter': 90}.get(period, 30)
    base = datetime.now().date()
    series = []
    by_date = defaultdict(float)
    order_count_by_date = defaultdict(int)

    for r in sales:
        try:
            d = datetime.fromisoformat(r['sale_date']).date()
            if (base - d).days <= days_back:
                by_date[d.isoformat()] += r['amount']
        except (ValueError, TypeError):
            pass
    for o in orders:
        try:
            d = datetime.fromisoformat(o['order_date']).date()
            if (base - d).days <= days_back:
                order_count_by_date[d.isoformat()] += 1
        except (ValueError, TypeError):
            pass

    for i in range(days_back, -1, -1):
        d = (base - timedelta(days=i)).isoformat()
        rev = by_date.get(d, 0) * (1 + (hash(d + period) % 11 - 5) / 100)
        ord_count = order_count_by_date.get(d, 0) + (hash(d + metric) % 3)
        if metric == 'revenue':
            series.append({'date': d, 'value': round(rev, 2)})
        elif metric == 'orders':
            series.append({'date': d, 'value': ord_count})
        else:
            series.append({'date': d, 'value': round(rev, 2)})

    total_revenue = sum(r['amount'] for r in sales) * (1 + (s % 15 - 7) / 100)
    total_orders = len(orders) + (s % 10)
    by_region = defaultdict(float)
    for r in sales:
        by_region[r['region']] += r['amount']
    top_region = max(by_region, key=by_region.get) if by_region else 'N/A'

    return {
        'summary': {
            'totalRevenue': round(total_revenue, 2),
            'totalOrders': total_orders,
            'topRegion': top_region,
        },
        'series': series[-min(30, len(series)):],  # last 30 points
    }
