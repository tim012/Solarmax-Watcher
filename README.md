Solarmax Watcher
================

Logger for SolarMax photovoltaic inverters (MT series) with output to InfluxDB,
MQTT and MySQL, plus Grafana dashboards and the classic PHP web pages.

Forked from the [Solarmax Watcher](http://sourceforge.net/projects/solarmaxwatcher/)
project.


Features
--------

* `smw-logger` reads the values of the inverter over ethernet (MaxTalk
  protocol), up to three DC strings
* **InfluxDB v2** output, the base for the Grafana dashboards
* **MQTT** output, one topic per value, e.g. for evcc or home automation
* **MySQL/MariaDB** output, the base for the PHP web pages
* every output is optional, any combination works
* Grafana dashboards for day, month and year, generated from a script
* Docker setup: logger, InfluxDB and Grafana behind Traefik


How it works
------------

```
                          every Logavginterval      every Loginterval
SolarMax inverter ──▶ smw-logger ──┬──▶ MQTT    ┌──▶ InfluxDB ──▶ Grafana
   (TCP 12345)                     └────────────┴──▶ MySQL    ──▶ PHP pages
```

The logger queries the inverter every `Logavginterval` seconds. Each sample is
published to MQTT right away. Power, voltage, current and temperature are
averaged over `Loginterval` seconds and then written to InfluxDB and/or MySQL;
the energy counters are taken from the last sample.

The **default setup is logger → InfluxDB → Grafana**. MySQL and MQTT are off
in the example configuration.


Repository layout
-----------------

| Path                         | Content                                                  |
|------------------------------|----------------------------------------------------------|
| `logger/`                    | `smw-logger.c`, Dockerfile, `smw-logger.conf.example`    |
| `grafana/`                   | dashboards, their generator script and provisioning      |
| `web/`                       | PHP web pages for the MySQL data, Dockerfile             |
| `db/create_db.sh`            | creates the MySQL database, user and table               |
| `docker-compose.example.yml` | complete stack, MariaDB and web pages commented out      |
| `.env.example`               | secrets for InfluxDB and Grafana                         |


Quick start with Docker
-----------------------

Requirements: Docker with Compose, and Traefik on an external network
`backend` for Grafana (or remove the Traefik labels and publish port 3000).

1. **Compose file and secrets**

       cp docker-compose.example.yml docker-compose.yml
       cp .env.example .env

   Replace all `<<DEFINE>>` in `docker-compose.yml` with host paths for the
   volumes, and set `grafana.example.com` to your domain. In `.env` set the
   passwords and a long random InfluxDB token. Both files are listed in
   `.gitignore`.

2. **Logger configuration**

   Copy `logger/smw-logger.conf.example` as `smw-logger.conf` into the host
   folder that is mounted to `/opt/solarmax/etc` and set at least:

   * `Hostname` / `Hostport` – address of the inverter
   * `INFLUXtoken` – the value of `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN` from `.env`

   `INFLUXurl=http://influxdb:8086`, `INFLUXorg=my-org` and
   `INFLUXbucket=solarmax` already match the compose file.

3. **Start**

       docker compose up -d --build

   InfluxDB creates the organization and the bucket on its first start. Errors
   of the logger end up in the mounted log folder (`solarmax-error.log`).

4. **Grafana data source**

   The dashboards are provisioned automatically, the data source is not. Log
   in to Grafana (user `admin`, password `GF_SECURITY_ADMIN_PASSWORD`) and add
   it once under *Connections → Data sources → Add data source → InfluxDB*:

   | Setting        | Value                                           |
   |----------------|-------------------------------------------------|
   | Query language | **Flux** (not InfluxQL)                         |
   | URL            | `http://influxdb:8086`                          |
   | Organization   | `my-org`                                        |
   | Token          | `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN` from `.env`  |
   | Default bucket | `solarmax`                                      |

   *Save & test* should report the bucket. The dashboards find the data source
   by its type, the name doesn't matter. If there is more than one InfluxDB
   data source, set `regex` in `DSVAR` in `grafana/build_dashboards.py`.

5. **Dashboards**

   The folder *SolarMax* contains *SolarMax – Tag*, *– Monat* and *– Jahr*. They
   are read-only in the UI; changes go through the generator script, see
   [Grafana dashboards](#grafana-dashboards).


Logger configuration
--------------------

All settings live in `smw-logger.conf`, see the comments in
`logger/smw-logger.conf.example`. At least one of `DBhost`, `MQTThost` and
`INFLUXurl` has to be set; an empty value switches that output off.

Required, there is no built-in default:

| Setting          | Example                              | Meaning                                  |
|------------------|--------------------------------------|------------------------------------------|
| `Loginterval`    | `120`                                | seconds between writes to InfluxDB/MySQL |
| `Logavginterval` | `30`                                 | seconds between queries of the inverter  |
| `Hostname`       | `192.168.178.35`                     | IP address or hostname of the inverter   |
| `Hostport`       | `12345`                              | TCP port of the inverter                 |
| `Errorfile`      | `/opt/solarmax/log/solarmax-error.log` | log file for errors                    |

Optional:

| Setting               | Default     | Meaning                                    |
|-----------------------|-------------|--------------------------------------------|
| `Debug`               | `0`         | `1` writes details to `Debugfile`          |
| `Debugfile`           |             | log file for debug output                  |
| `INFLUXurl`           | empty (off) | e.g. `http://influxdb:8086`                |
| `INFLUXorg`           |             | InfluxDB organization                      |
| `INFLUXbucket`        |             | InfluxDB bucket                            |
| `INFLUXtoken`         |             | API token with write access to the bucket  |
| `INFLUXmeasurement`   | `solarmax`  | measurement name                           |
| `MQTThost`            | empty (off) | IP address or hostname of the broker       |
| `MQTTport`            | `1883`      | port of the broker                         |
| `MQTTuser`/`MQTTpass` | empty       | leave empty for an anonymous broker        |
| `MQTTtopic`           | `solarmax`  | topic prefix                               |
| `MQTTqos`             | `0`         | QoS 0, 1 or 2                              |
| `MQTTretain`          | `1`         | publish retained                           |
| `Nightpower`          | `200`       | see [Inverter offline](#inverter-offline)  |
| `DBhost`              | empty (off) | MySQL host, e.g. `db`                      |
| `DBname`              |             | database, e.g. `solarmax`                  |
| `DBtable`             |             | table, e.g. `log10mt2`                     |
| `DBuser`/`DBpass`     |             | database user and password                 |


Data
----

All values are raw integers of the SolarMax protocol:

| InfluxDB / MySQL | MQTT topic                   | Meaning                  | Unit    |
|------------------|------------------------------|--------------------------|---------|
| `pac`            | `solarmax/pac`               | AC power                 | W       |
| `udc1`..`udc3`   | `solarmax/ud01`..`ud03`      | DC voltage string 1–3    | 0.1 V   |
| `idc1`..`idc3`   | `solarmax/id01`..`id03`      | DC current string 1–3    | 0.01 A  |
| `kdy`            | `solarmax/kdy`               | energy today             | 0.1 kWh |
| `kmt`            | `solarmax/kmt`               | energy this month        | kWh     |
| `kyr`            | `solarmax/kyr`               | energy this year         | kWh     |
| `kt0`            | `solarmax/kt0`               | energy total             | kWh     |
| `tkk`            | `solarmax/tkk`               | inverter temperature     | °C      |
| `sys`            | `solarmax/sys`               | operating state, e.g. 20008 = grid operation | code |

InfluxDB: measurement `solarmax` (`INFLUXmeasurement`), no tags, all fields as
integers, timestamps in seconds.

### Inverter offline

At night the inverter switches off and can't be reached. If the last sample
before that was below `Nightpower` watts (an orderly shutdown at dusk), the
logger publishes `pac=0` and the last `kt0` to MQTT every `Logavginterval`, so
consumers like evcc see a valid 0 W instead of an outdated value. After a
failure at higher power nothing is published, the inverter may still be
producing. Nothing of this is written to InfluxDB or MySQL.


Grafana dashboards
------------------

The JSON files in `grafana/dashboards/` are generated by
`grafana/build_dashboards.py` – don't edit them by hand. Adjust the script and
regenerate:

    cd grafana
    python3 build_dashboards.py

Things to adapt to your system:

* `TZ` – time zone for the day, month and year windows
* `ERW_TAG` / `ERW_MON` – expected yield per day and per month, e.g. from
  [PVGIS](https://re.jrc.ec.europa.eu/pvg_tools/)
* axis ranges, e.g. the kW axis (0–13) to the peak power of your system
* `JAHRE_Q` – first year of the year selection

Grafana reloads the files within 30 seconds (`grafana/provisioning.yaml`).
Design, Flux queries and known pitfalls are described in `grafana/CLAUDE.md`.


Optional: MySQL and PHP web pages
---------------------------------

The PHP pages in `web/` are the original visualisation of this project. They
read from MySQL, so the logger has to write there as well.

1. Uncomment the services `db` and `web` in `docker-compose.yml`.
2. Create database, user and table: set the variables at the top of
   `db/create_db.sh` and run it against the database.
3. In `smw-logger.conf` set `DBhost=db` and `DBname`, `DBtable`, `DBuser`,
   `DBpass`.
4. Adjust the web pages:
   * `solarertrag.php`, `analyzer.php`: host (`db`), user and password in
     `mysql_connect(...)`, table in `$table`, time zone in
     `date_default_timezone_set(...)`
   * `solarertrag_*_predictions.php`: expected yields for your location
   * `sitehead.php`: title, subtitle and links
   * `drawday.php`: `$maxpac` slightly above the peak power of your system
   * `solarertrag.php`: remuneration per kWh (search for `CHF`)
   * `colors.php`: graph colours; `img/header.jpg`: title image, 820 × 120 px
5. `img/` has to be writable by `www-data`, the graphs are rendered into it.

The page language follows the browser (de, en, nl, fr, es, it), English is the
fallback.


Manual installation of the logger
---------------------------------

Requirements: `libmysqlclient-dev`, `libmosquitto-dev`, `libcurl4-openssl-dev`
(or the equivalents of your distribution).

    cd logger
    gcc -W -Wall -Wextra -Wshadow -Wlong-long -Wformat -Wpointer-arith -rdynamic -pedantic-errors -std=c99 -o smw-logger smw-logger.c -lmysqlclient -lmosquitto -lcurl -pthread
    sudo cp smw-logger /usr/local/bin/
    sudo cp smw-logger.conf.example /usr/local/etc/smw-logger.conf

Edit `/usr/local/etc/smw-logger.conf` and start it with:

    /usr/local/bin/smw-logger /usr/local/etc/smw-logger.conf

The logger runs until it is stopped; start it with systemd, cron or similar.


Several inverters
-----------------

Connect the first inverter to the LAN and set it to ID 001. Connect the others
via RS485 in a row with ascending IDs (002, 003, …) and their LAN interface
disabled. For MySQL use one table per inverter. The PHP pages show the table
set in `$table` in `solarertrag.php`; the parameter `?wr=x` is read but doesn't
select a table.


Authors and license
-------------------

Licensed under the GNU General Public License v2 or later, see `LICENSE`.

The logger and the visualizer were written by zagibu in July 2010 (originally
under WTFPL 2), improved by Frank Lassowski in August/September 2010 and by
sleepprogger in January 2012. Adaption to the SolarMax MT3 series by Andreas
Lüthi. InfluxDB and MQTT output, Docker setup and Grafana dashboards were added
in this fork.

| Contributor       | Contact                  |
|-------------------|--------------------------|
| zagibu            | zagibu@gmx.ch            |
| Frank Lassowski   | flassowski@gmx.de        |
| Stephan Collet    | stephan@collet-online.de |
| Rene Essink       | supergudrun@web.de       |
| Thomas Kattenbeck | kattenbeck@gmx.de        |
| sleepprogger      | wwrStuff@gmx.de          |
| Andreas Lüthi     |                          |
