"""
Meridian Clothing Co. — data generator.

Two profiles:
  --profile clean   Pristine data. No nulls, no drift, no late orders.
                    Use as a control baseline and for initial stack setup.
  --profile dirty   Deliberate quality issues baked in (default):
                      · ~3% of POS transactions have null customer_id
                      · ~1% of POS transactions are voided (total = 0)
                      · ~8% of purchase orders arrive after expected_at
                      · inventory drifts and can go slightly negative (shrinkage)

Usage:
    python generate.py --profile clean
    python generate.py --profile dirty
    python generate.py --profile clean --reset
"""

import argparse
import os
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import psycopg2
from faker import Faker

fake = Faker()

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://meridian:meridian_pass@localhost:5432/meridian",
)

# ─── Data profiles ────────────────────────────────────────────────────────────

@dataclass
class DataProfile:
    name: str
    null_customer_rate: float     # share of POS txns with no customer_id
    voided_txn_rate: float        # share of POS txns with total = 0
    late_po_rate: float           # share of POs that arrive after expected_at
    allow_negative_inventory: bool
    random_seed: int


CLEAN = DataProfile(
    name="clean",
    null_customer_rate=0.0,
    voided_txn_rate=0.0,
    late_po_rate=0.0,
    allow_negative_inventory=False,
    random_seed=42,
)

DIRTY = DataProfile(
    name="dirty",
    null_customer_rate=0.03,
    voided_txn_rate=0.01,
    late_po_rate=0.08,
    allow_negative_inventory=True,
    random_seed=42,
)

PROFILES = {"clean": CLEAN, "dirty": DIRTY}

# ─── Reference data ───────────────────────────────────────────────────────────

STORE_DATA = [
    ("Meridian Flagship – NYC", "New York",  "Northeast", date(2018, 3, 15)),
    ("Meridian – Chicago",      "Chicago",   "Midwest",   date(2019, 6, 1)),
    ("Meridian – Austin",       "Austin",    "South",     date(2020, 2, 14)),
    ("Meridian – Seattle",      "Seattle",   "West",      date(2020, 9, 22)),
    ("Meridian – Atlanta",      "Atlanta",   "South",     date(2021, 4, 5)),
]

ROLES = [
    "Store Manager", "Sales Associate", "Senior Associate",
    "Cashier", "Visual Merchandiser",
]

CATEGORIES  = ["Tops", "Bottoms", "Outerwear", "Dresses", "Accessories", "Footwear"]
COLORS      = ["Black", "White", "Navy", "Grey", "Olive", "Camel", "Rust", "Cream",
               "Forest Green", "Burgundy"]
SIZES       = ["XS", "S", "M", "L", "XL", "XXL", "28", "30", "32", "34", "36"]

SUPPLIERS = [
    ("Sunrise Textiles",       "Bangladesh", 45),
    ("Pacific Rim Apparel",    "Vietnam",    35),
    ("Atlas Garment Co.",      "Turkey",     28),
    ("Nordic Fabric House",    "Portugal",   21),
    ("Southern Cross Apparel", "Australia",  14),
]

START_DATE         = date(2024, 1, 1)
END_DATE           = date(2025, 12, 31)
NUM_PRODUCTS       = 180
NUM_CUSTOMERS      = 4000
NUM_STAFF_PER_STORE = 12


# ─── Helpers ──────────────────────────────────────────────────────────────────

def date_range(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def rand_datetime(d: date, hour_min=9, hour_max=21):
    return datetime(d.year, d.month, d.day,
                    random.randint(hour_min, hour_max),
                    random.randint(0, 59),
                    random.randint(0, 59))


def seasonal_multiplier(d: date) -> float:
    if d.month in (11, 12): return 1.6
    if d.month in (3, 4):   return 1.25
    if d.month in (1, 2):   return 0.75
    return 1.0


def connect():
    return psycopg2.connect(DB_URL)


# ─── Seed static reference tables ─────────────────────────────────────────────

def seed_stores(cur):
    ids = []
    for name, city, region, opened in STORE_DATA:
        cur.execute(
            "INSERT INTO pos.stores (name, city, region, opened_at) VALUES (%s,%s,%s,%s) RETURNING id",
            (name, city, region, opened),
        )
        ids.append(cur.fetchone()[0])
    return ids


def seed_staff(cur, store_ids):
    rows = []
    for store_id in store_ids:
        for _ in range(NUM_STAFF_PER_STORE):
            cur.execute(
                "INSERT INTO pos.staff (name, email, role, store_id) VALUES (%s,%s,%s,%s) RETURNING id",
                (fake.name(), fake.unique.email(), random.choice(ROLES), store_id),
            )
            rows.append((cur.fetchone()[0], store_id))
    return rows


def seed_products(cur):
    skus, seen = [], set()
    for _ in range(NUM_PRODUCTS):
        while True:
            sku = f"MRD-{random.randint(10000, 99999)}"
            if sku not in seen:
                seen.add(sku)
                break
        category = random.choice(CATEGORIES)
        color    = random.choice(COLORS)
        size     = random.choice(SIZES)
        cost     = round(random.uniform(8, 95), 2)
        retail   = round(cost * random.uniform(2.2, 3.5), 2)
        name     = f"{color} {category[:-1] if category.endswith('s') else category}"
        cur.execute(
            """INSERT INTO pos.products (sku, name, category, color, size, cost_price, retail_price)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (sku, name, category, color, size, cost, retail),
        )
        skus.append(sku)
    return skus


def seed_customers(cur):
    rows = []
    for _ in range(NUM_CUSTOMERS):
        joined = fake.date_time_between(start_date=START_DATE, end_date=END_DATE)
        cur.execute(
            """INSERT INTO ecommerce.customers (name, email, address, joined_at)
               VALUES (%s,%s,%s,%s) RETURNING id""",
            (fake.name(), fake.unique.email(), fake.address(), joined),
        )
        rows.append((cur.fetchone()[0], joined.date()))
    return rows


def seed_suppliers(cur):
    ids = []
    for name, country, lead_time in SUPPLIERS:
        cur.execute(
            "INSERT INTO warehouse.suppliers (name, country, lead_time_days) VALUES (%s,%s,%s) RETURNING id",
            (name, country, lead_time),
        )
        ids.append(cur.fetchone()[0])
    return ids


def seed_inventory(cur, store_ids, skus):
    for store_id in store_ids:
        for sku in skus:
            cur.execute(
                """INSERT INTO pos.inventory (store_id, sku, qty_on_hand, reorder_threshold)
                   VALUES (%s,%s,%s,%s)""",
                (store_id, sku, random.randint(30, 120), random.randint(5, 20)),
            )


# ─── Daily POS transactions ───────────────────────────────────────────────────

def generate_pos_day(cur, d: date, store_ids, staff_map, skus, inventory, profile: DataProfile):
    for store_id in store_ids:
        n_txns = max(0, int(random.gauss(35, 8) * seasonal_multiplier(d)))

        for _ in range(n_txns):
            staff_id = random.choice(staff_map[store_id])

            if profile.null_customer_rate > 0 and random.random() < profile.null_customer_rate:
                customer_id = None
            else:
                customer_id = random.randint(1, NUM_CUSTOMERS)

            tx_time = rand_datetime(d)

            if profile.allow_negative_inventory:
                available = [s for s in skus if inventory.get((store_id, s), 0) > 0] or skus
            else:
                available = [s for s in skus if inventory.get((store_id, s), 0) > 0]
                if not available:
                    continue  # clean mode: skip rather than oversell

            items = random.sample(available, min(random.randint(1, 4), len(available)))

            voided = profile.voided_txn_rate > 0 and random.random() < profile.voided_txn_rate
            total = 0.0
            item_rows = []

            for sku in items:
                cur.execute("SELECT retail_price FROM pos.products WHERE sku=%s", (sku,))
                retail = float(cur.fetchone()[0])
                qty = random.randint(1, 3)

                if profile.allow_negative_inventory:
                    discount_pct = random.choice([0, 0, 0, 0, 0.1, 0.2, 0.3])
                else:
                    discount_pct = random.choice([0, 0, 0, 0.1, 0.2])

                discount = round(discount_pct * retail * qty, 2)
                total += retail * qty - discount
                item_rows.append((sku, qty, retail, discount))

                key = (store_id, sku)
                new_qty = inventory.get(key, 0) - qty
                if not profile.allow_negative_inventory:
                    new_qty = max(0, new_qty)
                inventory[key] = new_qty

            cur.execute(
                """INSERT INTO pos.pos_transactions
                       (store_id, staff_id, customer_id, occurred_at, total)
                   VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                (store_id, staff_id, customer_id, tx_time, 0.0 if voided else round(total, 2)),
            )
            tx_id = cur.fetchone()[0]

            for sku, qty, unit_price, discount in item_rows:
                cur.execute(
                    """INSERT INTO pos.pos_items
                           (transaction_id, sku, qty, unit_price, discount)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (tx_id, sku, qty, unit_price, discount),
                )


# ─── Daily ecommerce orders ───────────────────────────────────────────────────

def generate_ecommerce_day(cur, d: date, customers, skus, profile: DataProfile):
    eligible = [(cid, jd) for cid, jd in customers if jd <= d]
    if not eligible:
        return

    n_orders = max(0, int(random.gauss(25, 6) * seasonal_multiplier(d)))

    if profile.allow_negative_inventory:
        statuses = ["delivered", "delivered", "delivered", "shipped", "processing", "cancelled"]
    else:
        # clean: no cancelled orders, status progression is always coherent
        statuses = ["delivered", "delivered", "delivered", "shipped", "processing"]

    for _ in range(n_orders):
        customer_id, _ = random.choice(eligible)
        placed_at  = rand_datetime(d)
        status     = random.choice(statuses)
        shipping   = round(random.choice([0, 0, 4.95, 9.95]), 2)

        items = random.sample(skus, min(random.randint(1, 5), len(skus)))
        total = 0.0
        item_rows = []
        for sku in items:
            qty = random.randint(1, 2)
            cur.execute("SELECT retail_price FROM pos.products WHERE sku=%s", (sku,))
            price = float(cur.fetchone()[0])
            total += price * qty
            item_rows.append((sku, qty, price))

        cur.execute(
            """INSERT INTO ecommerce.online_orders
                   (customer_id, placed_at, status, total, shipping_cost)
               VALUES (%s,%s,%s,%s,%s) RETURNING id""",
            (customer_id, placed_at, status, round(total + shipping, 2), shipping),
        )
        order_id = cur.fetchone()[0]

        for sku, qty, unit_price in item_rows:
            cur.execute(
                """INSERT INTO ecommerce.online_items (order_id, sku, qty, unit_price)
                   VALUES (%s,%s,%s,%s)""",
                (order_id, sku, qty, unit_price),
            )


# ─── Purchase orders ──────────────────────────────────────────────────────────

def generate_purchase_orders(cur, skus, supplier_ids, profile: DataProfile):
    for d in date_range(START_DATE, END_DATE):
        if d.day != 1:
            continue
        for supplier_id in supplier_ids:
            cur.execute("SELECT lead_time_days FROM warehouse.suppliers WHERE id=%s", (supplier_id,))
            lead_time = cur.fetchone()[0]

            ordered_at  = datetime(d.year, d.month, 1, 9, 0)
            expected_at = ordered_at + timedelta(days=lead_time)

            if profile.late_po_rate > 0 and random.random() < profile.late_po_rate:
                actual_arrival = expected_at + timedelta(days=random.randint(5, 25))
                status = "received_late"
            else:
                jitter = timedelta(days=random.randint(-2, 2)) if profile.allow_negative_inventory else timedelta(0)
                actual_arrival = expected_at + jitter
                status = "received"

            if actual_arrival.date() > END_DATE:
                status = "pending"
                actual_arrival = None

            cur.execute(
                """INSERT INTO warehouse.purchase_orders
                       (supplier_id, ordered_at, expected_at, status)
                   VALUES (%s,%s,%s,%s) RETURNING id""",
                (supplier_id, ordered_at, expected_at, status),
            )
            po_id = cur.fetchone()[0]

            for sku in random.sample(skus, random.randint(5, 15)):
                cur.execute("SELECT cost_price FROM pos.products WHERE sku=%s", (sku,))
                cost = float(cur.fetchone()[0])
                cur.execute(
                    """INSERT INTO warehouse.po_items (po_id, sku, qty_ordered, unit_cost)
                       VALUES (%s,%s,%s,%s)""",
                    (po_id, sku, random.randint(20, 200), cost),
                )

            if actual_arrival:
                store_id = random.choice([None, None, 1, 2, 3])
                cur.execute(
                    "INSERT INTO warehouse.receipts (po_id, received_at, store_id) VALUES (%s,%s,%s)",
                    (po_id, actual_arrival, store_id),
                )


# ─── Main ─────────────────────────────────────────────────────────────────────

def reset_schemas(cur):
    for schema in ("warehouse", "ecommerce", "pos"):
        cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        cur.execute(f"CREATE SCHEMA {schema}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        choices=["clean", "dirty"],
        default="dirty",
        help="Data quality profile (default: dirty)",
    )
    parser.add_argument("--reset", action="store_true", help="Drop and recreate schemas before seeding")
    args = parser.parse_args()

    profile = PROFILES[args.profile]
    random.seed(profile.random_seed)
    fake.seed_instance(profile.random_seed)
    fake.unique.clear()

    print(f"Profile: {profile.name}")

    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    if args.reset:
        print("Resetting schemas...")
        reset_schemas(cur)
        conn.commit()

    print("Seeding stores...")
    store_ids = seed_stores(cur)
    conn.commit()

    print("Seeding staff...")
    staff_rows = seed_staff(cur, store_ids)
    staff_map = {}
    for sid, store_id in staff_rows:
        staff_map.setdefault(store_id, []).append(sid)
    conn.commit()

    print(f"Seeding {NUM_PRODUCTS} products...")
    skus = seed_products(cur)
    conn.commit()

    print(f"Seeding {NUM_CUSTOMERS} customers...")
    customers = seed_customers(cur)
    conn.commit()

    print("Seeding suppliers...")
    supplier_ids = seed_suppliers(cur)
    conn.commit()

    print("Bootstrapping inventory...")
    seed_inventory(cur, store_ids, skus)
    conn.commit()

    cur.execute("SELECT store_id, sku, qty_on_hand FROM pos.inventory")
    inventory = {(r[0], r[1]): r[2] for r in cur.fetchall()}

    print("Generating purchase orders...")
    generate_purchase_orders(cur, skus, supplier_ids, profile)
    conn.commit()

    days = list(date_range(START_DATE, END_DATE))
    print(f"Generating daily transactions across {len(days)} days...")
    for i, d in enumerate(days):
        generate_pos_day(cur, d, store_ids, staff_map, skus, inventory, profile)
        generate_ecommerce_day(cur, d, customers, skus, profile)
        if (i + 1) % 30 == 0:
            conn.commit()
            print(f"  {d}  ({i + 1}/{len(days)})")

    conn.commit()

    print("Writing final inventory quantities...")
    for (store_id, sku), qty in inventory.items():
        cur.execute(
            "UPDATE pos.inventory SET qty_on_hand=%s, updated_at=NOW() WHERE store_id=%s AND sku=%s",
            (qty, store_id, sku),
        )
    conn.commit()

    cur.close()
    conn.close()
    print(f"Done. [{profile.name}]")


if __name__ == "__main__":
    main()
