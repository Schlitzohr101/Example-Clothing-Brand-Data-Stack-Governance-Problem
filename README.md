# Meridian Clothing Co. — Data Stack & Governance Example

A self-contained data stack built around a fictional mid-size clothing brand. Five physical stores, an online store, and a central warehouse. Think Everlane or Madewell scale.

The project is designed as a teaching example for modern data tooling and governance: Iceberg, Nessie, Trino, dbt, and OpenMetadata all wired together in a single `docker compose up`.

---

## What's in the box

### Architecture

```
Postgres (source)
  └── pos schema        → stores, staff, products, transactions, items, inventory
  └── ecommerce schema  → customers, orders, items
  └── warehouse schema  → suppliers, purchase_orders, po_items, receipts

       ↓ Python ELT (PyIceberg)

MinIO (S3-compatible object store)
  └── s3://lakehouse/raw/...   ← Parquet files, Iceberg table format

Nessie (Iceberg REST catalog)
  └── Tracks table metadata, schema versions, snapshots

Trino (distributed SQL)
  └── Reads Iceberg tables via the Nessie catalog

dbt (dbt-trino)
  └── staging/ → marts/ (sales, products, inventory, customers)

Metabase        ← BI dashboards
OpenMetadata    ← Data catalog, lineage, governance, PII detection
```

### Services

| Container | Purpose | Port |
|---|---|---|
| `postgres` | Source database (3 schemas) | 5432 |
| `minio` | Object storage (S3-compatible) | 9000 (API), 9001 (console) |
| `nessie` | Iceberg REST catalog | 19120 |
| `trino` | Distributed SQL engine | 8080 |
| `metabase` | BI layer | 3000 |
| `openmetadata-server` | Data catalog & governance | 8585 |
| `openmetadata-ingestion` | Airflow-based ingestion | 8081 |
| `elasticsearch` | OMD search backend | 9200 |
| `mysql` | OMD metadata backend | 3306 |

### Data generator — two profiles

| Profile | Description |
|---|---|
| `clean` | Pristine data. No nulls, no voided transactions, no late POs, inventory never goes negative. Use as a control baseline. |
| `dirty` | Deliberate quality issues: ~3% of POS transactions missing `customer_id`, ~1% voided (total = $0), ~8% of purchase orders arrive after `expected_at`, inventory drifts and can go slightly negative. |

Both profiles cover 2 years of daily data: **2024-01-01 → 2025-12-31**.

### Source tables

```
pos.stores              pos.staff (PII)         pos.products
pos.pos_transactions    pos.pos_items           pos.inventory

ecommerce.customers (PII)   ecommerce.online_orders   ecommerce.online_items

warehouse.suppliers   warehouse.purchase_orders   warehouse.po_items   warehouse.receipts
```

### Iceberg lake layout

```
s3://lakehouse/
  raw/
    pos.stores/           pos.staff/            pos.products/
    pos.transactions/     pos.items/            pos.inventory/
    ecommerce.customers/  ecommerce.orders/     ecommerce.items/
    warehouse.suppliers/  warehouse.purchase_orders/
    warehouse.po_items/   warehouse.receipts/
```

### dbt models

```
models/
├── staging/
│   ├── pos/          stg_stores, stg_products, stg_transactions, stg_inventory
│   ├── ecommerce/    stg_customers, stg_orders
│   └── warehouse/    stg_purchase_orders
└── marts/
    ├── sales/        daily_sales_by_store, omnichannel_revenue
    ├── products/     product_performance
    ├── inventory/    inventory_health
    └── customers/    customer_ltv
```

---

## Quick-start (Mac — Apple Silicon M1/M2/M3/M4)

### 1. Prerequisites

Install [Docker Desktop for Mac (Apple Silicon)](https://www.docker.com/products/docker-desktop/).

Before starting, bump the resource limits — the full stack is memory-heavy:

- Docker Desktop → Settings → Resources
- **Memory: 12 GB** (8 GB minimum; less and Elasticsearch + OMD will thrash)
- **CPUs: 6+**
- Click **Apply & Restart**

That's the only prerequisite. Everything runs in containers.

### 2. Clone and configure

```bash
git clone <repo-url> meridian
cd meridian
cp .env.example .env
```

### 3. Start core services first

Bring up the data pipeline layer before the heavier BI/catalog services. This lets you validate the pipeline works before committing memory to OMD.

```bash
docker compose up -d postgres minio minio-init nessie trino
```

Wait for everything to be healthy (about 30–60 seconds):

```bash
docker compose ps
```

All four should show `healthy`. Nessie takes the longest — watch it if needed:

```bash
docker compose logs -f nessie
# Ready when you see: Listening on: http://0.0.0.0:19120
```

### 4. Seed the database

Pick your profile:

```bash
make generate-clean   # pristine data, good for initial setup and validation
# or
make generate-dirty   # data quality issues baked in
```

This takes about 2 minutes. You'll see day-by-day progress logged.

### 5. Load to Iceberg

```bash
make elt
```

This reads all 13 Postgres tables and writes them as Iceberg tables in MinIO, registered in Nessie. Takes 3–5 minutes on first run.

### 6. Validate in Trino

```bash
docker compose exec trino trino --catalog lakehouse
```

```sql
SHOW SCHEMAS;
-- raw_pos   raw_ecommerce   raw_warehouse

SELECT count(*) FROM raw_pos.pos_transactions;
-- ~90,000 rows for clean profile

SELECT count(*) FROM raw_ecommerce.online_orders;
-- ~18,000 rows
```

Type `quit` to exit.

### 7. Bring up Metabase

```bash
docker compose up -d metabase
```

Open [http://localhost:3000](http://localhost:3000) and complete the setup wizard. When asked to connect a database, point it at Trino (host: `trino`, port: `8080`).

### 8. Bring up OpenMetadata

```bash
docker compose up -d elasticsearch mysql openmetadata-server openmetadata-ingestion
```

OMD takes 2–3 minutes to initialise its schema. Watch for readiness:

```bash
docker compose logs -f openmetadata-server
# Ready when you see: Started ServerConnector
```

Open [http://localhost:8585](http://localhost:8585) — login: `admin / admin`.

### Known M4 gotcha

If any container shows `exec format error` in logs, that image doesn't publish an `arm64` build. Add `platform: linux/amd64` to that service in `docker-compose.yml` — Rosetta 2 handles it transparently, just slower startup. Most likely candidate: `openmetadata-ingestion`.

---

## Quick-start (Linux / Unraid)

### Prerequisites

```bash
# Docker Engine
curl -fsSL https://get.docker.com | sh

# Docker Compose plugin (skip if already installed)
sudo apt-get install docker-compose-plugin   # Debian/Ubuntu
# or: sudo yum install docker-compose-plugin  # RHEL/CentOS
```

Verify:

```bash
docker compose version   # should be v2.x
```

### Unraid-specific setup

Unraid runs Docker natively. You can either:

**Option A — Unraid terminal (simplest)**

SSH into your Unraid machine and follow the Linux steps below directly.

**Option B — User scripts plugin**

Install the **User Scripts** plugin from Community Applications, then paste the startup sequence into a script and trigger it from the Unraid UI.

**Recommended share setup:**

Create an Unraid share for project data, e.g. `/mnt/user/appdata/meridian/`, and clone the repo there so Docker volume mounts survive array restarts.

```bash
cd /mnt/user/appdata/meridian
git clone <repo-url> .
```

### Resource requirements

| Component | RAM |
|---|---|
| Core stack (postgres + minio + nessie + trino) | ~3 GB |
| Add Metabase | +1 GB |
| Add OMD (elasticsearch + mysql + server + ingestion) | +5 GB |
| **Total (full stack)** | **~9–10 GB** |

### Start the stack

Same commands as Mac — Docker Compose is cross-platform:

```bash
cp .env.example .env

# Core pipeline
docker compose up -d postgres minio minio-init nessie trino

# Seed and load
make generate-clean
make elt

# BI and catalog
docker compose up -d metabase
docker compose up -d elasticsearch mysql openmetadata-server openmetadata-ingestion
```

**Firewall note:** if you're accessing the UIs from another machine on your LAN, make sure the ports in the [port map](#port-map) are accessible. On Unraid the firewall is typically open by default.

---

## Quick-start (Windows — WSL 2)

### Prerequisites

1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) with the **WSL 2 backend** enabled.
2. Open Docker Desktop → Settings → Resources → WSL Integration and enable it for your distro.
3. Set resource limits in Docker Desktop → Settings → Resources:
   - **Memory: 12 GB**
   - **CPUs: 6+**
4. Open your WSL 2 terminal (Ubuntu recommended) and clone the repo there — **do not clone into `/mnt/c/...`**, file I/O through the Windows filesystem mount is very slow.

```bash
# In WSL 2
cd ~
git clone <repo-url> meridian
cd meridian
```

Then follow the same steps as Mac/Linux. All `make` and `docker compose` commands work identically inside WSL 2.

**Note:** `make` may not be installed by default. Install it with:

```bash
sudo apt-get install make
```

---

## Switching between clean and dirty data

You can swap profiles at any time. The generator always resets before seeding, so there's no bleed between runs.

```bash
# Switch to dirty data
make generate-dirty
make elt

# Switch back to clean
make generate-clean
make elt
```

The ELT overwrites the Iceberg tables on each run, so Trino and anything downstream always reflects the current Postgres state.

---

## Makefile reference

| Command | What it does |
|---|---|
| `make up` | Start all services |
| `make down` | Stop all services |
| `make logs` | Tail all container logs |
| `make ps` | Show container status |
| `make generate-clean` | Seed Postgres with clean data (resets first) |
| `make generate-dirty` | Seed Postgres with dirty data (resets first) |
| `make elt` | Load Postgres → Iceberg (MinIO + Nessie) |
| `make seed-clean` | `generate-clean` + `elt` in one shot |
| `make seed-dirty` | `generate-dirty` + `elt` in one shot |

---

## Port map

| Service | URL | Default credentials |
|---|---|---|
| Postgres | `localhost:5432` | `meridian / meridian_pass` |
| MinIO Console | [http://localhost:9001](http://localhost:9001) | `minioadmin / minioadmin` |
| MinIO API | `localhost:9000` | — |
| Nessie | [http://localhost:19120](http://localhost:19120) | — |
| Trino UI | [http://localhost:8080](http://localhost:8080) | user: `admin` (no password) |
| Metabase | [http://localhost:3000](http://localhost:3000) | first-run wizard |
| OpenMetadata | [http://localhost:8585](http://localhost:8585) | `admin / admin` |
| OMD Ingestion | [http://localhost:8081](http://localhost:8081) | `admin / admin` |

---

## Troubleshooting

**Container won't start / keeps restarting**

```bash
docker compose logs <service-name>
```

Common causes:
- Not enough memory — check Docker Desktop resource limits
- Port already in use — check with `lsof -i :<port>` (Mac/Linux) or `netstat -ano | findstr <port>` (Windows)

**Nessie healthcheck failing**

Nessie can take up to 60 seconds on first boot. Wait and retry:

```bash
docker compose logs nessie
```

**ELT fails with connection error**

Make sure all upstream services are healthy before running ELT:

```bash
docker compose ps
# postgres, minio, nessie should all show "healthy"
```

**Trino returns no tables after ELT**

The Nessie catalog registration can occasionally need a refresh. Restart Trino:

```bash
docker compose restart trino
```

**OpenMetadata stuck on initialisation**

OMD runs database migrations on first start. Give it 3–5 minutes. If it's still not up:

```bash
docker compose logs openmetadata-server | grep -i error
```

The most common cause is MySQL not being fully ready when OMD starts. Restart OMD:

```bash
docker compose restart openmetadata-server
```

**exec format error on M1/M2/M3/M4**

Add `platform: linux/amd64` to the affected service in `docker-compose.yml`:

```yaml
openmetadata-ingestion:
  platform: linux/amd64
  image: openmetadata/ingestion:1.5.4
  ...
```

---

## Project layout

```
.
├── docker-compose.yml        # All 9 services + generator/elt job profiles
├── Makefile                  # Convenience commands
├── .env.example              # Copy to .env before starting
│
├── postgres/
│   └── init.sql              # Schema definitions for all 3 source schemas
│
├── generator/
│   ├── generate.py           # Synthetic data generator (clean + dirty profiles)
│   ├── requirements.txt
│   └── Dockerfile
│
├── elt/
│   ├── elt.py                # Postgres → Iceberg ELT via PyIceberg
│   ├── requirements.txt
│   └── Dockerfile
│
├── trino/
│   ├── config.properties
│   ├── jvm.config
│   └── catalog/
│       ├── lakehouse.properties   # Iceberg via Nessie + MinIO
│       └── tpch.properties        # Built-in sample data
│
└── dbt/
    └── models/
        ├── staging/          # Light cleaning, one model per source table
        └── marts/            # sales, products, inventory, customers
```
