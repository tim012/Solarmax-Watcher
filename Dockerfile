##
# Dockerfile for SolarMax Watcher
#
# expose at least /opt/solarmax/log and /opt/solarmax/etc
#
## 

# build container
FROM alpine:latest AS build
RUN apk add --no-cache mariadb-client mariadb-connector-c-dev mosquitto-dev
RUN apk add --no-cache --virtual buildonlypkgs gcc alpine-sdk
COPY logger-src/* /opt/solarmax/src/
RUN cd /opt/solarmax/src; gcc -W -Wall -Wextra -Wshadow -Wlong-long -Wformat -Wpointer-arith -rdynamic -pedantic-errors -std=c99 -o smw-logger smw-logger.c -lmysqlclient -lmosquitto -pthread

# runtime container
FROM alpine:latest
RUN apk add --no-cache mariadb-client mariadb-connector-c-dev mosquitto-libs
RUN adduser -D -h /home/solar solar
RUN mkdir -p /opt/solarmax/log /opt/solarmax/bin /opt/solarmax/etc
COPY example-config/smw-logger.conf /opt/solarmax/etc
COPY --from=build /opt/solarmax/src/smw-logger /opt/solarmax/bin/
RUN chown solar /opt/solarmax/log
USER solar
WORKDIR /home/solar
CMD /opt/solarmax/bin/smw-logger /opt/solarmax/etc/smw-logger.conf
