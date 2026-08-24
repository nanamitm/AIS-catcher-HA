#!/usr/bin/with-contenv bashio
set -e

CONTROL_URL="$(bashio::config 'url')"
CONTROL_URL="${CONTROL_URL%/}"
VERIFY_SSL="$(bashio::config 'verify_ssl' 'true')"
NGINX_CONF_DIR="${NGINX_CONF_DIR:-/etc/nginx}"

RESOLVER="$(awk '/^nameserver/ { print $2; exit }' /etc/resolv.conf 2>/dev/null)"

{
    if [ -n "${RESOLVER}" ]; then
        echo "resolver ${RESOLVER} valid=30s;"
        echo "set \$control_upstream \"${CONTROL_URL}\";"
        echo 'proxy_pass $control_upstream$request_uri;'
    else
        echo "proxy_pass ${CONTROL_URL}/;"
    fi

    case "${CONTROL_URL}" in
        https://*)
            echo "proxy_ssl_server_name on;"
            if [ "${VERIFY_SSL}" = "true" ]; then
                echo "proxy_ssl_verify on;"
                echo "proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;"
            fi
            ;;
    esac
} > "${NGINX_CONF_DIR}/upstream.conf"

if [ -z "${RESOLVER}" ]; then
    bashio::log.warning "No nameserver found; the proxy will keep the control host address it starts with."
fi

mkdir -p /tmp/nginx_client_body /tmp/nginx_proxy
chmod 777 /tmp/nginx_client_body /tmp/nginx_proxy

if NGINX_CHECK="$(nginx -t 2>&1)"; then
    bashio::log.info "AIS-catcher-control ${CONTROL_URL} is available through the sidebar."
    bashio::log.info "The remote control password is still required; Home Assistant ingress does not bypass it."
else
    bashio::log.fatal "Could not start the AIS-catcher-control ingress proxy."
    bashio::log.fatal "${NGINX_CHECK}"
    bashio::exit.nok
fi

exec nginx -g "daemon off;"
