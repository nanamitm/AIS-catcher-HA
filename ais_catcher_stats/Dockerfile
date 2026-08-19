ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 PYTHONUNBUFFERED=1

RUN pip3 install --no-cache-dir "requests>=2.31" "paho-mqtt>=1.6"

COPY run.sh bridge.py sensors.py /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
