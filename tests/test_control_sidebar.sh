#!/usr/bin/env bash
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SH="${HERE}/../ais_catcher_control/run.sh"
NGINX_CONF="${HERE}/../ais_catcher_control/nginx.conf"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT
mkdir -p "${WORK}/data" "${WORK}/nginx"

cat > "${WORK}/stubs.sh" <<'STUB'
bashio::config() {
    jq -r --arg k "$1" --arg d "${2:-}" \
        'if has($k) then .[$k] else $d end' "${DATA_DIR}/options.json"
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
    rm -f "${WORK}/nginx/upstream.conf"
    LOG="$(DATA_DIR="${WORK}/data" NGINX_CONF_DIR="${WORK}/nginx" \
        bash -c "source '${WORK}/stubs.sh'; source '${RUN_SH}'" 2>&1 || true)"
    UPSTREAM="$(cat "${WORK}/nginx/upstream.conf" 2>/dev/null || true)"
}

echo "# HTTP target"
run_case '{"url":"http://receiver.local:8110","verify_ssl":true}'
contains "control URL becomes dynamic nginx target" \
    'set $control_upstream "http://receiver.local:8110";' "${UPSTREAM}"
excludes "HTTP target has no TLS directives" "proxy_ssl_verify" "${UPSTREAM}"
contains "startup identifies remote control" "receiver.local:8110" "${LOG}"

echo "# verified HTTPS target"
run_case '{"url":"https://receiver.local:8110/","verify_ssl":true}'
contains "trailing slash is removed" \
    'set $control_upstream "https://receiver.local:8110";' "${UPSTREAM}"
contains "HTTPS certificate verification is enabled" "proxy_ssl_verify on;" "${UPSTREAM}"

echo "# self-signed HTTPS target"
run_case '{"url":"https://receiver.local:8110","verify_ssl":false}'
excludes "verification can be disabled" "proxy_ssl_verify on;" "${UPSTREAM}"

CONFIG="$(cat "${NGINX_CONF}")"
contains "redirects become ingress-relative" 'proxy_redirect ~^/(.*)$ ./$1;' "${CONFIG}"
contains "session cookie is scoped to ingress" 'proxy_cookie_path / $control_cookie_path;' "${CONFIG}"
contains "API paths are rewritten" "sub_filter \"'/api/\" \"'api/\";" "${CONFIG}"
contains "SSE is not buffered" "proxy_buffering off;" "${CONFIG}"
contains "long actions get an extended timeout" "proxy_read_timeout 3600s;" "${CONFIG}"

if [ "${FAILURES}" -ne 0 ]; then
    echo "${FAILURES} check(s) failed"
    exit 1
fi
echo "all checks passed"
