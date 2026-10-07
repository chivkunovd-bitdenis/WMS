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
REPO="$(git -C "$SRC" rev-parse --show-toplevel)"
SHA="$(git -C "$SRC" rev-parse HEAD)"
if [ -n "$(git -C "$REPO" status --porcelain -- tools/support_agent .codex/config.toml)" ]; then
  echo "Код службы или WMS context config не сохранены в Git. Сначала закоммитьте изменения."
  exit 1
fi

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

# Verify the installed bytes against the saved commit, before allowing launchd
# to run them. Config/state and the dependency environment are kept separately.
"$APP/.venv/bin/python" - "$REPO" "$APP" "$SHA" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

repo, app, sha = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
prefix = 'tools/support_agent/'
tracked = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '-z', prefix]).decode().split('\0')
hashes = {}
for relative in tracked:
    if not relative or relative.startswith(prefix + 'tests/'):
        continue
    name = relative.removeprefix(prefix)
    original = subprocess.check_output(['git', '-C', str(repo), 'show', f'{sha}:{relative}'])
    installed = (app / name).read_bytes()
    if installed != original:
        raise SystemExit(f'Installed file differs from {sha}: {name}')
    hashes[name] = hashlib.sha256(installed).hexdigest()
temporary = app / '.INSTALLATION.tmp'
temporary.write_text(json.dumps({'sha': sha, 'files': hashes}, indent=2) + '\n')
temporary.replace(app / 'INSTALLATION.json')
print(f'Установлен и проверен Git commit {sha}: {len(hashes)} файлов.')
PY

# The live desktop thread's cwd is the main WMS checkout. Install only its
# two context settings from the same saved SHA, preserving all owner fields.
(cd "$APP" && "$APP/.venv/bin/python" -m support_agent.context_config "$REPO" "$SHA" "$APP")

sed -e "s#__APP__#$APP#g" -e "s#__HOME__#$HOME#g" \
  "$SRC/launchd/$LABEL.plist.template" > "$PLIST"
plutil -lint "$PLIST"
if [ -n "${WMS_AGENT_SKIP_LAUNCHD:-}" ]; then
  echo "Проверка пройдена, launchd пропущен (WMS_AGENT_SKIP_LAUNCHD)."; exit 0
fi
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl enable "gui/$(id -u)/$LABEL"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
echo "Служба $LABEL запущена. Лог: $HOME/Library/Logs/wms-support-agent.log"
