ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 PYTHONUNBUFFERED=1

RUN apk add --no-cache nginx \
    && pip3 install --no-cache-dir "requests>=2.31" "paho-mqtt>=1.6"

COPY run.sh bridge.py sensors.py /
COPY nginx.conf /etc/nginx/nginx.conf
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
