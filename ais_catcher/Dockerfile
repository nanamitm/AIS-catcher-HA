ARG BUILD_FROM
FROM ${BUILD_FROM}

ARG BUILD_ARCH
ARG AIS_CATCHER_VERSION

ENV LANG=C.UTF-8

# The release .deb rather than a source build.  Compiling AIS-catcher on the
# user's own machine -- which is what happens here, the add-on ships no prebuilt
# image -- takes many minutes on a Raspberry Pi and pulls in a compiler
# toolchain that is then dead weight in the image.  The package also carries
# librtlsdr and libhydrasdr in /usr/lib/ais-catcher, built with
# DETACH_KERNEL_DRIVER=ON, which is what lets it take a dongle away from the
# kernel's DVB driver; the rest of its dependencies are stock bookworm.
#
# `apt-get install ./x.deb` and not `dpkg -i`: dpkg does not resolve depends.
#
# The ldd check at the end is not ceremony: a missing shared library shows up
# only when the add-on is started, as an add-on that dies immediately with
# nothing in its log.  Failing the build says which library instead.
RUN set -eux; \
    case "${BUILD_ARCH}" in \
        amd64)   DEB_ARCH="amd64" ;; \
        aarch64) DEB_ARCH="arm64" ;; \
        *) echo "unsupported architecture: ${BUILD_ARCH}" >&2; exit 1 ;; \
    esac; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl nginx; \
    curl -fsSL -o /tmp/ais-catcher.deb \
        "https://github.com/jvde-github/AIS-catcher/releases/download/${AIS_CATCHER_VERSION}/ais-catcher_debian_bookworm_${DEB_ARCH}.deb"; \
    apt-get install -y --no-install-recommends /tmp/ais-catcher.deb; \
    rm -f /tmp/ais-catcher.deb; \
    rm -rf /var/lib/apt/lists/*; \
    if ldd /usr/bin/AIS-catcher | grep -q 'not found'; then \
        ldd /usr/bin/AIS-catcher >&2; \
        exit 1; \
    fi

COPY run.sh /
COPY nginx.conf /etc/nginx/nginx.conf
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
