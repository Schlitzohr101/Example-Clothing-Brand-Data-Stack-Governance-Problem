---
name: arch_elt_timestamp_us
description: ELT must downcast pandas nanosecond timestamps to microseconds before writing to Iceberg
metadata:
  type: project
---

The ELT pipeline (`elt/elt.py`) reads Postgres via pandas and writes Iceberg via pyiceberg. pandas/Arrow produce nanosecond (`ns`) timestamps, but Iceberg only supports microsecond (`us`) precision. pyiceberg 0.7.1 raises `TypeError: Iceberg does not yet support 'ns' timestamp precision` on table create for any table with a timestamp column (first hit: `pos.pos_transactions` with `occurred_at`).

**Why:** Iceberg's type system caps timestamp precision at microseconds; pyiceberg refuses to silently truncate unless told to.

**How to apply:** `pg_to_arrow` in `elt/elt.py` explicitly casts every `ns` timestamp Arrow column to `pa.timestamp("us", tz=...)` (preserving tz) before write. Preferred over the per-write `downcast-ns-timestamp-to-us-on-write` flag because it is explicit and version-robust. If timestamp errors reappear, check this cast still runs. Timestamp partition cols in TABLES: pos_transactions (occurred_at), online_orders (placed_at), purchase_orders (ordered_at), receipts (received_at).
