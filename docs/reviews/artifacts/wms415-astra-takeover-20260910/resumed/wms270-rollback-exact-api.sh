set -euo pipefail
cd /opt/wms
test "$(git rev-parse HEAD)" = 1922a2242ad626a9618cb2b7300e6cf500d25b4d
test "$(docker inspect wms_prod-api-1 --format '{{.Image}}')" = sha256:fe66c88c44f9fe346a4dda34b59f6dcf76cf3149b75e8ed9296f5f4570d5aaab
git archive 120b106cc3f47dd28fa499e094c7cde83e8a6b40:backend | docker build -t wms-recovery-api:120b106c -
test "$(git rev-parse HEAD)" = 1922a2242ad626a9618cb2b7300e6cf500d25b4d
docker image tag wms-recovery-api:120b106c wms_prod-api:latest
docker compose -p wms_prod -f docker-compose.prod.yml -f docker-compose.wms-host-8088.yml up -d --no-deps --no-build api </dev/null
docker inspect wms_prod-api-1 --format 'WMS_RECOVERY {{.Image}} {{.State.StartedAt}} {{.State.Running}}'
