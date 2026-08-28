#!/usr/bin/env bash
# Откат правки «артикул уникален внутри продавца» (миграция 20260825_0101).
#
# Точка, к которой возвращаемся — снято 25.08.2026 перед выкаткой:
#   ветка   etalon
#   коммит  0339e4b0d5440e663e40773e28e1e57f4d724e3d
#   alembic 20260823_0100
#   товаров 11776
#   дамп    /root/wms-backups/wms-20260825-150000-before-sku-unique.dump
#           sha256 начинается на ed9be9279cb48796
#           копия у разработчика: ~/wms-backups/
#
# Запускать НА СЕРВЕРЕ из /opt/wms:
#   ./scripts/deploy/rollback-sku-unique-20260825.sh --check    # только показать, что мешает
#   ./scripts/deploy/rollback-sku-unique-20260825.sh --apply    # откатить код и миграцию
#   ./scripts/deploy/rollback-sku-unique-20260825.sh --restore  # восстановить базу из дампа
#
# ВАЖНО. Обратная миграция возвращает ограничение (tenant_id, sku_code). Если после
# выкатки успел пройти импорт каталога ООО «Фэшн», в базе появятся товары с тем же
# артикулом, что у Loviana, и ограничение просто не создастся. Поэтому --apply сначала
# показывает конфликтующие строки и без --force не идёт дальше: удалять товары должен
# человек, осознанно, а не скрипт.

set -euo pipefail

TARGET_COMMIT="0339e4b0d5440e663e40773e28e1e57f4d724e3d"
TARGET_ALEMBIC="20260823_0100"
DUMP="/root/wms-backups/wms-20260825-150000-before-sku-unique.dump"

REPO_DIR="${WMS_REPO_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$REPO_DIR"

COMPOSE=(docker compose -f docker-compose.prod.yml)
if [[ -f docker-compose.wms-host-8088.yml ]]; then
  COMPOSE+=(-f docker-compose.wms-host-8088.yml)
fi
PSQL=(docker exec -i wms_prod-db-1 psql -U postgres -d wms)

MODE=""
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --check) MODE="check" ;;
    --apply) MODE="apply" ;;
    --restore) MODE="restore" ;;
    --force) FORCE=1 ;;
    *) echo "неизвестный аргумент: $arg" >&2; exit 2 ;;
  esac
done
if [[ -z "$MODE" ]]; then
  echo "укажи --check, --apply или --restore" >&2
  exit 2
fi

show_state() {
  echo "==> сейчас на сервере"
  echo "    коммит  $(git rev-parse HEAD)"
  echo "    alembic $("${PSQL[@]}" -A -t -c 'select version_num from alembic_version')"
  echo "    товаров $("${PSQL[@]}" -A -t -c 'select count(*) from products')"
  echo "==> цель отката"
  echo "    коммит  $TARGET_COMMIT"
  echo "    alembic $TARGET_ALEMBIC"
}

conflicts() {
  "${PSQL[@]}" -A -F' | ' -c "
    select p.tenant_id, p.sku_code, count(*) as strok,
           string_agg(coalesce(s.name,'—'), ', ') as prodavcy
    from products p left join sellers s on s.id = p.seller_id
    group by p.tenant_id, p.sku_code having count(*) > 1
    order by count(*) desc"
}

case "$MODE" in
  check)
    show_state
    echo "==> артикулы, из-за которых обратная миграция не пройдёт"
    conflicts
    ;;

  apply)
    show_state
    n=$(conflicts | grep -c '|' || true)
    if [[ "$n" -gt 1 && "$FORCE" -eq 0 ]]; then
      echo
      echo "СТОП: найдены артикулы, занятые несколькими продавцами — обратная миграция упадёт."
      conflicts
      echo
      echo "Это товары, которые завёл импорт после выкатки. Реши, что с ними делать:"
      echo "  - если остатков и движений по ним нет, их можно удалить вручную;"
      echo "  - если остатки уже начислены, откат миграции невозможен, нужен --restore."
      echo "Осознанно продолжить (упадёт, если конфликты остались): добавь --force"
      exit 1
    fi
    echo "==> alembic downgrade $TARGET_ALEMBIC"
    "${COMPOSE[@]}" run --rm migrations alembic downgrade "$TARGET_ALEMBIC"
    echo "==> git checkout $TARGET_COMMIT"
    git checkout --detach "$TARGET_COMMIT"
    echo "==> пересборка и подъём"
    for svc in migrations api celery_worker celery_beat web; do
      "${COMPOSE[@]}" build "$svc"
    done
    "${COMPOSE[@]}" up -d
    show_state
    ;;

  restore)
    if [[ ! -f "$DUMP" ]]; then
      echo "нет дампа: $DUMP" >&2
      exit 1
    fi
    if [[ "$FORCE" -eq 0 ]]; then
      echo "ВНИМАНИЕ: восстановление затрёт всё, что произошло на проде после $(basename "$DUMP")."
      echo "Это крайняя мера. Если уверен — добавь --force"
      exit 1
    fi
    echo "==> гасим приложение, база остаётся"
    "${COMPOSE[@]}" stop api celery_worker celery_beat web
    echo "==> восстановление из $DUMP"
    docker exec -i wms_prod-db-1 pg_restore -U postgres -d wms --clean --if-exists < "$DUMP"
    echo "==> git checkout $TARGET_COMMIT"
    git checkout --detach "$TARGET_COMMIT"
    for svc in migrations api celery_worker celery_beat web; do
      "${COMPOSE[@]}" build "$svc"
    done
    "${COMPOSE[@]}" up -d
    show_state
    ;;
esac
