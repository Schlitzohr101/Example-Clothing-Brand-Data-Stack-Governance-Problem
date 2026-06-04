-- Create additional databases
CREATE DATABASE metabase;
CREATE DATABASE airflow;

-- Schemas for Meridian source data
\c meridian;

CREATE SCHEMA IF NOT EXISTS pos;
CREATE SCHEMA IF NOT EXISTS ecommerce;
CREATE SCHEMA IF NOT EXISTS warehouse;

-- ─── POS Schema ──────────────────────────────────────────────────────────────

CREATE TABLE pos.stores (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    city        VARCHAR(100) NOT NULL,
    region      VARCHAR(50)  NOT NULL,
    opened_at   DATE         NOT NULL
);

CREATE TABLE pos.staff (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    email       VARCHAR(150) NOT NULL,
    role        VARCHAR(50)  NOT NULL,
    store_id    INT          NOT NULL REFERENCES pos.stores(id)
);

CREATE TABLE pos.products (
    sku           VARCHAR(20)    PRIMARY KEY,
    name          VARCHAR(150)   NOT NULL,
    category      VARCHAR(50)    NOT NULL,
    color         VARCHAR(50),
    size          VARCHAR(10),
    cost_price    NUMERIC(10,2)  NOT NULL,
    retail_price  NUMERIC(10,2)  NOT NULL
);

CREATE TABLE pos.pos_transactions (
    id            SERIAL PRIMARY KEY,
    store_id      INT            NOT NULL REFERENCES pos.stores(id),
    staff_id      INT            REFERENCES pos.staff(id),
    customer_id   INT,                         -- nullable: walk-in customers
    occurred_at   TIMESTAMP      NOT NULL,
    total         NUMERIC(10,2)  NOT NULL
);

CREATE TABLE pos.pos_items (
    id              SERIAL PRIMARY KEY,
    transaction_id  INT           NOT NULL REFERENCES pos.pos_transactions(id),
    sku             VARCHAR(20)   NOT NULL REFERENCES pos.products(sku),
    qty             INT           NOT NULL,
    unit_price      NUMERIC(10,2) NOT NULL,
    discount        NUMERIC(10,2) NOT NULL DEFAULT 0
);

CREATE TABLE pos.inventory (
    store_id           INT           NOT NULL REFERENCES pos.stores(id),
    sku                VARCHAR(20)   NOT NULL REFERENCES pos.products(sku),
    qty_on_hand        INT           NOT NULL,
    reorder_threshold  INT           NOT NULL DEFAULT 10,
    updated_at         TIMESTAMP     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (store_id, sku)
);

-- ─── Ecommerce Schema ─────────────────────────────────────────────────────────

CREATE TABLE ecommerce.customers (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    email       VARCHAR(150) NOT NULL UNIQUE,
    address     TEXT,
    joined_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE ecommerce.online_orders (
    id             SERIAL PRIMARY KEY,
    customer_id    INT            NOT NULL REFERENCES ecommerce.customers(id),
    placed_at      TIMESTAMP      NOT NULL,
    status         VARCHAR(30)    NOT NULL,
    total          NUMERIC(10,2)  NOT NULL,
    shipping_cost  NUMERIC(10,2)  NOT NULL DEFAULT 0
);

CREATE TABLE ecommerce.online_items (
    id          SERIAL PRIMARY KEY,
    order_id    INT           NOT NULL REFERENCES ecommerce.online_orders(id),
    sku         VARCHAR(20)   NOT NULL REFERENCES pos.products(sku),
    qty         INT           NOT NULL,
    unit_price  NUMERIC(10,2) NOT NULL
);

-- ─── Warehouse Schema ─────────────────────────────────────────────────────────

CREATE TABLE warehouse.suppliers (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(150) NOT NULL,
    country          VARCHAR(80)  NOT NULL,
    lead_time_days   INT          NOT NULL
);

CREATE TABLE warehouse.purchase_orders (
    id           SERIAL PRIMARY KEY,
    supplier_id  INT         NOT NULL REFERENCES warehouse.suppliers(id),
    ordered_at   TIMESTAMP   NOT NULL,
    expected_at  TIMESTAMP   NOT NULL,
    status       VARCHAR(30) NOT NULL
);

CREATE TABLE warehouse.po_items (
    id          SERIAL PRIMARY KEY,
    po_id       INT           NOT NULL REFERENCES warehouse.purchase_orders(id),
    sku         VARCHAR(20)   NOT NULL REFERENCES pos.products(sku),
    qty_ordered INT           NOT NULL,
    unit_cost   NUMERIC(10,2) NOT NULL
);

CREATE TABLE warehouse.receipts (
    id           SERIAL PRIMARY KEY,
    po_id        INT       NOT NULL REFERENCES warehouse.purchase_orders(id),
    received_at  TIMESTAMP NOT NULL,
    store_id     INT       REFERENCES pos.stores(id)   -- null = warehouse receipt
);

-- Grants so the ELT service user can read everything
GRANT USAGE ON SCHEMA pos, ecommerce, warehouse TO meridian;
GRANT SELECT ON ALL TABLES IN SCHEMA pos TO meridian;
GRANT SELECT ON ALL TABLES IN SCHEMA ecommerce TO meridian;
GRANT SELECT ON ALL TABLES IN SCHEMA warehouse TO meridian;
