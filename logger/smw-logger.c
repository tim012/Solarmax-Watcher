/*
    Simple solarmax logger c program written by zagibu@gmx.ch in July 2010
    This program was originally licensed under WTFPL 2 http://sam.zoy.org/wtfpl/
    It is now licensed under GPLv2 or later http://www.gnu.org/licenses/gpl2.html

    You need the mysql client library files installed to be able to compile it.
    For the optional MQTT output you additionally need libmosquitto
    (Debian/Ubuntu: "apt install libmosquitto-dev"), for the optional InfluxDB
    output libcurl ("apt install libcurl4-openssl-dev").

    Compile with: gcc -W -Wall -Wextra -Wshadow -Wlong-long -Wformat -Wpointer-arith -rdynamic -pedantic-errors -std=c99 -o smw-logger smw-logger.c -lmysqlclient -lmosquitto -lcurl

    Run with: ./smw-logger /path/to/config-file

    Structure of the config-file:

    Debug=0
    Loginterval=60
    Waitinterval=200
    DBhost=localhost
    DBname=solarmax
    DBtable=log10mt2
    DBuser=solaruser
    DBpass=userpassword
    Hostname=192.168.178.35
    Hostport=12345

    The DB settings are optional, DB logging stays off as long as DBhost is
    missing. At least one of DBhost, MQTThost or INFLUXurl has to be set.

    Optional MQTT settings, MQTT stays off as long as MQTThost is missing:

    MQTThost=192.168.X.Y
    MQTTport=1883
    MQTTuser=
    MQTTpass=
    MQTTtopic=solarmax
    MQTTqos=0
    MQTTretain=1
    Nightpower=200

    Optional InfluxDB (v2) settings, off as long as INFLUXurl is missing:

    INFLUXurl=http://influxdb:8086
    INFLUXorg=my-org
    INFLUXbucket=solarmax
    INFLUXtoken=my-write-token
    INFLUXmeasurement=solarmax

    InfluxDB receives the same averaged values with the same field names as
    the database, at the same interval (Loginterval).

    Every single sample (Logavginterval) is published as one topic per value,
    e.g. solarmax/pac, solarmax/kdy, solarmax/ud01, ... The database still gets
    the averaged values every Loginterval.

    While the inverter is not reachable, solarmax/pac=0 and the last known
    solarmax/kt0 are published every Logavginterval, so consumers like evcc
    don't treat the values as outdated. Nothing of this goes to the database.

    This only happens if the last sample read before the failure was below
    Nightpower watts, which means the inverter shut down in an orderly way
    (dusk). After a failure at higher power something really went wrong, the
    inverter may well still be producing, so no values are published at all
    and consumers correctly report the meter as outdated.

   You can set DEBUG to 1 to get detailed output in a separate logfile.

   It is recommended to schedule the smw-logger to be started between 5:00 - 6:00 in the
   morning and stopped between 22:00 and 23:00 in the evening (compare with sunshine
   duration). The smw-logger has no built-in facility for logging, so use CRON or similar.

   Example CRON entries:
   00 05 * * * /usr/local/bin/smw-logger /usr/local/etc/smw-logger.conf
   00 23 * * * killall smw-logger

   Sources:
  - http://www.linuxhowtos.org/C_C++/socket.htm
  - http://wwwuser.gwdg.de/~kboehm/ebook/21_kap15_w6.html#49329
  - http://man.cx/setbuf%283%29
  - http://allfaq.org/forums/t/169895.aspx
  - http://dev.mysql.com/tech-resources/articles/mysql-capi-tutorial.html
  - https://mosquitto.org/api/files/mosquitto-h.html
*/

#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <strings.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netdb.h>
#include <mysql/mysql.h>
#include <mosquitto.h>
#include <curl/curl.h>
#include <regex.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <pthread.h>

static  FILE*   error_file = NULL;
static  char    error_file_name[512];

static  FILE*   debug_file = NULL;
static  char    debug_file_name[512];

static  FILE*   config_file = NULL;
static  char*   config_file_name;

static  int     sockfd, portno, n, log_interval, logavg_interval;
static  int     result, wait_interval, DEBUG;

static  int     failure_flag;
static  struct  sockaddr_in serv_addr;
static  struct  hostent* server;
static  char    dbhost[512];
static  char    dbname[512];
static  char    dbtable[512];
static  char    dbuser[512];
static  char    dbpass[512];
static  char    hostaddr[512];
static  char    line[512];
static  char*   message;

/* MQTT settings */
static  struct  mosquitto* mosq = NULL;
static  char    mqtt_host[512] = "";        // empty => MQTT disabled
static  int     mqtt_port      = 1883;
static  char    mqtt_user[512] = "";
static  char    mqtt_pass[512] = "";
static  char    mqtt_topic[256] = "solarmax";
static  int     mqtt_qos       = 0;
static  int     mqtt_retain    = 1;
static  int     night_power    = 200;       // see Nightpower in the config file

/* InfluxDB settings */
static  CURL*   curl = NULL;
static  struct  curl_slist* influx_headers = NULL;
static  char    influx_url[512] = "";       // empty => InfluxDB disabled
static  char    influx_org[256] = "";
static  char    influx_bucket[256] = "";
static  char    influx_token[512] = "";
static  char    influx_measurement[256] = "solarmax";
static  char    influx_write_url[1280];

static  int     kdy;    // Energy today [Wh]  (KDY)
static  int     kmt;    // Energy this month [kWh] (KMT)
static  int     kyr;    // Energy this year [kWh] (KYR)
static  int     kt0;    // Energy total [kWh] (KT0)
static  int     tkk;    // Temperature power unit 1 TKK
static  int     pac;    // AC power [mW] (PAC)
static  int     ud01;   // DC voltage [mV] string 1
static  int     ud02;   // DC voltage [mV] string 2
static  int     ud03;   // DC voltage [mV] string 3
static  int     id01;   // DC current [mA] string 1
static  int     id02;   // DC current [mA] string 2
static  int     id03;   // DC current [mA] string 3
static  int     sys;    // Operating state

/* values of the sample that was just read, these go out via MQTT */
static  int     cur_kdy, cur_kmt, cur_kyr, cur_kt0, cur_tkk, cur_pac;
static  int     cur_ud01, cur_ud02, cur_ud03, cur_id01, cur_id02, cur_id03, cur_sys;
static  int     have_counters = 0;  // 1 as soon as one sample was read successfully

static  char*   expression = "...=([0-9A-F]*);...=([0-9A-F]*);...=([0-9A-F]*);...=([0-9A-F]*);...=([0-9A-F]*);...=([0-9A-F]*);....=([0-9A-F]*);....=([0-9A-F]*);....=([0-9A-F]*);....=([0-9A-F]*);....=([0-9A-F]*);....=([0-9A-F]*);...=([0-9A-F]*)";
static  char    buffer[512], buffer2[512];
static  char    query[512];
static  regex_t rx;
static  regmatch_t* matches;
static  MYSQL*  connection = NULL;

static void mqtt_stop(void);
static void influx_stop(void);

static void error_exit(const char* msg) {
    perror(msg);
    mqtt_stop();
    influx_stop();
    if (error_file != NULL) fclose(error_file);
    if (debug_file != NULL) fclose(debug_file);
    exit(0);
}

static void error_retry(char* msg) {
    time_t timestamp = time(NULL);
    char error_msg[512];
    char *time_now = ctime(&timestamp);
    time_now[strlen(time_now)-1]=0;
    if (error_file == NULL) error_exit("ERROR writing to error.log file");
    sprintf(error_msg, "%s %s", time_now, msg);
    fprintf(error_file, "%s\n", error_msg);
}

static void debug_entry(char* msg) {
    time_t timestamp = time(NULL);
    char debug_msg[512];
    char *time_now = ctime(&timestamp);
    if (debug_file != NULL) {;
      time_now[strlen(time_now)-1]=0;
      sprintf(debug_msg, "%s %s", time_now, msg);
      fprintf(debug_file, "%s\n", debug_msg);
    } // if
    else {
      error_retry("ERROR writing to debug.log file");
    } // else
}

static void set_nonblock(int sock) {
    int flags;
    flags = fcntl(sock,F_GETFL,0);
    if (flags == -1) error_exit("ERROR no valid flags on socket");
    fcntl(sock, F_SETFL, flags | O_NONBLOCK);
}

/* =========================== MQTT functions =========================== */

/* Set up the mosquitto client. Does nothing if MQTThost is not configured. */
static int mqtt_start(void) {
    char msg[512];
    int rc;

    if (mqtt_host[0] == '\0') return 0;

    mosquitto_lib_init();

    mosq = mosquitto_new(NULL, true, NULL);
    if (mosq == NULL) {
        error_retry("ERROR can't create mosquitto client, continuing without MQTT");
        return -1;
    } // if

    if (mqtt_user[0] != '\0') {
        mosquitto_username_pw_set(mosq, mqtt_user, mqtt_pass[0] != '\0' ? mqtt_pass : NULL);
    } // if

    mosquitto_reconnect_delay_set(mosq, 2, 60, true);

    // connect_async() + loop_start(): the network thread does the (re)connecting,
    // so a broker that is down neither blocks nor kills the logger
    rc = mosquitto_connect_async(mosq, mqtt_host, mqtt_port, 60);
    if (rc != MOSQ_ERR_SUCCESS) {
        snprintf(msg, sizeof(msg), "MQTT connect to %s:%d failed: %s", mqtt_host, mqtt_port, mosquitto_strerror(rc));
        error_retry(msg);
    } // if

    rc = mosquitto_loop_start(mosq);
    if (rc != MOSQ_ERR_SUCCESS) {
        snprintf(msg, sizeof(msg), "ERROR can't start MQTT thread: %s", mosquitto_strerror(rc));
        error_retry(msg);
        mosquitto_destroy(mosq);
        mosq = NULL;
        mosquitto_lib_cleanup();
        return -1;
    } // if

    if (DEBUG) {
        snprintf(msg, sizeof(msg), "MQTT publishing to %s:%d, topic %s", mqtt_host, mqtt_port, mqtt_topic);
        debug_entry(msg);
    } // if (DEBUG)

    return 0;
} // mqtt_start

static void mqtt_stop(void) {
    if (mosq == NULL) return;

    mosquitto_disconnect(mosq);
    mosquitto_loop_stop(mosq, false);
    mosquitto_destroy(mosq);
    mosq = NULL;
    mosquitto_lib_cleanup();
} // mqtt_stop

static void mqtt_publish_value(const char* subtopic, int value) {
    char topic[600];
    char payload[32];
    char msg[700];
    int len, rc;

    if (mosq == NULL) return;

    snprintf(topic, sizeof(topic), "%s/%s", mqtt_topic, subtopic);
    len = snprintf(payload, sizeof(payload), "%d", value);

    rc = mosquitto_publish(mosq, NULL, topic, len, payload, mqtt_qos, mqtt_retain != 0);
    if (rc != MOSQ_ERR_SUCCESS && DEBUG) {
        snprintf(msg, sizeof(msg), "ERROR publishing %s: %s", topic, mosquitto_strerror(rc));
        debug_entry(msg);
    } // if
} // mqtt_publish_value

/* Publish the values of the sample that has just been read from the inverter. */
static void mqtt_publish_sample(void) {
    if (mosq == NULL) return;

    mqtt_publish_value("kdy",  cur_kdy);
    mqtt_publish_value("kmt",  cur_kmt);
    mqtt_publish_value("kyr",  cur_kyr);
    mqtt_publish_value("kt0",  cur_kt0);
    mqtt_publish_value("tkk",  cur_tkk);
    mqtt_publish_value("pac",  cur_pac);
    mqtt_publish_value("ud01", cur_ud01);
    mqtt_publish_value("ud02", cur_ud02);
    mqtt_publish_value("ud03", cur_ud03);
    mqtt_publish_value("id01", cur_id01);
    mqtt_publish_value("id02", cur_id02);
    mqtt_publish_value("id03", cur_id03);
    mqtt_publish_value("sys",  cur_sys);
} // mqtt_publish_sample

/* 0 W may only be published if the inverter shut down in an orderly way, which
   is the case when the last sample before the failure was below night_power.
   After a failure at higher power the inverter might still be producing and
   0 W would be a lie, so nothing is published at all. */
static int offline_is_night(void) {
    return (have_counters && cur_pac < night_power);
} // offline_is_night

/* Inverter not reachable: publish 0 W, so consumers don't see the values as
   outdated. The total counter is repeated unchanged (never 0, it must not go
   backwards). kdy/kmt/kyr are left out, they would be wrong after midnight. */
static void mqtt_publish_offline(void) {
    if (mosq == NULL) return;
    if (!offline_is_night()) return;

    mqtt_publish_value("pac", 0);
    mqtt_publish_value("kt0", cur_kt0);
} // mqtt_publish_offline

/* Replacement for sleep() while the inverter is not reachable:
   keeps publishing the offline values every logavg_interval seconds. */
static void wait_offline(int seconds) {
    int chunk;

    if (DEBUG && mosq != NULL) {
        char msg[512];
        if (offline_is_night()) {
            snprintf(msg, sizeof(msg), "Inverter not reachable, last sample was %d W, publishing 0 W via MQTT", cur_pac);
        } // if
        else if (have_counters) {
            snprintf(msg, sizeof(msg), "Inverter not reachable, last sample was %d W, publishing nothing", cur_pac);
        } // else if
        else {
            snprintf(msg, sizeof(msg), "Inverter not reachable, no sample read yet, publishing nothing");
        } // else
        debug_entry(msg);
    } // if (DEBUG)

    while (seconds > 0) {
        mqtt_publish_offline();
        chunk = (seconds < logavg_interval) ? seconds : logavg_interval;
        sleep(chunk);
        seconds -= chunk;
    } // while
} // wait_offline

/* ========================== InfluxDB functions ========================= */

/* Throw the response body away instead of printing it to stdout. */
static size_t influx_discard(void* ptr, size_t size, size_t nmemb, void* userdata) {
    (void) ptr;
    (void) userdata;
    return size * nmemb;
} // influx_discard

/* Set up the curl handle. Does nothing if INFLUXurl is not configured. */
static int influx_start(void) {
    char header[600];
    char* esc_org;
    char* esc_bucket;

    if (influx_url[0] == '\0') return 0;

    curl_global_init(CURL_GLOBAL_DEFAULT);

    curl = curl_easy_init();
    if (curl == NULL) {
        error_retry("ERROR can't create curl handle, continuing without InfluxDB");
        curl_global_cleanup();
        return -1;
    } // if

    esc_org    = curl_easy_escape(curl, influx_org, 0);
    esc_bucket = curl_easy_escape(curl, influx_bucket, 0);
    snprintf(influx_write_url, sizeof(influx_write_url), "%s/api/v2/write?org=%s&bucket=%s&precision=s",
             influx_url, esc_org != NULL ? esc_org : influx_org,
             esc_bucket != NULL ? esc_bucket : influx_bucket);
    curl_free(esc_org);
    curl_free(esc_bucket);

    snprintf(header, sizeof(header), "Authorization: Token %s", influx_token);
    influx_headers = curl_slist_append(influx_headers, header);
    influx_headers = curl_slist_append(influx_headers, "Content-Type: text/plain; charset=utf-8");

    curl_easy_setopt(curl, CURLOPT_URL, influx_write_url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, influx_headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, influx_discard);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 10L);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 5L);

    if (DEBUG) {
        char msg[1400];
        snprintf(msg, sizeof(msg), "InfluxDB writing to %s", influx_write_url);
        debug_entry(msg);
    } // if (DEBUG)

    return 0;
} // influx_start

static void influx_stop(void) {
    if (curl == NULL) return;

    curl_easy_cleanup(curl);
    curl = NULL;
    curl_slist_free_all(influx_headers);
    influx_headers = NULL;
    curl_global_cleanup();
} // influx_stop

/* Write the averaged values to InfluxDB, same values and names as the db row.
   A failure is logged and otherwise ignored, the logger keeps running. */
static void influx_write(void) {
    char body[768];
    char msg[900];
    long http_code = 0;
    CURLcode rc;

    if (curl == NULL) return;

    snprintf(body, sizeof(body),
             "%s kdy=%di,kmt=%di,kyr=%di,kt0=%di,tkk=%di,pac=%di,"
             "udc1=%di,udc2=%di,udc3=%di,idc1=%di,idc2=%di,idc3=%di,sys=%di %ld",
             influx_measurement, kdy, kmt, kyr, kt0, tkk, pac,
             ud01, ud02, ud03, id01, id02, id03, sys, (long) time(NULL));

    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body);

    if (DEBUG) {
        snprintf(msg, sizeof(msg), "Writing to InfluxDB: %s", body);
        debug_entry(msg);
    } // if (DEBUG)

    rc = curl_easy_perform(curl);
    if (rc != CURLE_OK) {
        snprintf(msg, sizeof(msg), "ERROR writing to InfluxDB: %s", curl_easy_strerror(rc));
        error_retry(msg);
        return;
    } // if

    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
    if (http_code != 204) {
        snprintf(msg, sizeof(msg), "ERROR writing to InfluxDB: HTTP %ld", http_code);
        error_retry(msg);
    } // if
} // influx_write

/* ====================================================================== */

int main(int argc, char *argv[]) {
    int     avgCount;

    // Check commandline arguments
    if (argc < 2) error_exit("ERROR program needs config-file as parameter");

    //Read Config File
    config_file_name = argv[1];
    config_file = fopen(config_file_name, "r");

    // Read variables
    if (config_file) {
        while (fgets(line, sizeof(line), config_file)) {
            sscanf(line, "Debug=%d[^\n]", &DEBUG);
            sscanf(line, "Errorfile=%[^\n]", error_file_name);
            sscanf(line, "Debugfile=%[^\n]", debug_file_name);
            sscanf(line, "Loginterval=%d[^\n]", &log_interval);
            sscanf(line, "Logavginterval=%d[^\n]", &logavg_interval);
            sscanf(line, "Waitinterval=%d[^\n]", &wait_interval);
            sscanf(line, "DBhost=%[^\n]", dbhost);
            sscanf(line, "DBname=%[^\n]", dbname);
            sscanf(line, "DBtable=%[^\n]", dbtable);
            sscanf(line, "DBuser=%[^\n]", dbuser);
            sscanf(line, "DBpass=%[^\n]", dbpass);
            sscanf(line, "Hostname=%[^\n]", hostaddr);
            sscanf(line, "Hostport=%d[^\n]", &portno);
            sscanf(line, "MQTThost=%[^\n]", mqtt_host);
            sscanf(line, "MQTTport=%d[^\n]", &mqtt_port);
            sscanf(line, "MQTTuser=%[^\n]", mqtt_user);
            sscanf(line, "MQTTpass=%[^\n]", mqtt_pass);
            sscanf(line, "MQTTtopic=%[^\n]", mqtt_topic);
            sscanf(line, "MQTTqos=%d[^\n]", &mqtt_qos);
            sscanf(line, "MQTTretain=%d[^\n]", &mqtt_retain);
            sscanf(line, "Nightpower=%d[^\n]", &night_power);
            sscanf(line, "INFLUXurl=%[^\n]", influx_url);
            sscanf(line, "INFLUXorg=%[^\n]", influx_org);
            sscanf(line, "INFLUXbucket=%[^\n]", influx_bucket);
            sscanf(line, "INFLUXtoken=%[^\n]", influx_token);
            sscanf(line, "INFLUXmeasurement=%[^\n]", influx_measurement);
        } // while
    } // if
    fclose(config_file);

    // Try to open error log file
    if ((error_file = fopen(error_file_name, "w")) == NULL) {
        error_exit("ERROR opening error.log file");
    } // if

    // Make file unbuffered
    setbuf(error_file, NULL);

    // calculate the requests per log_interval
    int logavg_pertick = log_interval /logavg_interval;

    // Try to open debug log file, if necessary
    if(DEBUG) {
        if((debug_file = fopen(debug_file_name, "w")) == NULL) {
            error_exit("ERROR opening debug.log file");
        } // if

        // Make file unbuffered
        setbuf(debug_file, NULL);
    } // if (DEBUG)

    // Try to compile regular expression
    result = regcomp(&rx, expression, REG_EXTENDED);
    if (result != 0) {
        regerror(result, &rx, expression, sizeof(expression));
        regfree(&rx);
        sprintf(buffer, "ERROR invalid regular expression: %s", expression);
        error_exit(buffer);
    } // if

    // Try to reserve memory for matches
    matches = (regmatch_t *) malloc((rx.re_nsub + 1) * sizeof(regmatch_t));
    if (!matches) error_exit("Out of memory");

    // Without DB, MQTT and InfluxDB there is nothing to log to
    if (dbhost[0] == '\0' && mqtt_host[0] == '\0' && influx_url[0] == '\0') {
        error_exit("ERROR neither DBhost nor MQTThost nor INFLUXurl configured");
    } // if

    // Start the MQTT client (does nothing if MQTThost is not configured)
    mqtt_start();

    // Set up InfluxDB (does nothing if INFLUXurl is not configured)
    influx_start();

    // Connect to database (only if DBhost is configured)
    if (dbhost[0] != '\0') {
        connection = mysql_init(NULL);
        if (!mysql_real_connect(connection, dbhost, dbuser, dbpass, dbname, 0, NULL, 0)) {
            error_exit(mysql_error(connection));
        } // if

        if (DEBUG) {
            sprintf(buffer, "Connected to database %s on host %s", dbname, dbhost);
            debug_entry(buffer);
        } // if (DEBUG)
    } // if
    else if (DEBUG) {
        debug_entry("DB logging disabled (no DBhost in config file)");
    } // else

    while (1) {

        // Check if connection to db-server must be re-established
        if (connection != NULL && mysql_ping(connection)) {

            //TODO Maybe a reconnect (if needed) here ?
            // Connect to database
            if (!mysql_real_connect(connection, dbhost, dbuser, dbpass, dbname, 0, NULL, 0))
                error_exit(mysql_error(connection));

            if (DEBUG) {
                sprintf(buffer, "Connected to database %s on host %s", dbname, dbhost);
                debug_entry(buffer);
            }
        }

        // Try to resolve solarmax address/hostname
        server = gethostbyname(hostaddr);
        if (server == NULL) {
            sprintf(buffer, "Can't resolve \"%s\"", hostaddr);
            error_retry(buffer);
            wait_offline(60);
            continue;
        }

        // prepare network parameters
        bzero((char *) &serv_addr, sizeof(serv_addr));
        serv_addr.sin_family = AF_INET;
        bcopy((char *) server->h_addr, (char *) &serv_addr.sin_addr.s_addr, server->h_length);
        serv_addr.sin_port = htons(portno);

        // Start sending the data requests and logging the answers
        time_t start_time = time(NULL);
        while (1) {
            failure_flag = 0;
            kdy = kmt = kyr = kt0 = tkk = pac = ud01 = ud02 = ud03 = id01 = id02 = id03 = sys = 0;

            // sample the data
            avgCount = logavg_pertick;
            while (avgCount--) {
                time_t single_start_time = time(NULL);

                // Generate message according to device address of solarmax:
                // Could be something like this:
                // sprintf(message, "{FB;0%d;46|64:KDY;KMT;KYR;KT0;TNF;TKK;PAC;PRL;IL1;IDC;UL1;UDC;SYS|%s}", active_max, 16_bit_checksum
                // For further information on the protocol refer to: http://blog.dest-unreach.be/2009/04/15/solarmax-maxtalk-protocol-reverse-engineered

                message = "{FB;01;4C|64:KDY;KMT;KYR;KT0;TKK;PAC;UD01;UD02;UD03;ID01;ID02;ID03;SYS|124A}";

                if (DEBUG) {
                    sprintf(buffer, "Sending message: %s", message);
                    debug_entry(buffer);
                } // if (DEBUG)

                // Try to open socket for communication with solarmax
                sockfd = socket(AF_INET, SOCK_STREAM, 0);
                if (sockfd < 0) {
                    error_retry("Can't open any socket");
                    sleep(60);
                    continue;
                } // if

                // Establish a connection with solarmax
                if (connect(sockfd, (struct sockaddr*) &serv_addr, sizeof(serv_addr)) < 0) {
                    sprintf(buffer, "%s: Can't connect to solarmax (%s) on port %d", strerror(errno), hostaddr, portno);
                    error_retry(buffer);
                    close(sockfd);
                    wait_offline(600);
                    failure_flag = 1;
                    break;
                } // if

                // Make socket non-blocking
                set_nonblock(sockfd);

                // Send message
                n = write(sockfd,message,strlen(message));
                if (n < 0) {
                    close(sockfd);
                    error_retry("ERROR sending TCP packet");
                    failure_flag = 1;
                    break;
                }

                // Read answer
                bzero(buffer, 256);
                usleep(10000);
                n = read(sockfd, buffer, 255);
                // try a second time
                if (n < 0) {
                    if (DEBUG) debug_entry("Socket contains no data, trying to read again later");
                    usleep(50000);
                    n = read(sockfd, buffer, 255);
                } // if (n < 0)

                // close connection
                close(sockfd);

                if (n < 0) {
                    error_retry("ERROR receiving TCP packet");
                    failure_flag = 1;
                    break;
                } // if

                if (DEBUG) {
                    sprintf(buffer2, "Received answer: %s", buffer);
                    debug_entry(buffer2);
                } // if (DEBUG)

                // Extract the data fields from answer
                result = regexec(&rx, buffer, rx.re_nsub + 1, matches, 0);
                if (result) {
                    regerror(result, &rx, buffer, sizeof(buffer));
                    error_retry("ERROR no regexp match");
                    failure_flag = 2;
                    break;
                }

                // Convert the extracted data fields of this sample to integer values
                cur_kdy  = strtol(buffer + matches[1].rm_so, NULL, 16);
                cur_kmt  = strtol(buffer + matches[2].rm_so, NULL, 16);
                cur_kyr  = strtol(buffer + matches[3].rm_so, NULL, 16);
                cur_kt0  = strtol(buffer + matches[4].rm_so, NULL, 16);
                cur_tkk  = strtol(buffer + matches[5].rm_so, NULL, 16);
                cur_pac  = strtol(buffer + matches[6].rm_so, NULL, 16) / 2;
                cur_ud01 = strtol(buffer + matches[7].rm_so, NULL, 16);
                cur_ud02 = strtol(buffer + matches[8].rm_so, NULL, 16);
                cur_ud03 = strtol(buffer + matches[9].rm_so, NULL, 16);
                cur_id01 = strtol(buffer + matches[10].rm_so, NULL, 16);
                cur_id02 = strtol(buffer + matches[11].rm_so, NULL, 16);
                cur_id03 = strtol(buffer + matches[12].rm_so, NULL, 16);
                cur_sys  = strtol(buffer + matches[13].rm_so, NULL, 16);

                kdy   = cur_kdy;
                kmt   = cur_kmt;
                kyr   = cur_kyr;
                kt0   = cur_kt0;
                tkk  += cur_tkk;
                pac  += cur_pac;
                ud01 += cur_ud01;
                ud02 += cur_ud02;
                ud03 += cur_ud03;
                id01 += cur_id01;
                id02 += cur_id02;
                id03 += cur_id03;
                sys   = cur_sys;
                have_counters = 1;

                // Publish the current values via MQTT
                mqtt_publish_sample();

                //TODO check if the task need more time than logavg_interval
                if (avgCount) sleep(logavg_interval - (time(NULL)-single_start_time));

            } // while (avgCount--)

            // Calculate the average values and write them to db and/or InfluxDB
            if (failure_flag == 0) {
                    tkk  = tkk  / logavg_pertick;
                    pac  = pac  / logavg_pertick;
                    ud01 = ud01 / logavg_pertick;
                    ud02 = ud02 / logavg_pertick;
                    ud03 = ud03 / logavg_pertick;
                    id01 = id01 / logavg_pertick;
                    id02 = id02 / logavg_pertick;
                    id03 = id03 / logavg_pertick;

                    if (connection != NULL) {
                        // Construct the query according to active solarmax
                        sprintf(query, "INSERT INTO %s (kdy, kmt, kyr, kt0, tkk, pac, udc1, udc2, udc3, idc1, idc2, idc3, sys) VALUES (%d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d);",
                                               dbtable, kdy, kmt, kyr, kt0, tkk, pac, ud01, ud02, ud03, id01, id02, id03, sys);
                        if (DEBUG) {
                            sprintf(buffer, "Executing query: %s", query);
                            debug_entry(buffer);
                        } // if (DEBUG)

                        // Execute the query to write the data into db
                        mysql_query(connection, query);
                        if (mysql_errno(connection)) error_exit(mysql_error(connection));
                    } // if (connection != NULL)

                    // Write the same values to InfluxDB
                    influx_write();

            } // if (failure_flag == 0)

            // Wait for the specified number of seconds - calc duration - 1
            if (DEBUG) debug_entry("Waiting for next sampling ...");

            // Get the current time
            time_t stop_time = time(NULL);

            // TODO check if time needed is > log_interval
            int sleepTime = log_interval + start_time - stop_time;
            if(sleepTime > 0) {
                sleep(sleepTime);
                start_time += log_interval;
            } // if
            else {
                // you get here after the 10 min delay after a connection error
                if (DEBUG) {
                    sprintf(buffer, "!!! sleepTime error. Assuming desync: %i seconds. !!!\n", sleepTime);
                    debug_entry(buffer);
                } // if (DEBUG)
                start_time = time(NULL);
            } // else

        } // while
    } // while

    mqtt_stop();
    influx_stop();

    return 0;
} // main
