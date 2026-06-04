"""
Meridian ELT — Postgres → Iceberg (MinIO via Nessie)

Reads each source table in full and overwrites the corresponding Iceberg table.
Run incrementally by passing --table <schema.table>.

Usage:
    python elt.py                    # full load, all tables
    python elt.py --table pos.stores # single table
"""

import argparse
import os

import pandas as pd
import psycopg2
import pyarrow as pa
from pyiceberg.catalog import load_catalog
from pyiceberg.exceptions import NamespaceAlreadyExistsError, NoSuchTableError

# ─── Config ───────────────────────────────────────────────────────────────────

PG_URL = os.getenv("DATABASE_URL", "postgresql://meridian:meridian_pass@postgres:5432/meridian")

NESSIE_URI   = os.getenv("NESSIE_URI",    "http://nessie:19120/iceberg")
MINIO_URI    = os.getenv("MINIO_URI",     "http://minio:9000")
MINIO_KEY    = os.getenv("MINIO_KEY",     "minioadmin")
MINIO_SECRET = os.getenv("MINIO_SECRET",  "minioadmin")
WAREHOUSE    = os.getenv("WAREHOUSE",     "s3://lakehouse/")

# source schema → iceberg namespace mapping
NAMESPACE_MAP = {
    "pos":        "raw_pos",
    "ecommerce":  "raw_ecommerce",
    "warehouse":  "raw_warehouse",
}

# All source tables: (pg_schema, pg_table, partition_column_or_None)
TABLES = [
    ("pos",        "stores",           None),
    ("pos",        "staff",            None),
    ("pos",        "products",         None),
    ("pos",        "pos_transactions", "occurred_at"),
    ("pos",        "pos_items",        None),
    ("pos",        "inventory",        None),
    ("ecommerce",  "customers",        None),
    ("ecommerce",  "online_orders",    "placed_at"),
    ("ecommerce",  "online_items",     None),
    ("warehouse",  "suppliers",        None),
    ("warehouse",  "purchase_orders",  "ordered_at"),
    ("warehouse",  "po_items",         None),
    ("warehouse",  "receipts",         "received_at"),
]


# ─── Catalog ──────────────────────────────────────────────────────────────────

def get_catalog():
    return load_catalog(
        "nessie",
        **{
            "type": "rest",
            "uri": NESSIE_URI,
            "warehouse": WAREHOUSE,
            "s3.endpoint": MINIO_URI,
            "s3.access-key-id": MINIO_KEY,
            "s3.secret-access-key": MINIO_SECRET,
            "s3.region": "us-east-1",
            "s3.path-style-access": "true",
        },
    )


def ensure_namespace(catalog, namespace: str):
    try:
        catalog.create_namespace(namespace)
        print(f"  Created namespace: {namespace}")
    except NamespaceAlreadyExistsError:
        pass


# ─── Load helpers ─────────────────────────────────────────────────────────────

def fetch_table(pg_schema: str, pg_table: str) -> pd.DataFrame:
    conn = psycopg2.connect(PG_URL)
    df = pd.read_sql(f'SELECT * FROM "{pg_schema}"."{pg_table}"', conn)
    conn.close()
    return df


def pg_to_arrow(df: pd.DataFrame) -> pa.Table:
    """Convert pandas DataFrame to Arrow, coercing timestamps to UTC."""
    for col in df.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns:
        df[col] = pd.to_datetime(df[col], utc=True)
    return pa.Table.from_pandas(df, preserve_index=False)


def write_table(catalog, namespace: str, table_name: str, arrow_table: pa.Table):
    full_name = f"{namespace}.{table_name}"
    schema = arrow_table.schema

    try:
        ice_table = catalog.load_table(full_name)
        # Overwrite — append snapshot
        ice_table.overwrite(arrow_table)
        print(f"  Overwrote  {full_name}  ({len(arrow_table)} rows)")
    except NoSuchTableError:
        ice_table = catalog.create_table(full_name, schema=schema)
        ice_table.append(arrow_table)
        print(f"  Created    {full_name}  ({len(arrow_table)} rows)")


# ─── Main ─────────────────────────────────────────────────────────────────────

def run(target_table: str | None = None):
    catalog = get_catalog()

    for ns in NAMESPACE_MAP.values():
        ensure_namespace(catalog, ns)

    for pg_schema, pg_table, _partition_col in TABLES:
        qualified = f"{pg_schema}.{pg_table}"
        if target_table and qualified != target_table:
            continue

        namespace = NAMESPACE_MAP[pg_schema]
        print(f"Loading {qualified} → {namespace}.{pg_table}")

        df = fetch_table(pg_schema, pg_table)
        arrow_table = pg_to_arrow(df)
        write_table(catalog, namespace, pg_table, arrow_table)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", help="Single table to load, e.g. pos.stores")
    args = parser.parse_args()
    run(target_table=args.table)


if __name__ == "__main__":
    main()
