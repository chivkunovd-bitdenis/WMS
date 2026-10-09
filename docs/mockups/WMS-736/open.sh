#!/bin/sh
# Открыть макет ТСД локально: http://127.0.0.1:16736/
# node_modules не ставится заново — берётся из основного checkout (диск почти полон).
set -e
cd "$(dirname "$0")"
DEPS=/Users/deniscivkunov/Projects/WMS/frontend/node_modules
[ -e node_modules ] || ln -s "$DEPS" node_modules
exec ./node_modules/.bin/vite --config vite.config.ts "$@"
