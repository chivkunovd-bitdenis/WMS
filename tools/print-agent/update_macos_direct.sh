#!/bin/bash
# Native macOS Direct updater. No release pins are inferred from a branch/latest.
# The reviewed distribution supplies updater-manifest.json beside this command.
set -euo pipefail
umask 077

fail() { printf '%s\n' "WMS Print update: $*" >&2; exit 1; }
json() { /usr/bin/plutil -extract "$2" raw -expect "${3:-string}" -o - "$1" 2>/dev/null; }
hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
script_dir=$(cd -P "$(dirname "$0")" && pwd)
app_dir="$script_dir"
state_dir="${HOME:-}/Library/Application Support/WMS Print/direct"
backup_dir="${HOME:-}/Library/Application Support/WMS Print/updates"
manifest="$script_dir/updater-manifest.json"
while [ "$#" -gt 0 ]; do
    [ "$#" -ge 2 ] || fail 'Missing command argument'
    case "$1" in
        --app-dir) app_dir=$2;;
        --state-dir) state_dir=$2;;
        --backup-dir) backup_dir=$2;;
        --manifest) manifest=$2;;
        *) fail "Unknown argument: $1";;
    esac
    shift 2
done

[ "$(uname -s)" = Darwin ] || fail 'Only native macOS Direct packages are supported'
machine=$(uname -m)
arm=$(sysctl -n hw.optional.arm64 2>/dev/null || true)
translated=$(sysctl -n sysctl.proc_translated 2>/dev/null || true)
if [ "$arm" = 1 ] || [ "$translated" = 1 ]; then arch=arm64
elif [ "$machine" = x86_64 ]; then arch=x86_64
else fail "Unsupported hardware: $machine"; fi
[ -f "$manifest" ] || fail 'Reviewed immutable updater-manifest.json is required; distribution is not configured'
source_commit=$(json "$manifest" source_commit) || fail 'Invalid manifest source_commit'
url=$(json "$manifest" "artifacts.$arch.url") || fail "Missing $arch artifact URL"
checksum=$(json "$manifest" "artifacts.$arch.sha256") || fail 'Missing archive SHA256'
[[ "$source_commit" =~ ^[0-9a-f]{40}$ ]] || fail 'Invalid pinned source_commit'
[[ "$checksum" =~ ^[0-9a-f]{64}$ ]] || fail 'Invalid pinned archive SHA256'
[[ "$url" = https://* ]] && [[ "$url" != *'/latest/'* ]] && [[ "$url" != *'?'* ]] && [[ "$url" != *'#'* ]] || fail 'A pinned HTTPS artifact URL is required'

# Resolve the selected filesystem boundaries; refuse overlapping trees.
parent=$(cd "$(dirname "$app_dir")" && pwd -L) || fail 'Application parent does not exist'
app_dir="$parent/$(basename "$app_dir")"
[ "$(basename "$app_dir")" != . ] && [ "$(basename "$app_dir")" != .. ] && [ ! -L "$app_dir" ] || fail 'Application must be an ordinary directory'
[ -d "$state_dir" ] && [ ! -L "$state_dir" ] || fail 'Existing Direct state directory required'
state_dir=$(cd "$state_dir" && pwd -L)
case "$state_dir/" in "$app_dir/"*) fail 'State must live outside the application';; esac
case "$app_dir/" in "$state_dir/"*) fail 'Application must live outside Direct state';; esac
mkdir -p "$backup_dir" || fail 'Cannot create private archive directory'
[ ! -L "$backup_dir" ] || fail 'Archive directory cannot be a symbolic link'
backup_dir=$(cd "$backup_dir" && pwd -L)
case "$backup_dir/" in "$app_dir/"*|"$state_dir/"*) fail 'Archive directory overlaps application/state';; esac
case "$app_dir/" in "$backup_dir/"*) fail 'Application overlaps archive directory';; esac
app_physical="$(cd -P "$parent" && pwd)/$(basename "$app_dir")"
state_physical=$(cd -P "$state_dir" && pwd)
backup_physical=$(cd -P "$backup_dir" && pwd)
case "$state_physical/" in "$app_physical/"*) fail 'State overlaps physical application tree';; esac
case "$app_physical/" in "$state_physical/"*|"$backup_physical/"*) fail 'Application overlaps physical state/archive tree';; esac
case "$backup_physical/" in "$app_physical/"*|"$state_physical/"*) fail 'Archive overlaps physical application/state tree';; esac
work="$parent/.$(basename "$app_dir").direct-update"
mkdir -p "$work"
[ ! -L "$work" ] || fail 'Unsafe update workspace'
lock="$work/lock"
locked=0
for ((attempt=0; attempt<100; attempt++)); do
    if mkdir "$lock" 2>/dev/null; then
        printf '%s\n' "$$" > "$lock/pid"
        locked=1; break
    fi
    owner=$(cat "$lock/pid" 2>/dev/null || true)
    if [[ "$owner" =~ ^[0-9]+$ ]] && ! builtin kill -0 "$owner" 2>/dev/null; then
        # Serialize stale-lock reclamation too: two callers cannot remove a new lock.
        if mkdir "$work/reclaim" 2>/dev/null; then
            current=$(cat "$lock/pid" 2>/dev/null || true)
            if [ "$current" = "$owner" ] && ! builtin kill -0 "$owner" 2>/dev/null; then rm -rf "$lock"; fi
            rmdir "$work/reclaim"
        fi
    fi
    sleep 0.05
done
[ "$locked" = 1 ] || fail 'Another update is running; repeat this command when it finishes'

transaction=0
stage=''
backup=''
old_running=0
cleanup() {
    local result=$?
    trap - EXIT HUP INT TERM
    if [ "$result" -ne 0 ] && [ "$transaction" = 1 ]; then
        rollback || printf '%s\n' "Recovery retained at $work; repeat the same command. Current print history is untouched." >&2
    fi
    if [ -n "$stage" ] && [ "$transaction" = 0 ]; then rm -rf "$stage"; fi
    rm -rf "$lock"
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

port_pid() { lsof -nP -iTCP:17843 -sTCP:LISTEN -t 2>/dev/null || true; }
process_path() { ps -p "$1" -o comm= 2>/dev/null | sed 's/^[[:space:]]*//'; }
process_matches() {
    local path physical
    path=$(process_path "$1")
    [ "$path" = "$app_dir/wms-print" ] && return 0
    [ "$(basename "$path")" = wms-print ] || return 1
    physical=$(cd -P "$(dirname "$path")" 2>/dev/null && pwd) || return 1
    [ "$physical/wms-print" = "$app_physical/wms-print" ]
}
owned_pid() {
    local pid path
    pid=$(port_pid)
    [ -n "$pid" ] || return 1
    [[ "$pid" =~ ^[0-9]+$ ]] || return 2
    process_matches "$pid" || return 2
    printf '%s\n' "$pid"
}
stop_owned() {
    local pid status i
    status=0; pid=$(owned_pid) || status=$?
    [ "$status" != 2 ] || { printf '%s\n' 'Port 17843 belongs to another executable; it was not stopped.' >&2; return 1; }
    [ "$status" = 0 ] || return 0
    # Recheck immediately before TERM. No blanket process-name kill or forced kill.
    process_matches "$pid" || return 1
    kill -TERM "$pid" || return 1
    for ((i=0; i<50; i++)); do
        [ "$(port_pid)" != "$pid" ] && ! kill -0 "$pid" 2>/dev/null && return 0
        sleep 0.05
    done
    printf '%s\n' 'Owned executable did not stop; application was not replaced.' >&2
    return 1
}
metadata_ok() {
    local directory=$1
    [ -f "$directory/build.json" ] && [ ! -L "$directory/build.json" ] && [ -x "$directory/wms-print" ] && [ ! -L "$directory/wms-print" ] || return 1
    [ "$(json "$directory/build.json" source_commit)" = "$source_commit" ] &&
    [ "$(json "$directory/build.json" runtime)" = direct ] &&
    [ "$(json "$directory/build.json" console bool)" = true ] &&
    [ "$(json "$directory/build.json" architecture)" = "$arch" ] &&
    [ "$(lipo -archs "$directory/wms-print")" = "$arch" ] &&
    [[ "$(file "$directory/wms-print")" = *'Mach-O'* ]] || return 1
    [ -z "$(find "$directory" \( -iname '*python*' -o -name _internal \) -print -quit)" ]
}
health_ok() {
    local pid value queue
    pid=$(owned_pid) || return 1
    [ "$pid" = "$(port_pid)" ] || return 1
    value=$(curl --fail --silent --show-error --max-time 2 http://127.0.0.1:17843/health) || return 1
    printf '%s' "$value" > "$work/health.json"
    [ "$(json "$work/health.json" app)" = 'WMS Print Direct' ] && [ "$(json "$work/health.json" protocolVersion integer)" = 2 ] &&
    process_matches "$pid" || return 1
    if [ "${1:-target}" = previous ]; then
        # Earlier compatible binaries have no readiness flag. Only read the named
        # system default; never run an unknown option which could start a server.
        value=$(lpstat -d 2>/dev/null) || return 1
        [[ "$value" = *:* ]] || return 1
        queue=$(printf '%s' "${value#*:}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        [ -n "$queue" ] && [[ "$queue" != *[[:space:]/\\]* ]] && lpstat -p "$queue" > "$work/readiness.log" 2>&1
    else
        "$app_dir/wms-print" --readiness > "$work/readiness.log" 2>&1
    fi
}
start_owned() {
    local i child child_status=0
    [ -z "$(port_pid)" ] || return 1
    nohup "$app_dir/wms-print" --updater-start "$state_dir" > "$work/start.log" 2>&1 < /dev/null &
    child=$!
    for ((i=0; i<50; i++)); do
        if health_ok "${1:-target}"; then return 0; fi
        if ! builtin kill -0 "$child" 2>/dev/null; then
            wait "$child" || child_status=$?
            [ "$child_status" = 0 ] || break
        fi
        sleep 0.05
    done
    printf '%s\n' 'Start/readiness failed. If macOS blocked this verified executable, allow it in Privacy & Security, then repeat this command. Chrome may request local access for the WMS site.' >&2
    return 1
}
restart_previous() {
    local record status
    # Do not let an older ordinary entrypoint automatically resume saved jobs.
    while IFS= read -r -d '' record; do
        status=$(json "$record" status) || { printf '%s\n' 'Previous bytes retained; unreadable journal prevents automatic restart.' >&2; return 1; }
        if [ "$status" = saved ]; then
            printf '%s\n' 'Previous bytes retained; pending saved jobs require a separate normal launch. Print history retained.' >&2
            return 1
        fi
    done < <(find "$state_dir/jobs-v2" -name '*.json' -type f -print0 2>/dev/null)
    start_owned previous
}
tree_inventory() {
    local directory=$1 path
    (cd "$directory" && find . -print0 | LC_ALL=C sort -z | while IFS= read -r -d '' path; do
        # Inventory contains hashes and permissions only; never configuration contents.
        printf '%s\0%s\0' "$(/usr/bin/stat -f '%Lp' "$path")" "$path"
        if [ -L "$path" ]; then printf 'link\0%s\0' "$(readlink "$path")"
        elif [ -f "$path" ]; then printf 'file\0%s\0' "$(hash "$path")"
        elif [ -d "$path" ]; then printf 'directory\0'
        else return 1; fi
    done)
}
copy_verified() {
    local from=$1 to=$2
    ditto "$from" "$to" || return 1
    tree_inventory "$from" > "$work/from.inventory" && tree_inventory "$to" > "$work/to.inventory" &&
    cmp -s "$work/from.inventory" "$work/to.inventory"
}
clear_transaction() {
    rm -f "$work/transaction" "$work/backup-path" "$work/old-running"
    transaction=0
    rm -rf "$work/previous" "$work/next"
}
rollback() {
    # Application-only recovery: NEVER copy the archived state over current history.
    local foreign=0
    stop_owned || foreign=1
    if [ -d "$work/previous" ]; then
        rm -rf "$work/failed-target"
        if [ -d "$app_dir" ]; then mv "$app_dir" "$work/failed-target" || return 1; fi
        mv "$work/previous" "$app_dir" || return 1
    elif [ ! -d "$app_dir" ]; then
        [ -d "$backup/application" ] || return 1
        copy_verified "$backup/application" "$work/restore" || return 1
        mv "$work/restore" "$app_dir" || return 1
    fi
    [ -d "$backup/application" ] || return 1
    tree_inventory "$backup/application" > "$work/from.inventory" && tree_inventory "$app_dir" > "$work/to.inventory" &&
    cmp -s "$work/from.inventory" "$work/to.inventory" || return 1
    clear_transaction
    rm -rf "$work/failed-target"
    if [ "$foreign" != 0 ]; then
        printf '%s\n' 'Previous application bytes restored; foreign port owner retained, restart not confirmed.' >&2
        return 1
    fi
    if [ "$old_running" = 1 ]; then
        # A prior compatible binary may lack --updater-start. Never start it with
        # saved jobs which its normal entrypoint would automatically submit.
        restart_previous || { printf '%s\n' 'Previous application bytes restored; working restart was not confirmed. Print history retained.' >&2; return 1; }
    fi
}

# Any interruption after the intent record is rolled back before another update.
if [ -f "$work/transaction" ]; then
    backup=$(cat "$work/backup-path")
    old_running=$(cat "$work/old-running")
    transaction=1
    rollback || fail 'Interrupted update needs recovery; retained archives were not overwritten'
fi
[ -d "$app_dir" ] && [ -f "$app_dir/wms-print" ] || fail 'Existing application directory required'
status=0; pid=$(owned_pid) || status=$?
[ "$status" != 2 ] || fail 'Port 17843 belongs to a different executable; nothing was stopped'
if [ "$status" = 0 ]; then old_running=1; fi

# A unique staging tree on the application volume is never merged into the old tree.
stage=$(mktemp -d "$parent/.wms-print-stage.XXXXXXXX")
curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --max-time 120 "$url" -o "$stage/package.zip" || fail 'Pinned artifact download failed'
[ "$(hash "$stage/package.zip")" = "$checksum" ] || fail 'Archive SHA256 mismatch'
/usr/bin/unzip -tq "$stage/package.zip" > /dev/null || fail 'Invalid ZIP archive'
/usr/bin/zipinfo -1 "$stage/package.zip" > "$stage/entries"
while IFS= read -r entry; do
    case "/$entry/" in */../*|*/./*|*\\*) fail 'Unsafe ZIP path';; esac
    case "$entry" in
        __MACOSX/*) continue;;
        wms-print/*) ;;
        *) fail 'ZIP contains files outside wms-print';;
    esac
done < "$stage/entries"
# The native console package has no symbolic links; reject them before extraction.
/usr/bin/zipinfo -l "$stage/package.zip" > "$stage/attributes"
if /usr/bin/grep -q '^l' "$stage/attributes"; then fail 'Symlinks are not supported in target archives'; fi
ditto -xk "$stage/package.zip" "$stage/unpacked" || fail 'Archive extraction failed'
target="$stage/unpacked/wms-print"
metadata_ok "$target" || fail 'Target is not the pinned native Direct console package'
codesign --verify --strict "$target/wms-print" || fail 'Target signature verification failed'
"$target/wms-print" --self-test > "$work/self-test.log" 2>&1 || fail 'Unpacked native self-test could not run/pass. If macOS blocked this verified executable, allow only it in Privacy & Security, then repeat. Previous application is still running.'
# Pins are delivered beside the command (they cannot be embedded in a ZIP whose
# own hash they contain). Carry this reviewed manifest into the prepared tree so
# the installed ordinary command retains its defaults on the next invocation.
cp -p "$manifest" "$target/updater-manifest.json" || fail 'Cannot retain reviewed updater manifest; previous application retained'
cmp -s "$manifest" "$target/updater-manifest.json" || fail 'Prepared manifest differs from reviewed pins'
target_hash=$(hash "$target/wms-print")
if metadata_ok "$app_dir" && [ "$(hash "$app_dir/wms-print")" = "$target_hash" ]; then
    if health_ok; then printf '%s\n' 'Verified target already running; previous archives and print history retained.'; exit 0; fi
    [ -z "$(port_pid)" ] || fail 'Installed target readiness failed; existing process was retained'
    start_owned || fail 'Installed target could not be started; history retained'
    printf '%s\n' 'Verified installed target restarted; archives and print history retained.'
    exit 0
fi

app_kb=$(du -sk "$app_dir" | /usr/bin/awk '{print $1}')
state_kb=$(du -sk "$state_dir" | /usr/bin/awk '{print $1}')
target_kb=$(du -sk "$target" | /usr/bin/awk '{print $1}')
free_app=$(df -k "$parent" | /usr/bin/awk 'END {print $4}')
free_backup=$(df -k "$backup_dir" | /usr/bin/awk 'END {print $4}')
[[ "$free_app" =~ ^[0-9]+$ ]] && [[ "$free_backup" =~ ^[0-9]+$ ]] || fail 'Cannot verify free space'
needed=$((app_kb + state_kb + target_kb + 1024))
[ "$free_app" -gt "$needed" ] && [ "$free_backup" -gt "$needed" ] || fail 'Not enough space for verified archives and atomic replacement'
backup=$(mktemp -d "$backup_dir/previous.XXXXXXXX")
# Archive the complete old application before stopping; validate a readable copy.
copy_verified "$app_dir" "$backup/application" || fail 'Previous application archive failed; application retained'
rm -rf "$work/next"
copy_verified "$target" "$work/next" || fail 'Cannot prepare atomic target tree; previous application retained'
stop_owned || fail 'Previous application could not be stopped safely'
# Stop has quiesced the runtime: preserve the final complete journal/config snapshot.
if ! copy_verified "$state_dir" "$backup/state"; then
    [ "$old_running" != 1 ] || restart_previous || true
    fail 'Direct state archive failed; application not replaced'
fi
# Existing adjacent configuration is included only within the selected state parent.
for config in "$(dirname "$state_dir")/config.json" "$(dirname "$state_dir")/config"; do
    if [ -e "$config" ] || [ -L "$config" ]; then
        cp -pPR "$config" "$backup/" || { [ "$old_running" != 1 ] || restart_previous || true; fail 'Configuration archive failed; application not replaced'; }
    fi
done
printf '%s\n' "$backup" > "$work/backup-path"
printf '%s\n' "$old_running" > "$work/old-running"
printf '%s\n' 'replace' > "$work/transaction"
transaction=1
sync
mv "$app_dir" "$work/previous" || fail 'Cannot retain previous application for replacement'
mv "$work/next" "$app_dir" || fail 'Atomic application replacement failed'
metadata_ok "$app_dir" && [ "$(hash "$app_dir/wms-print")" = "$target_hash" ] || fail 'Installed target differs from verified staging'
start_owned || fail 'Target launch/readiness failed; restoring previous application'
metadata_ok "$app_dir" && [ "$(hash "$app_dir/wms-print")" = "$target_hash" ] && health_ok || fail 'Running target verification failed'
sync
clear_transaction
printf '%s\n' "Verified native Direct target $source_commit ($arch). Previous application/state archive: $backup. Physical printing has not been tested."
