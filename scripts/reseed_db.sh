#!/usr/bin/env bash
set -euo pipefail

CONTAINER=${1:-sports_card_db}
DB=${POSTGRES_DB:-sports_cards}
USER=${POSTGRES_USER:-postgres}

printf "Reseeding %s (db=%s user=%s)\n" "$CONTAINER" "$DB" "$USER"

docker cp scripts/reset_demo_data.sql "$CONTAINER":/tmp/reset_demo_data.sql
docker cp scripts/init_db.sql "$CONTAINER":/tmp/init_db.sql
docker cp seed/demo_seed.sql "$CONTAINER":/tmp/demo_seed.sql

docker exec -i "$CONTAINER" psql -U "$USER" -d "$DB" -f /tmp/reset_demo_data.sql
docker exec -i "$CONTAINER" psql -U "$USER" -d "$DB" -f /tmp/init_db.sql
docker exec -i "$CONTAINER" psql -U "$USER" -d "$DB" -f /tmp/demo_seed.sql

echo "Reseed complete"
