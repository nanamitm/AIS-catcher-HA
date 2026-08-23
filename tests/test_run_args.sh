#!/usr/bin/env bash
# Offline test of ais_catcher/run.sh: the options in, the AIS-catcher command
# line out.  Nothing here needs Home Assistant, a Supervisor, an SDR or the
# add-on image.  bashio and nginx are stubbed out as shell functions, and the
# `exec` at the end of run.sh is stubbed too -- capturing the command line
# instead of letting it replace the shell is what makes it testable at all.
# run.sh is pointed at a fixture directory instead of /data.
#
#   bash tests/test_run_args.sh
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SH="${HERE}/../ais_catcher/run.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

mkdir -p "${WORK}/data" "${WORK}/nginx" "${WORK}/plugins"

# --------------------------------------------------------------- the stubs ---

# bashio reads the same options.json the Supervisor writes, so these are a thin
# layer over jq and the fixtures below are the real thing.
cat > "${WORK}/stubs.sh" <<'STUB'
bashio::config() {
    jq -r --arg k "$1" 'if has($k) then .[$k] else empty end' "${DATA_DIR}/options.json"
}
bashio::config.has_value() {
    jq -e --arg k "$1" \
        'has($k) and .[$k] != null and .[$k] != ""
         and (.[$k] | if type == "array" then length > 0 else true end)' \
        "${DATA_DIR}/options.json" > /dev/null
}
bashio::config.true() {
    jq -e --arg k "$1" '.[$k] == true' "${DATA_DIR}/options.json" > /dev/null
}
bashio::log.info() { echo "[INFO] $*" >&2; }
bashio::log.warning() { echo "[WARNING] $*" >&2; }
bashio::log.fatal() { echo "[FATAL] $*" >&2; }
bashio::exit.nok() { exit 1; }

# run.sh asks the binary whether it supports managed mode before using it.  The
# test says what that answer is; AIS_CATCHER_HELP is the help text it prints.
AIS-catcher() { printf '%s\n' "${AIS_CATCHER_HELP:-}"; }

# The ingress proxy is not what is under test; that a failure to start it does
# not stop the receiver is, so `nginx -t` succeeds here and the failure path is
# left to the other direction.
nginx() { return 0; }

exec() {
    printf '%s' "$1" > "${ARGV_OUT}.cmd"
    shift
    printf '%s\n' "$@" > "${ARGV_OUT}"
    exit 0
}
STUB

# ------------------------------------------------------------- the harness ---

FAILURES=0
LOG=""
ARGV=""
CMD=""

run_case() {
    # run_case <options json> [plugin dir]; leaves the command line in $CMD and
    # $ARGV, and everything that was logged in $LOG.
    printf '%s' "$1" > "${WORK}/data/options.json"
    rm -f "${WORK}/argv" "${WORK}/argv.cmd" "${WORK}/nginx/upstream.conf"
    LOG="$(
        DATA_DIR="${WORK}/data" \
        NGINX_CONF_DIR="${WORK}/nginx" \
        PLUGIN_DIR="${2:-${WORK}/plugins}" \
        ARGV_OUT="${WORK}/argv" \
        AIS_CATCHER_HELP="${AIS_CATCHER_HELP:-}" \
        bash -c "source '${WORK}/stubs.sh'; source '${RUN_SH}'" 2>&1 || true
    )"
    CMD="$(cat "${WORK}/argv.cmd" 2>/dev/null || true)"
    ARGV="$(cat "${WORK}/argv" 2>/dev/null | tr '\n' ' ' | sed 's/ $//')"
}

check() {   # check <what> <expected> <actual>
    if [ "$2" = "$3" ]; then
        echo "ok   - $1"
    else
        echo "FAIL - $1"
        echo "       expected: $2"
        echo "       actual:   $3"
        FAILURES=$((FAILURES + 1))
    fi
}

contains() {   # contains <what> <needle> <haystack>
    case "$3" in
        *"$2"*) echo "ok   - $1" ;;
        *)      echo "FAIL - $1"; echo "       not found: $2"; echo "       in: $3"
                FAILURES=$((FAILURES + 1)) ;;
    esac
}

excludes() {   # excludes <what> <needle> <haystack>
    case "$3" in
        *"$2"*) echo "FAIL - $1"; echo "       found: $2"; echo "       in: $3"
                FAILURES=$((FAILURES + 1)) ;;
        *)      echo "ok   - $1" ;;
    esac
}

D="${WORK}/data"

# --------------------------------------------------------------- the cases ---

echo "# managed mode, on an AIS-catcher that has it"
AIS_CATCHER_HELP="	[-E [config file] [bind address:port] - managed mode]"
run_case '{"mode":"managed","managed_sidebar":"web_viewer","log_level":"info","udp_targets":[]}'
check "starts AIS-catcher" "AIS-catcher" "${CMD}"
check "runs the dashboard and nothing else" \
    "-E ${D}/config.json 0.0.0.0:8118" "${ARGV}"
# Never the dashboard: it fetches /api/... with a leading slash, which under the
# ingress path prefix the browser sends to Home Assistant instead of here.
check "ingress points at the managed web viewer" \
    "proxy_pass http://127.0.0.1:8119;" "$(cat "${WORK}/nginx/upstream.conf")"
contains "the first start mentions the password" "set a password" "${LOG}"
contains "and says where the dashboard is" "port 8118 of this host" "${LOG}"

echo
echo "# managed mode, with the dashboard in the sidebar"
run_case '{"mode":"managed","managed_sidebar":"dashboard","log_level":"info","udp_targets":[]}'
contains "ingress points at the managed dashboard" \
    "proxy_pass http://127.0.0.1:8118;" "$(cat "${WORK}/nginx/upstream.conf")"
contains "root-relative dashboard APIs are made ingress-relative" \
    "sub_filter \"'/api/\" \"'api/\";" "$(cat "${WORK}/nginx/upstream.conf")"
contains "dashboard selection is logged" \
    "sidebar panel shows the management dashboard" "${LOG}"

echo
echo "# managed mode, on an AIS-catcher that does not"
# v0.70 and older: -E is an obsolete alias for the NMEA2000 output, so asking
# for managed mode there fails with a message about -I and nothing else.
AIS_CATCHER_HELP="	[-I [interface] - push messages as NMEA2000 data]"
run_case '{"mode":"managed","managed_sidebar":"web_viewer","log_level":"info","udp_targets":[]}'
check "refuses to start it" "" "${ARGV}"
contains "and says what to do instead" "does not have managed mode" "${LOG}"
contains "naming the option to change" "Set mode to manual" "${LOG}"
AIS_CATCHER_HELP=""

echo
echo "# manual mode, nothing configured"
run_case '{"mode":"manual","log_level":"info","udp_targets":[]}'
check "web viewer on, console quiet, sharing off" \
    "-N 8100 file ${D}/stat.bin backup 10 -X off -q -v 60" "${ARGV}"
check "ingress points at the web viewer" \
    "proxy_pass http://127.0.0.1:8100;" "$(cat "${WORK}/nginx/upstream.conf")"

echo
echo "# manual mode, everything configured"
run_case '{
  "mode": "manual", "log_level": "debug",
  "device_index": 0,
  "tuner_gain": "auto", "sample_rate": "1536K", "freq_correction": -2,
  "rtlagc": true, "biastee": false,
  "station_name": "Yokohama", "latitude": 35.44, "longitude": 139.64,
  "share_location": true, "web_plugins": true, "sharing_key": "s3cr3t",
  "udp_targets": [{"host": "192.168.1.20", "port": 10110},
                  {"host": "opencpn.local", "port": 10111}],
  "extra_args": "-a 192K"
}'
check "every option lands in the right place" \
    "-d:0 -gr tuner auto sample_rate 1536K freqoffset -2 rtlagc on biastee off\
 -N 8100 file ${D}/stat.bin backup 10 station Yokohama lat 35.44 lon 139.64\
 share_loc on plugin_dir ${WORK}/plugins -X s3cr3t\
 -u 192.168.1.20 10110 -u opencpn.local 10111 -v 10 -a 192K" \
    "${ARGV}"
excludes "the sharing key stays out of the log" "s3cr3t" "${LOG}"
contains "which still logs the command line" "<sharing key>" "${LOG}"

echo
echo "# sharing is never turned on by saying nothing"
run_case '{"mode":"manual","log_level":"info"}'
contains "off by default" "-X off" "${ARGV}"

run_case '{"mode":"manual","log_level":"info","share_community":true}'
contains "on when asked for" "-X on" "${ARGV}"
excludes "and not off as well" "-X off" "${ARGV}"

run_case '{"mode":"manual","log_level":"info","share_community":false,"sharing_key":"s3cr3t"}'
contains "a key turns it on by itself" "-X s3cr3t" "${ARGV}"

echo
echo "# a serial number is not a device index"
run_case '{"mode":"manual","log_level":"info","device_serial":"00000001"}'
contains "passed as an argument" "-d 00000001 " "${ARGV} "
excludes "and not as an index" "-d:00000001" "${ARGV}"

run_case '{"mode":"manual","log_level":"info","device_serial":"AISRX","device_index":1}'
contains "the serial number wins over the index" "-d AISRX " "${ARGV} "
contains "and says so" "using the serial number" "${LOG}"

echo
echo "# half-configured options are dropped, not half-applied"
run_case '{"mode":"manual","log_level":"info","latitude":35.44}'
excludes "a latitude without a longitude is dropped" " lat " "${ARGV}"
contains "and is reported" "only work as a pair" "${LOG}"

run_case '{"mode":"manual","log_level":"info","web_plugins":true}' "${WORK}/nowhere"
excludes "a missing plugin directory is not passed on" "plugin_dir" "${ARGV}"
contains "and is reported" "the web_plugins option is ignored" "${LOG}"

echo
if [ "${FAILURES}" -eq 0 ]; then
    echo "all checks passed"
else
    echo "${FAILURES} check(s) failed"
fi
exit "${FAILURES}"
