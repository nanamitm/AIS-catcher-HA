#!/usr/bin/env bash
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SH="${HERE}/../ais_catcher_stats/run.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT
mkdir -p "${WORK}/data" "${WORK}/nginx"

cat > "${WORK}/stubs.sh" <<'STUB'
bashio::config() {
    jq -r --arg k "$1" --arg d "${2:-}" \
        'if has($k) then .[$k] else $d end' "${DATA_DIR}/options.json"
}
bashio::config.has_value() {
    jq -e --arg k "$1" 'has($k) and .[$k] != null and .[$k] != ""' \
        "${DATA_DIR}/options.json" >/dev/null
}
bashio::config.true() {
    jq -e --arg k "$1" '.[$k] == true' "${DATA_DIR}/options.json" >/dev/null
}
bashio::services.available() { return 0; }
bashio::services() {
    case "$2" in
        host) echo mqtt.local ;;
        port) echo 1883 ;;
        username) echo user ;;
        password) echo pass ;;
    esac
}
bashio::log.info() { echo "[INFO] $*" >&2; }
bashio::log.warning() { echo "[WARNING] $*" >&2; }
bashio::log.fatal() { echo "[FATAL] $*" >&2; }
bashio::exit.nok() { exit 1; }
nginx() { return 0; }
exec() { exit 0; }
STUB

FAILURES=0
contains() {
    case "$3" in
        *"$2"*) echo "ok   - $1" ;;
        *) echo "FAIL - $1"; FAILURES=$((FAILURES + 1)) ;;
    esac
}
excludes() {
    case "$3" in
        *"$2"*) echo "FAIL - $1"; FAILURES=$((FAILURES + 1)) ;;
        *) echo "ok   - $1" ;;
    esac
}

run_case() {
    printf '%s' "$1" > "${WORK}/data/options.json"
    rm -f "${WORK}/nginx/upstream.conf" "${WORK}/nginx/decompress_upstream.conf"
    LOG="$(DATA_DIR="${WORK}/data" NGINX_CONF_DIR="${WORK}/nginx" \
        bash -c "source '${WORK}/stubs.sh'; source '${RUN_SH}'" 2>&1 || true)"
    UPSTREAM="$(cat "${WORK}/nginx/upstream.conf" 2>/dev/null || true)"
    DECOMPRESS="$(cat "${WORK}/nginx/decompress_upstream.conf" 2>/dev/null || true)"
}

BASE='"scan_interval":30,"device_name":"AIS-catcher","device_id":"aiscatcher","message_type_sensors":true,"remove_entities_on_stop":false,"log_level":"info","vessels":[],"vessel_timeout":30,"fleet_sensors":true,"nearby_radius":5'

contains "dashboard URL has a visible manifest default" \
    'dashboard_url: "http://192.168.1.10:8118"' \
    "$(cat "${HERE}/../ais_catcher_stats/config.yaml")"

echo "# web viewer"
run_case "{${BASE},\"url\":\"http://receiver.local:8100\",\"sidebar_view\":\"web_viewer\"}"
contains "viewer uses the statistics URL" 'set $ais_upstream "http://receiver.local:8100";' "${UPSTREAM}"
contains "dashboard decompressor is disabled" "return 503;" "${DECOMPRESS}"
excludes "viewer responses are not rewritten" "sub_filter" "${UPSTREAM}"

echo "# managed dashboard"
run_case "{${BASE},\"url\":\"http://receiver.local:8119\",\"sidebar_view\":\"dashboard\",\"dashboard_url\":\"http://receiver.local:8118\"}"
contains "dashboard goes through the decompression stage" "proxy_pass http://127.0.0.1:8098;" "${UPSTREAM}"
contains "decompressor uses dashboard_url" 'set $ais_upstream "http://receiver.local:8118";' "${DECOMPRESS}"
contains "dashboard is decompressed" "gunzip on;" "${DECOMPRESS}"
contains "dashboard API paths are rewritten" "sub_filter \"'/api/\" \"'api/\";" "${UPSTREAM}"
contains "dashboard assets are cache-busted" '?ingress=stats&hash=' "${UPSTREAM}"

echo "# missing dashboard URL"
run_case "{${BASE},\"url\":\"http://receiver.local:8100\",\"sidebar_view\":\"dashboard\"}"
contains "missing dashboard URL is logged" "dashboard_url is empty" "${LOG}"
contains "missing dashboard URL falls back to viewer" 'set $ais_upstream "http://receiver.local:8100";' "${UPSTREAM}"

if [ "${FAILURES}" -ne 0 ]; then
    echo "${FAILURES} check(s) failed"
    exit 1
fi
echo "all checks passed"
