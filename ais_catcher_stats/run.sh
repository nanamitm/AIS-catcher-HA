#!/usr/bin/with-contenv bashio
set -e

export AIS_URL="$(bashio::config 'url')"
export SCAN_INTERVAL="$(bashio::config 'scan_interval')"
export DEVICE_NAME="$(bashio::config 'device_name')"
export DEVICE_ID="$(bashio::config 'device_id')"
export MESSAGE_TYPE_SENSORS="$(bashio::config 'message_type_sensors')"
export REMOVE_ON_STOP="$(bashio::config 'remove_entities_on_stop')"
export LOG_LEVEL="$(bashio::config 'log_level')"
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

bashio::log.info "Polling ${AIS_URL} every ${SCAN_INTERVAL}s -> MQTT ${MQTT_HOST}:${MQTT_PORT}"
exec python3 /bridge.py
