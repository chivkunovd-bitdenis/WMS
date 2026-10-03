#!/bin/bash
# Установка агента-диспетчера как службы launchd для текущего пользователя (WMS-641, R32).
# Копирует код в ~/.wms-support-agent/app (чтобы смена ветки в репозитории его не ломала),
# ставит зависимости в отдельный venv, регистрирует службу с автоперезапуском.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$HOME/.wms-support-agent"
APP="$STATE/app"
LABEL="pro.sellerfocus.wms-support-agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$APP" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
rsync -a --delete --exclude .venv --exclude tests --exclude __pycache__ --exclude '.*cache' \
  "$SRC/" "$APP/"
[ -d "$APP/.venv" ] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"

if [ ! -f "$STATE/config.json" ]; then
  cp "$SRC/config.example.json" "$STATE/config.json"
  chmod 600 "$STATE/config.json"
  echo "Создан $STATE/config.json из примера. Заполните его и запустите этот скрипт ещё раз."
  exit 0
fi
chmod 600 "$STATE/config.json"
# Модуль лежит в $APP, поэтому проверку выполняем оттуда, а не из текущего каталога (F10).
(cd "$APP" && "$APP/.venv/bin/python" -m support_agent check-config --config "$STATE/config.json") || {
  echo "Конфигурация неполная (см. выше). Служба не запущена."; exit 1; }

sed -e "s#__APP__#$APP#g" -e "s#__HOME__#$HOME#g" \
  "$SRC/launchd/$LABEL.plist.template" > "$PLIST"
plutil -lint "$PLIST"
if [ -n "${WMS_AGENT_SKIP_LAUNCHD:-}" ]; then
  echo "Проверка пройдена, launchd пропущен (WMS_AGENT_SKIP_LAUNCHD)."; exit 0
fi
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
echo "Служба $LABEL запущена. Лог: $HOME/Library/Logs/wms-support-agent.log"
