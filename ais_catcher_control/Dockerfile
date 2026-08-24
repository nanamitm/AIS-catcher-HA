ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache nginx

COPY run.sh /
COPY nginx.conf /etc/nginx/nginx.conf
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]

