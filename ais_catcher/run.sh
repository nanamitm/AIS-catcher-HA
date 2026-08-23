#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
set -e

# The web viewer port is fixed inside the container.  config.yaml maps it to the
# host, and only the host side of a port mapping can be changed in the add-on's
# Network panel -- making the container side configurable as well would let the
# two drift apart and leave the mapped port pointing at nothing.
WEB_PORT=8100

# Managed mode serves its dashboard here.  Nothing outside this container talks
# to it: nginx proxies it to the ingress panel.  See nginx.conf for why.
DASHBOARD_PORT=8118

# These three are what the add-on really uses; they are only overridable so that
# tests/test_run_args.sh can run this script outside the container, against a
# fixture instead of the add-on's volume.
DATA_DIR="${DATA_DIR:-/data}"
NGINX_CONF_DIR="${NGINX_CONF_DIR:-/etc/nginx}"
PLUGIN_DIR="${PLUGIN_DIR:-/etc/AIS-catcher/plugins/src/plugins}"

MODE="$(bashio::config 'mode')"

# ---------------------------------------------------------------- ingress ----

if [ "${MODE}" = "managed" ]; then
    UPSTREAM_PORT="${DASHBOARD_PORT}"
else
    UPSTREAM_PORT="${WEB_PORT}"
fi
echo "proxy_pass http://127.0.0.1:${UPSTREAM_PORT};" > "${NGINX_CONF_DIR}/upstream.conf"

# nginx workers drop to an unprivileged user, so its scratch space has to be
# writable by them.
mkdir -p /tmp/nginx_client_body /tmp/nginx_proxy
chmod 777 /tmp/nginx_client_body /tmp/nginx_proxy
if NGINX_CHECK="$(nginx -t 2>&1)" && nginx; then
    bashio::log.info "Sidebar panel ready."
else
    # A broken panel must not stop the receiver -- it is still decoding and
    # still feeding whatever it was configured to feed.  But the reason has to
    # reach the log; DOCS.md sends people here to find out why the panel is
    # empty.
    bashio::log.warning "Could not start the ingress proxy; the sidebar panel will be empty."
    bashio::log.warning "${NGINX_CHECK}"
fi

# ----------------------------------------------------------- managed mode ----

if [ "${MODE}" = "managed" ]; then
    # Managed mode is newer than the AIS-catcher release this add-on pins, and
    # in that release -E means something else entirely -- an obsolete alias for
    # the NMEA2000 output -- so it fails with a message about -I that has
    # nothing to do with what was asked for.  Ask the binary what it supports
    # instead of assuming, so bumping AIS_CATCHER_VERSION is all it takes.
    if ! AIS-catcher -h 2>&1 | grep -q -- '-E \[config file\]'; then
        bashio::log.fatal "This AIS-catcher does not have managed mode."
        bashio::log.fatal "Set mode to manual, or build the add-on against a newer"
        bashio::log.fatal "AIS-catcher by raising AIS_CATCHER_VERSION in build.yaml."
        bashio::exit.nok
    fi

    bashio::log.info "Managed mode. Configure the station from the sidebar panel."
    if [ ! -f "${DATA_DIR}/config.json" ]; then
        bashio::log.info "First start: the panel opens the setup wizard."
    fi
    bashio::log.info "Give the station a web viewer output on port ${WEB_PORT} to reach"
    bashio::log.info "it from the network and to feed the Statistics add-on."

    # Supplying any other option puts AIS-catcher back into manual mode and the
    # dashboard is never started, so -E has to stand alone here.
    exec AIS-catcher -E "${DATA_DIR}/config.json" "127.0.0.1:${DASHBOARD_PORT}"
fi

# ------------------------------------------------------------ manual mode ----

ARGS=()

# Two options rather than one that guesses: RTL-SDR serial numbers are often
# "00000001", which is indistinguishable from a device index unless the user
# says which one they meant.  The index belongs to the switch itself (-d:0), a
# serial number is a separate argument (-d 00000001).
if bashio::config.has_value 'device_serial'; then
    ARGS+=( -d "$(bashio::config 'device_serial')" )
    if bashio::config.has_value 'device_index'; then
        bashio::log.warning "Both device_serial and device_index are set; using the serial number."
    fi
elif bashio::config.has_value 'device_index'; then
    ARGS+=( "-d:$(bashio::config 'device_index')" )
fi

# Device settings are "name value" pairs after -gr.  Booleans reach AIS-catcher
# as on/off; bashio prints true/false, so they cannot be passed straight
# through.
GR=()
gr_value() {
    if bashio::config.has_value "$1"; then
        GR+=( "$2" "$(bashio::config "$1")" )
    fi
}
gr_bool() {
    if bashio::config.has_value "$1"; then
        if bashio::config.true "$1"; then
            GR+=( "$2" on )
        else
            GR+=( "$2" off )
        fi
    fi
}
gr_value 'tuner_gain' tuner
gr_value 'sample_rate' sample_rate
gr_value 'freq_correction' freqoffset
gr_bool 'rtlagc' rtlagc
gr_bool 'biastee' biastee
if [ ${#GR[@]} -gt 0 ]; then
    ARGS+=( -gr "${GR[@]}" )
fi

# The web viewer is not optional in manual mode: it is the sidebar panel, and it
# is the endpoint the Statistics add-on polls.  `file`/`backup` keep the plots
# across a restart -- DATA_DIR is the add-on's persistent volume, and five
# minutes is the shortest backup interval AIS-catcher accepts.
ARGS+=( -N "${WEB_PORT}" file "${DATA_DIR}/stat.bin" backup 10 )

if bashio::config.has_value 'station_name'; then
    ARGS+=( station "$(bashio::config 'station_name')" )
fi
if bashio::config.has_value 'latitude' && bashio::config.has_value 'longitude'; then
    ARGS+=( lat "$(bashio::config 'latitude')" lon "$(bashio::config 'longitude')" )
    # Without share_loc the viewer is given the position but will not show it,
    # and distances and the range plot stay empty.
    if bashio::config.true 'share_location'; then
        ARGS+=( share_loc on )
    fi
elif bashio::config.has_value 'latitude' || bashio::config.has_value 'longitude'; then
    bashio::log.warning "Latitude and longitude only work as a pair; ignoring the one that is set."
fi

# The plugins that ship with the package (aggregator lookups, extra map layers).
# Pointing plugin_dir at a directory that is not there stops AIS-catcher, so the
# path from the .deb is checked rather than trusted.
if bashio::config.true 'web_plugins'; then
    if [ -d "${PLUGIN_DIR}" ]; then
        ARGS+=( plugin_dir "${PLUGIN_DIR}" )
    else
        bashio::log.warning "No plugins in ${PLUGIN_DIR}; the web_plugins option is ignored."
    fi
fi

# AIS-catcher shares reception with the aiscatcher.org community feed unless
# told otherwise, and connects the moment it starts.  Sharing is a fine thing to
# do, but an add-on must not opt its user into uploading anything by saying
# nothing, so this is explicit in both directions.
if bashio::config.has_value 'sharing_key'; then
    ARGS+=( -X "$(bashio::config 'sharing_key')" )
elif bashio::config.true 'share_community'; then
    ARGS+=( -X on )
else
    ARGS+=( -X off )
fi

# A list of objects, which bashio::config cannot return: for a list option it
# prints the elements, so a single entry arrives as a bare object.  The raw
# options file keeps the array intact.
while IFS=$'\t' read -r UDP_HOST UDP_PORT; do
    if [ -n "${UDP_HOST}" ] && [ -n "${UDP_PORT}" ]; then
        ARGS+=( -u "${UDP_HOST}" "${UDP_PORT}" )
    fi
done < <(jq -r '(.udp_targets // [])[] | [.host, (.port | tostring)] | @tsv' \
             "${DATA_DIR}/options.json" 2>/dev/null || true)

# NMEA on the console is a wall of text at any real message rate, so it is
# suppressed unless the log level asks for it.  -v prints the periodic
# statistics that make the log useful either way.
if [ "$(bashio::config 'log_level')" = "debug" ]; then
    ARGS+=( -v 10 )
else
    ARGS+=( -q -v 60 )
fi

# The escape hatch.  AIS-catcher has far more options than are worth writing
# into the schema, and this is what keeps an unmapped one from being a reason to
# stop using the add-on.  Split on whitespace only -- quoting is not supported.
if bashio::config.has_value 'extra_args'; then
    read -r -a EXTRA_ARGS <<< "$(bashio::config 'extra_args')"
    ARGS+=( "${EXTRA_ARGS[@]}" )
fi

# The command line is logged because it is the fastest way to see what the
# options turned into -- but the sharing key is a credential, and the add-on log
# is what people paste into issues.
LOG_LINE="${ARGS[*]}"
if bashio::config.has_value 'sharing_key'; then
    LOG_LINE="${LOG_LINE//$(bashio::config 'sharing_key')/<sharing key>}"
fi
bashio::log.info "Manual mode: AIS-catcher ${LOG_LINE}"

exec AIS-catcher "${ARGS[@]}"
