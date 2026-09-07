#!/usr/bin/env bash
set -euo pipefail
umask 077
source_dir=/mnt/c/Users/user/wms-training-setup
test ! -e /opt/wms-training/.env
tar -xzf "$source_dir/wms387-training-runtime-prep.tar.gz" -C /opt
cd /opt/wms-training
cp "$source_dir/compose.yaml" compose.yaml
mkdir -p private
cp "$source_dir/seller-map.json" private/seller-map.json
cp "$source_dir/source-row-counts.json" private/source-row-counts.json
cp "$source_dir/create_secrets.py" "$source_dir/bootstrap_copy.py" .
python3 create_secrets.py /opt/wms-training --public-url http://192.168.12.62:8088
docker compose config --quiet
docker compose --progress plain build
docker compose up -d --wait db
gzip -dc "$source_dir/training.sql.gz" | docker compose exec -T db psql -q -U wms -d wms -v ON_ERROR_STOP=1
# Create container volumes without starting either application.
docker compose create api wb-emulator
docker run --rm --network none -v wms-training_files:/restore -v "$source_dir:/snapshot:ro" \
  --entrypoint sh wms-training-api -c 'tar -xzf /snapshot/files.tar.gz -C /restore'
docker run --rm --network none -v wms-training_emulator:/restore -v "$source_dir:/snapshot:ro" \
  --entrypoint sh wms-training-api -c 'tar -xzf /snapshot/emulator.tar.gz -C /restore wb_emulator.sqlite'
docker compose run --rm --no-deps -T --interactive=false -v /opt/wms-training:/training --entrypoint python api /training/bootstrap_copy.py
docker compose up -d --wait
docker compose ps
