.PHONY: up down logs ps \
        generate-clean generate-dirty \
        elt \
        seed-clean seed-dirty

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

# ─── Data generation ──────────────────────────────────────────────────────────

# Pristine data — no nulls, no drift, no late orders. Good starting point.
generate-clean:
	docker compose run --rm --profile jobs generator-clean

# Dirty data — quality issues baked in (null customer_ids, voided txns, etc.)
generate-dirty:
	docker compose run --rm --profile jobs generator-dirty

# ─── ELT: Postgres → Iceberg ──────────────────────────────────────────────────

elt:
	docker compose run --rm --profile jobs elt

# ─── Full pipelines ───────────────────────────────────────────────────────────

# Clean end-to-end: seed + load to Iceberg
seed-clean: generate-clean elt

# Dirty end-to-end: seed + load to Iceberg
seed-dirty: generate-dirty elt
