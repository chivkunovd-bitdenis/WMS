#!/bin/sh
set -eu
# Starts the already installed Chrome in a separate profile. Installs nothing.
chrome_app='/Applications/Google Chrome.app'
if [ ! -d "$chrome_app" ]; then
  printf '%s\n' 'Installed Google Chrome was not found in /Applications. Nothing was installed or changed.' >&2
  exit 1
fi
exec /usr/bin/open -na "$chrome_app" --args \
  --kiosk-printing \
  "--user-data-dir=$HOME/Library/Application Support/WMS-Chrome-Print" \
  --no-first-run --no-default-browser-check \
  'https://sellerfocus.pro/packing-scan-check/'
