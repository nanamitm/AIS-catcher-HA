#!/usr/bin/with-contenv bashio
set -e

AIS_URL="$(bashio::config 'url')"
AIS_URL="${AIS_URL%/}"
export AIS_URL
export SCAN_INTERVAL="$(bashio::config 'scan_interval')"
export DEVICE_NAME="$(bashio::config 'device_name')"
export DEVICE_ID="$(bashio::config 'device_id')"
export MESSAGE_TYPE_SENSORS="$(bashio::config 'message_type_sensors')"
export REMOVE_ON_STOP="$(bashio::config 'remove_entities_on_stop')"
export LOG_LEVEL="$(bashio::config 'log_level')"
export VESSEL_TIMEOUT="$(bashio::config 'vessel_timeout' '30')"
export FLEET_SENSORS="$(bashio::config 'fleet_sensors' 'true')"
export NEARBY_RADIUS="$(bashio::config 'nearby_radius' '5')"

# A list of objects, which bridge.py parses as JSON.  `bashio::config` cannot
# return it: for a list option it prints the *elements*, so a single vessel
# arrives as a bare object and jq counts its keys instead of the entries.
# The raw options file keeps the array intact.
# `|| true` keeps `set -e` from killing the script when jq or the options file
# is not there -- the point of the check below is to fall back to an empty list.
VESSELS="$(jq -c '.vessels // []' /data/options.json 2>/dev/null || true)"
if [ -z "${VESSELS}" ] || [ "${VESSELS}" = "null" ]; then
    VESSELS="[]"
fi
export VESSELS
export DISCOVERY_PREFIX="$(bashio::config 'discovery_prefix' 'homeassistant')"
export HTTP_USERNAME="$(bashio::config 'http_username' '')"
export HTTP_PASSWORD="$(bashio::config 'http_password' '')"
export VERIFY_SSL="$(bashio::config 'verify_ssl' 'true')"

if bashio::config.has_value 'mqtt_host'; then
    bashio::log.info "Using the MQTT broker from the add-on options."
    export MQTT_HOST="$(bashio::config 'mqtt_host')"
    export MQTT_PORT="$(bashio::config 'mqtt_port' '1883')"
    export MQTT_USER="$(bashio::config 'mqtt_user' '')"
    export MQTT_PASS="$(bashio::config 'mqtt_password' '')"
else
    if ! bashio::services.available 'mqtt'; then
        bashio::log.fatal "No MQTT service found. Install the Mosquitto broker add-on,"
        bashio::log.fatal "or set mqtt_host/mqtt_port/mqtt_user/mqtt_password in the options."
        bashio::exit.nok
    fi
    bashio::log.info "Using the MQTT broker provided by the Supervisor."
    export MQTT_HOST="$(bashio::services mqtt 'host')"
    export MQTT_PORT="$(bashio::services mqtt 'port')"
    export MQTT_USER="$(bashio::services mqtt 'username')"
    export MQTT_PASS="$(bashio::services mqtt 'password')"
fi

# The ingress panel: nginx proxies the AIS-catcher web UI so it shows up in the
# Home Assistant sidebar.  Only the upstream and its credentials vary, so they
# go in a snippet that /etc/nginx/nginx.conf includes.
#
# A host name written straight into proxy_pass is resolved once, when nginx
# starts, and cached for the life of the process.  A receiver on DHCP or mDNS
# that changes address then leaves the panel on 502 for good while the
# statistics keep working, with nothing in the log to say why.  Going through a
# variable makes nginx resolve per request, which needs an explicit resolver --
# the container's own, so it keeps resolving whatever it resolves today.
RESOLVER="$(awk '/^nameserver/ { print $2; exit }' /etc/resolv.conf 2>/dev/null)"
{
    if [ -n "${RESOLVER}" ]; then
        echo "resolver ${RESOLVER} valid=30s;"
        echo "set \$ais_upstream \"${AIS_URL}\";"
        # With a variable nginx no longer appends the location's URI, so the
        # request path has to be passed on explicitly.
        echo 'proxy_pass $ais_upstream$request_uri;'
    else
        echo "proxy_pass ${AIS_URL}/;"
    fi
    case "${AIS_URL}" in
        https://*)
            echo "proxy_ssl_server_name on;"
            # nginx does not verify an upstream certificate unless told to, which
            # is what a self-signed receiver needs.
            if ! bashio::config.has_value 'verify_ssl' || bashio::config.true 'verify_ssl'; then
                echo "proxy_ssl_verify on;"
                echo "proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;"
            fi
            ;;
    esac
    if bashio::config.has_value 'http_username'; then
        # busybox base64 has no -w, so the newline is stripped separately
        CREDENTIALS="$(printf '%s:%s' "${HTTP_USERNAME}" "${HTTP_PASSWORD}" | base64 | tr -d '\n')"
        echo "proxy_set_header Authorization \"Basic ${CREDENTIALS}\";"
    fi
} > /etc/nginx/upstream.conf

if [ -z "${RESOLVER}" ]; then
    bashio::log.warning "No nameserver found; the web UI proxy will keep the receiver address it starts with."
fi

# nginx workers drop to an unprivileged user, so its scratch space has to be
# writable by them.
mkdir -p /tmp/nginx_client_body /tmp/nginx_proxy
chmod 777 /tmp/nginx_client_body /tmp/nginx_proxy
if NGINX_CHECK="$(nginx -t 2>&1)" && nginx; then
    bashio::log.info "Web UI proxied to the sidebar panel."
else
    # A broken panel must not take the statistics down with it, but the reason
    # has to reach the log -- DOCS.md sends people here to find out why the
    # panel is empty.
    bashio::log.warning "Could not start the web UI proxy; the sidebar panel will be empty."
    bashio::log.warning "${NGINX_CHECK}"
fi

bashio::log.info "Polling ${AIS_URL} every ${SCAN_INTERVAL}s -> MQTT ${MQTT_HOST}:${MQTT_PORT}"
bashio::log.info "Tracking $(echo "${VESSELS}" | jq -r 'length' 2>/dev/null || echo '?') vessel(s)"
exec python3 /bridge.py
