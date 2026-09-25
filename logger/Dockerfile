# build container
FROM alpine:latest AS build
RUN apk add --no-cache mariadb-client mariadb-connector-c-dev mosquitto-dev curl-dev
RUN apk add --no-cache --virtual buildonlypkgs gcc alpine-sdk
COPY smw-logger.c /opt/solarmax/src/
RUN cd /opt/solarmax/src; gcc -W -Wall -Wextra -Wshadow -Wlong-long -Wformat -Wpointer-arith -rdynamic -pedantic-errors -std=c99 -o smw-logger smw-logger.c -lmysqlclient -lmosquitto -lcurl -pthread

# runtime container
FROM alpine:latest
RUN apk add --no-cache mariadb-client mariadb-connector-c-dev mosquitto-libs libcurl ca-certificates
RUN adduser -D -h /home/solar solar
RUN mkdir -p /opt/solarmax/log /opt/solarmax/bin /opt/solarmax/etc
COPY smw-logger.conf.example /opt/solarmax/etc/smw-logger.conf
COPY --from=build /opt/solarmax/src/smw-logger /opt/solarmax/bin/
RUN chown solar /opt/solarmax/log
USER solar
WORKDIR /home/solar
CMD /opt/solarmax/bin/smw-logger /opt/solarmax/etc/smw-logger.conf