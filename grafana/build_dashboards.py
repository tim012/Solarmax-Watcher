#!/usr/bin/env python3
"""Erzeugt die drei SolarMax-Grafana-Dashboards (Tag, Monat, Jahr) als JSON.

    python3 build_dashboards.py            -> schreibt nach grafana/dashboards/
Grafana lädt die JSON-Dateien per File-Provisioning direkt aus dashboards/
(provisioning.yaml); auf dem Server genügt git pull.

Siehe CLAUDE.md für Aufbau, Flux-Muster und bekannte Fallstricke.
"""
import json
import os
# Zeitzone für Tages-/Monats-/Jahresfenster und Anzeige
TZ = "Europe/Zurich"
# Datenquelle über eine versteckte Variable statt fester UID: funktioniert beim Bereitstellen
# aus Dateien (dort gibt es keine __inputs) und beim manuellen Import gleichermassen.
DS = {"type": "influxdb", "uid": "${ds}"}
DSVAR = {"name": "ds", "label": "Datenquelle", "type": "datasource", "query": "influxdb", "regex": "",
         "current": {}, "options": [], "hide": 2, "refresh": 1, "multi": False, "includeAll": False}
PRE = 'import "array"\nimport "date"\nimport "timezone"\noption location = timezone.location(name: "' + TZ + '")\n'
Y0 = 'date.truncate(t: time(v: "${jahr}-06-15T00:00:00Z"), unit: 1y)'
RANGE_YEAR = f'start: {Y0}, stop: date.add(d: 1y, to: {Y0})'


VPRE = PRE
M0 = 'date.truncate(t: time(v: "${jahr}-${monat}-15T00:00:00Z"), unit: 1mo)'
RANGE_MONTH = f'start: {M0}, stop: date.add(d: 1mo, to: {M0})'
Y0V = 'date.truncate(t: time(v: "${jahr}-06-15T12:00:00Z"), unit: 1y)'
TEIL = {"jahr": 'string(v: date.year(t: z))',
        "monat": '(if date.month(t: z) < 10 then "0" else "") + string(v: date.month(t: z))',
        "tag": '(if date.monthDay(t: z) < 10 then "0" else "") + string(v: date.monthDay(t: z))'}

def qvar(name, query):
    return {"name": name, "label": name, "type": "query", "datasource": DS, "query": query, "definition": query,
            "refresh": 1, "sort": 0, "regex": "", "current": {}, "options": [], "hide": 2,
            "multi": False, "includeAll": False}

def nav_query(ebene, delta, teil):
    # date.add nimmt "to:", date.sub nimmt "from:"
    step = (lambda d, x: f"date.add(d: {d}, to: {x})") if delta > 0 else (lambda d, x: f"date.sub(d: {d}, from: {x})")
    if ebene == "tag":
        kopf = f"""m0 = {M0}
m1 = date.add(d: 1mo, to: m0)
kand = date.truncate(t: time(v: int(v: m0) + 43200000000000 + (int(v: "${{tag}}") - 1) * 86400000000000), unit: 1d)
d0 = if int(v: kand) >= int(v: m1) then date.truncate(t: date.sub(d: 12h, from: m1), unit: 1d) else kand
z = {step("1d", "date.add(d: 12h, to: d0)")}"""
    elif ebene == "monat":
        kopf = f'z = date.add(d: 12h, to: {step("1mo", M0)})'
    else:
        kopf = f'z = date.add(d: 12h, to: {step("1y", Y0V)})'
    return VPRE + kopf + "\narray.from(rows: [{_value: " + TEIL[teil] + "}])"

JAHRE_Q = VPRE + """j = date.year(t: now())
array.from(rows: [{n: 1}, {n: 2}, {n: 3}, {n: 4}, {n: 5}, {n: 6}, {n: 7}, {n: 8}, {n: 9}, {n: 10}, {n: 11}, {n: 12}, {n: 13}, {n: 14}, {n: 15}, {n: 16}, {n: 17}, {n: 18}, {n: 19}, {n: 20}, {n: 21}, {n: 22}, {n: 23}, {n: 24}, {n: 25}, {n: 26}, {n: 27}, {n: 28}, {n: 29}, {n: 30}])
  |> map(fn: (r) => ({j: j - r.n + 1}))
  |> filter(fn: (r) => r.j >= 2014)
  |> map(fn: (r) => ({_value: string(v: r.j)}))"""

# Liefert "09|Sep"; die Regex der Variable trennt Wert und Anzeigetext (Flux-Variablen selbst
# kennen keine Beschriftung).
MONATE_Q = VPRE + """monate = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
jj = int(v: "${jahr}")
letzter = if jj == date.year(t: now()) then date.month(t: now()) else 12
array.from(rows: [{n: 1}, {n: 2}, {n: 3}, {n: 4}, {n: 5}, {n: 6}, {n: 7}, {n: 8}, {n: 9}, {n: 10}, {n: 11}, {n: 12}])
  |> filter(fn: (r) => r.n <= letzter)
  |> sort(columns: ["n"], desc: true)
  |> map(fn: (r) => ({_value: (if r.n < 10 then "0" else "") + string(v: r.n) + "|" + monate[r.n - 1]}))"""
MONATE_RE = r"/(?<value>[^|]+)\|(?<text>.+)/"

TAGE_Q = VPRE + """m0 = date.truncate(t: time(v: "${jahr}-${monat}-15T12:00:00Z"), unit: 1mo)
m1 = date.add(d: 1mo, to: m0)
heute = date.add(d: 12h, to: date.truncate(t: now(), unit: 1d))
letzter = if int(v: m0) <= int(v: heute) and int(v: heute) < int(v: m1)
  then date.monthDay(t: heute)
  else date.monthDay(t: date.sub(d: 12h, from: m1))
array.from(rows: [{n: 1}, {n: 2}, {n: 3}, {n: 4}, {n: 5}, {n: 6}, {n: 7}, {n: 8}, {n: 9}, {n: 10}, {n: 11}, {n: 12}, {n: 13}, {n: 14}, {n: 15}, {n: 16}, {n: 17}, {n: 18}, {n: 19}, {n: 20}, {n: 21}, {n: 22}, {n: 23}, {n: 24}, {n: 25}, {n: 26}, {n: 27}, {n: 28}, {n: 29}, {n: 30}, {n: 31}])
  |> filter(fn: (r) => r.n <= letzter)
  |> sort(columns: ["n"], desc: true)
  |> map(fn: (r) => ({_value: (if r.n < 10 then "0" else "") + string(v: r.n)}))"""

def lvar(name, label, query, regex=""):
    return {"name": name, "label": label, "type": "query", "datasource": DS, "query": query,
            "definition": query, "refresh": 1, "sort": 0, "regex": regex, "current": {}, "options": [],
            "hide": 0, "multi": False, "includeAll": False}


def heute_query(teil, bucket="solarmax"):
    # Zeitpunkt des jüngsten Werts im Bucket statt now()
    return VPRE + 'from(bucket: "' + bucket + '")' + """
  |> range(start: -90d)
  |> group()
  |> max(column: "_time")
  |> keep(columns: ["_time"])
  |> map(fn: (r) => ({_value: """ + TEIL[teil].replace("t: z", "t: r._time") + "}))"

def heute_vars(ebene, bucket="solarmax"):
    teile = {"tag": ["jahr", "monat", "tag"], "monat": ["jahr", "monat"], "jahr": ["jahr"]}[ebene]
    return [qvar(f"heute_{t}", heute_query(t, bucket)) for t in teile]

def heute_link(uid, ebene):
    teile = {"tag": ["jahr", "monat", "tag"], "monat": ["jahr", "monat"], "jahr": ["jahr"]}[ebene]
    ziel = f"/d/{uid}?" + "&".join("var-%s=${heute_%s}" % (t, t) for t in teile)
    return [{"type": "link", "title": "Heute", "url": ziel, "tooltip": "Zum jüngsten Wert im Archiv springen",
             "icon": "", "tags": [], "asDropdown": False, "targetBlank": False,
             "includeVars": False, "keepTime": False}]

def nav_vars(ebene):
    teile = {"tag": ["jahr", "monat", "tag"], "monat": ["jahr", "monat"], "jahr": ["jahr"]}[ebene]
    out = []
    for richtung, delta in (("z", -1), ("v", 1)):
        for teil in teile:
            out.append(qvar(f"nav_{richtung}_{teil}", nav_query(ebene, delta, teil)))
    return out

def nav_links(uid, ebene, titel_z, titel_v):
    teile = {"tag": ["jahr", "monat", "tag"], "monat": ["jahr", "monat"], "jahr": ["jahr"]}[ebene]
    def ziel(richtung):
        return f"/d/{uid}?" + "&".join("var-%s=${nav_%s_%s}" % (t, richtung, t) for t in teile)
    def lnk(titel, richtung, tip):
        return {"type": "link", "title": titel, "url": ziel(richtung), "tooltip": tip, "icon": "",
                "tags": [], "asDropdown": False, "targetBlank": False, "includeVars": False, "keepTime": False}
    return [lnk(titel_z, "z", "Ein Schritt zurück"), lnk(titel_v, "v", "Ein Schritt vor")]


class D:
    def __init__(s): s.panels = []; s.id = 0
    def add(s, **kw):
        s.id += 1; kw["id"] = s.id; kw["datasource"] = DS; s.panels.append(kw)

BASE = {"__requires": [{"type": "datasource", "id": "influxdb", "name": "InfluxDB", "version": "1.0.0"}],
        "timezone": TZ, "schemaVersion": 39, "editable": True, "tags": ["solarmax"],
        # Aufklapp-Menü mit allen Dashboards, die den Tag "solarmax" tragen
        "links": [{"type": "dashboards", "tags": ["solarmax"], "asDropdown": True, "title": "SolarMax",
                   "includeVars": False, "keepTime": False, "icon": "external link"}]}

# Tag aus Jahr/Monat/Tag; ungültige Tage (z.B. 31. Februar) werden auf den Monatsletzten begrenzt
DAYDEF = PRE + """m0 = date.truncate(t: time(v: "${jahr}-${monat}-15T12:00:00Z"), unit: 1mo)
m1 = date.add(d: 1mo, to: m0)
kand = date.truncate(t: time(v: int(v: m0) + 43200000000000 + (int(v: "${tag}") - 1) * 86400000000000), unit: 1d)
d0 = if int(v: kand) >= int(v: m1) then date.truncate(t: date.sub(d: 12h, from: m1), unit: 1d) else kand
d1 = date.add(d: 1d, to: d0)
"""
RANGE_DAY = 'start: d0, stop: d1'

# ================= SolarMax: ausschliesslich Bucket "solarmax" =================
# Rohwerte des Wechselrichters alle 2 min, Felder als int: pac W, udc 0.1 V, idc 0.01 A,
# kdy 0.1 kWh, kmt/kyr/kt0 kWh, tkk °C, sys Statuscode. String 3 ist unbelegt und fehlt.
# Erträge kommen durchgehend aus dem Tageszähler kdy (Tagesmaximum), damit Tag, Monat und
# Jahr zueinander passen; nur der Kopfbereich zeigt die Zähler kmt/kyr/kt0 direkt.
ERW_TAG = [10.0, 15.2, 23.2, 25.7, 26.4, 28.2, 29.1, 27.7, 24.1, 18.1, 10.0, 7.6]
ERW_MON = [299.0, 455.0, 696.0, 771.0, 793.0, 846.0, 874.0, 832.0, 723.0, 543.0, 298.0, 227.0]
def flux_arr(xs): return "[" + ", ".join(repr(x) for x in xs) + "]"
MON_IDX = 'int(v: "${monat}") - 1'
STATUS = {20001: "Service", 20002: "Zu wenig Einstrahlung", 20003: "Anfahren", 20004: "Betrieb auf MPP",
          20005: "Ventilator an", 20006: "Max. AC-Einspeiseleistung", 20007: "Temperaturüberschreitung",
          20008: "Netzbetrieb", 20009: "Max. DC-Eingangsleistung"}
SM_BASE = BASE
# Live-Werte im Kopf (Leistung, Temperatur, DC, Status) gelten als offline, wenn der letzte
# Wert älter ist (Logger schreibt alle 2 min, 10 min = fünf verpasste Werte).
OFFLINE = "10m"

def sm_src(rng, fields):
    cond = " or ".join(f'r._field == "{f}"' for f in fields)
    return f'from(bucket: "solarmax")\n  |> range({rng})\n  |> filter(fn: (r) => r._measurement == "solarmax" and ({cond}))\n'

def sm_tage(rng):
    # Tagesertrag in kWh je Tag (lokale Tage), _start/_stop bleiben für aggregateWindow erhalten
    return sm_src(rng, ["kdy"]) + """  |> aggregateWindow(every: 1d, fn: max, createEmpty: false, timeSrc: "_start")
  |> group()
  |> map(fn: (r) => ({_time: r._time, _start: r._start, _stop: r._stop, _value: float(v: r._value) / 10.0}))
"""

def sm_monate(rng):
    # Monatsertrag in kWh je Monat aus dem Monatszähler kmt (Monatsmaximum). Vollständiger als
    # die Summe der Tageserträge: der Wechselrichter zählt auch, wenn der Logger nicht lief.
    return sm_src(rng, ["kmt"]) + """  |> aggregateWindow(every: 1mo, fn: max, createEmpty: false, timeSrc: "_start")
  |> group()
  |> map(fn: (r) => ({_time: r._time, _start: r._start, _stop: r._stop, _value: float(v: r._value)}))
"""

def sm_stat(d, title, q, unit, gp, decimals=0, desc="", no_value=None, mappings=None, multi=False, pre=PRE):
    fc = {"unit": unit, "decimals": decimals, "color": {"mode": "fixed", "fixedColor": "text"}}
    if no_value: fc["noValue"] = no_value
    if mappings: fc["mappings"] = mappings
    d.add(type="stat", title=title, description=desc, gridPos=gp,
          targets=[{"refId": "A", "datasource": DS, "query": pre + q}],
          options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                   "colorMode": "value", "graphMode": "none", "textMode": "value_and_name" if multi else "value",
                   "justifyMode": "center"},
          fieldConfig={"defaults": fc, "overrides": []})

def sm_kopf(d):
    """Aktuelle Werte wie im Kopf der alten Web-Oberfläche – unabhängig vom gewählten Zeitraum."""
    heute = "start: date.truncate(t: now(), unit: 1d)"
    live = f"start: -{OFFLINE}"
    def last1(f, rng, conv):
        return sm_src(rng, [f]) + f"  |> last()\n  |> map(fn: (r) => ({{_time: r._time, _value: {conv}}}))"
    def strings(a, b, div):
        return sm_src(live, [a, b]) + f"""  |> last()
  |> group()
  |> pivot(rowKey: ["_measurement"], columnKey: ["_field"], valueColumn: "_value")
  |> map(fn: (r) => ({{s1: float(v: r.{a}) / {div}, s2: float(v: r.{b}) / {div}}}))
  |> rename(columns: {{s1: "String 1", s2: "String 2"}})"""
    sm_stat(d, "Einspeiseleistung", last1("pac", live, "float(v: r._value)"), "W", {"h": 3, "w": 5, "x": 0, "y": 0},
            no_value="0 W", desc=f"Aktuelle AC-Leistung; 0 W, wenn der letzte Wert älter als {OFFLINE} ist.")
    sm_stat(d, "Temperatur WR", last1("tkk", live, "float(v: r._value)"), "celsius", {"h": 3, "w": 4, "x": 5, "y": 0}, no_value="–")
    sm_stat(d, "DC-Spannung", strings("udc1", "udc2", "10.0"), "volt", {"h": 3, "w": 5, "x": 9, "y": 0}, no_value="–", multi=True)
    sm_stat(d, "DC-Strom", strings("idc1", "idc2", "100.0"), "amp", {"h": 3, "w": 5, "x": 14, "y": 0}, decimals=2, no_value="–", multi=True)
    sm_stat(d, "Betriebsstatus", last1("sys", live, "r._value"), "none", {"h": 3, "w": 5, "x": 19, "y": 0}, no_value="Offline",
            desc=f"Statuscode des Wechselrichters; unbekannte Codes erscheinen als Zahl. Offline, wenn der letzte Wert älter als {OFFLINE} ist.",
            mappings=[{"type": "value", "options": {str(k): {"text": v, "index": i} for i, (k, v) in enumerate(STATUS.items())}}])
    sm_stat(d, "Ertrag heute", last1("kdy", heute, "float(v: r._value) / 10.0"), "kWh", {"h": 3, "w": 6, "x": 0, "y": 3},
            decimals=1, no_value="0 kWh")
    sm_stat(d, "Monatsertrag", last1("kmt", "start: date.truncate(t: now(), unit: 1mo)", "float(v: r._value)"), "kWh",
            {"h": 3, "w": 6, "x": 6, "y": 3}, no_value="0 kWh", desc="Zähler des Wechselrichters (kmt).")
    sm_stat(d, "Jahresertrag", last1("kyr", "start: date.truncate(t: now(), unit: 1y)", "float(v: r._value)"), "kWh",
            {"h": 3, "w": 6, "x": 12, "y": 3}, no_value="0 kWh", desc="Zähler des Wechselrichters (kyr).")
    sm_stat(d, "Gesamtertrag", last1("kt0", "start: -30d", "float(v: r._value)"), "kWh",
            {"h": 3, "w": 6, "x": 18, "y": 3}, desc="Zähler des Wechselrichters (kt0).")

def sm_zeitraum(d, titel, rng, erw, pre, y=21, quelle=sm_tage, desc=""):
    """Ertrag, Erwartung und Anteil für den gewählten Zeitraum: Summe aus quelle
    (Tag: Tageszähler kdy, Monat/Jahr: Monatszähler kmt)."""
    summe = quelle(rng) + "  |> sum()"
    sm_stat(d, titel, summe, "kWh", {"h": 3, "w": 8, "x": 0, "y": y}, decimals=1, no_value="0 kWh", pre=pre, desc=desc)
    sm_stat(d, "Erwartet", f"array.from(rows: [{{_value: {erw}}}])", "kWh", {"h": 3, "w": 8, "x": 8, "y": y},
            desc="Feste Erwartungswerte (PVGIS) aus der alten Web-Oberfläche.", pre=pre)
    sm_stat(d, "Anteil am erwarteten Ertrag", f"erw = {erw}\n" + quelle(rng) + """  |> sum()
  |> map(fn: (r) => ({_value: r._value / erw * 100.0}))""",
            "percent", {"h": 3, "w": 8, "x": 16, "y": y}, no_value="0 %", pre=pre)

def ovr(name, props): return {"matcher": {"id": "byName", "options": name}, "properties": [{"id": k, "value": v} for k, v in props]}
def farbe(c): return ("color", {"mode": "fixed", "fixedColor": c})
DASH = ("custom.lineStyle", {"fill": "dash", "dash": [10, 6]})

# ---------- SolarMax Tag
st = D()
sm_kopf(st)
sm_zeitraum(st, "Ertrag ${tag}.${monat}.${jahr}", RANGE_DAY, f"{flux_arr(ERW_TAG)}[{MON_IDX}]", DAYDEF, y=24)
sm_tag_q = DAYDEF + f"erw = {flux_arr(ERW_TAG)}[{MON_IDX}]\n" + \
    sm_src(RANGE_DAY, ["pac", "kdy", "udc1", "udc2", "idc1", "idc2"]) + """  |> group()
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
  |> map(fn: (r) => ({
       Uhrzeit: float(v: int(v: r._time) - int(v: d0)) / 3600000000000.0,
       pac: float(v: r.pac) / 1000.0,
       ertrag: float(v: r.kdy) / 10.0,
       vorhersage: erw,
       udc1: float(v: r.udc1) / 10.0, udc2: float(v: r.udc2) / 10.0,
       idc1: float(v: r.idc1) / 100.0, idc2: float(v: r.idc2) / 100.0,
       pdc1: float(v: r.udc1) * float(v: r.idc1) / 1000000.0,
       pdc2: float(v: r.udc2) * float(v: r.idc2) / 1000000.0}))
  |> rename(columns: {pac: "Leistung AC", ertrag: "Ertrag", vorhersage: "Vorhersage",
       udc1: "UDC String 1", udc2: "UDC String 2", idc1: "IDC String 1", idc2: "IDC String 2",
       pdc1: "PDC String 1", pdc2: "PDC String 2"})"""
# x-Achse in Stunden statt Sekunden: Grafana legt Achsenstriche auf runde Zahlen (1, 2, 5 …),
# in Stunden also auf volle Stunden. Anzeige als hh:mm über Bereichszuordnungen je Minute –
# gilt für Achsenbeschriftung und Tooltip; Obergrenze knapp unter der nächsten Minute, weil
# Grafana Bereiche inklusive beider Grenzen vergleicht. Nur 05:00–22:00 (sichtbarer Bereich).
MINUTEN = [{"type": "range", "options": {"from": m / 60, "to": (m + 1) / 60 - 1e-9,
            "result": {"text": f"{m // 60:02d}:{m % 60:02d}", "index": m}}} for m in range(5 * 60, 22 * 60 + 1)]
st.add(type="trend", title="Leistung im Tagesverlauf",
       description="Ertrag = akkumulierter Tagesertrag, Vorhersage = erwarteter Tagesertrag (beide kWh, rechte Achse).",
       gridPos={"h": 18, "w": 24, "x": 0, "y": 6},
       targets=[{"refId": "A", "datasource": DS, "query": sm_tag_q}],
       options={"xField": "Uhrzeit", "legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi", "sort": "none"}},
       fieldConfig={"defaults": {"decimals": 2, "custom": {"drawStyle": "line", "lineInterpolation": "linear", "fillOpacity": 0,
                                                            "lineWidth": 1, "showPoints": "never", "spanNulls": False}},
                    "overrides": [
         ovr("Uhrzeit", [("unit", "none"), ("min", 5), ("max", 22), ("mappings", MINUTEN)]),
         ovr("Leistung AC", [("unit", "kwatt"), ("min", 0), ("max", 13), farbe("orange"), ("custom.fillOpacity", 60), ("custom.lineWidth", 0)]),
         ovr("PDC String 1", [("unit", "kwatt"), ("min", 0), ("max", 13), farbe("red"), ("custom.lineWidth", 2)]),
         ovr("PDC String 2", [("unit", "kwatt"), ("min", 0), ("max", 13), farbe("green"), ("custom.lineWidth", 2)]),
         ovr("Ertrag", [("unit", "kWh"), farbe("blue"), ("custom.lineWidth", 2), ("custom.axisPlacement", "right"), ("min", 0), ("max", 100)]),
         ovr("Vorhersage", [("unit", "kWh"), farbe("blue"), DASH, ("custom.axisPlacement", "right"), ("min", 0), ("max", 100)]),
         ovr("UDC String 1", [("unit", "volt"), farbe("red"), ("custom.axisPlacement", "right"), ("decimals", 0), ("min", 0), ("max", 800)]),
         ovr("UDC String 2", [("unit", "volt"), farbe("green"), ("custom.axisPlacement", "right"), ("decimals", 0), ("min", 0), ("max", 800)]),
         ovr("IDC String 1", [("unit", "amp"), farbe("red"), DASH, ("custom.axisPlacement", "right"), ("min", 0), ("max", 10)]),
         ovr("IDC String 2", [("unit", "amp"), farbe("green"), DASH, ("custom.axisPlacement", "right"), ("min", 0), ("max", 10)]),
       ]})
solarmax_tag = dict(SM_BASE, links=nav_links("solarmax-tag", "tag", "◀", "▶") + heute_link("solarmax-tag", "tag") + SM_BASE["links"],
                    title="SolarMax – Tag", uid="solarmax-tag", version=7, refresh="5m",
                    time={"from": "now/d", "to": "now/d"}, timepicker={"hidden": True},
                    templating={"list": [DSVAR, lvar("jahr", "Jahr", JAHRE_Q), lvar("monat", "Monat", MONATE_Q, MONATE_RE),
                                         lvar("tag", "Tag", TAGE_Q)] + nav_vars("tag") + heute_vars("tag", "solarmax")},
                    panels=st.panels)

# ---------- SolarMax Monat
sm_m = D()
sm_kopf(sm_m)
sm_zeitraum(sm_m, "Ertrag ${monat:text} ${jahr}", RANGE_MONTH, f"{flux_arr(ERW_MON)}[{MON_IDX}]", PRE,
            quelle=sm_monate, desc="Aus dem Monatszähler des Wechselrichters (kmt). Enthält auch Zeiten, in denen der Logger nicht lief – kann deshalb höher sein als die Summe der Tagesbalken.")
# Durchschnitt per join über eine feste Spalte k statt findColumn (lieferte in Grafana nichts)
sm_monat_q = PRE + f"erw = {flux_arr(ERW_TAG)}[{MON_IDX}]\n" + "t = " + sm_tage(RANGE_MONTH) + """avg = t
  |> mean()
  |> map(fn: (r) => ({k: 1, Durchschnitt: r._value}))
tage = t
  |> map(fn: (r) => ({k: 1, Tag: float(v: date.monthDay(t: r._time)), Tagesertrag: r._value,
       Kumuliert: r._value, Erwartet: erw}))
  |> cumulativeSum(columns: ["Kumuliert"])
join(tables: {t: tage, a: avg}, on: ["k"])
  |> drop(columns: ["k"])
  |> sort(columns: ["Tag"])"""
sm_m.add(type="trend", title="Ertrag pro Tag",
         description="Erwartet = erwarteter Tagesertrag, Durchschnitt = mittlerer Tagesertrag des Monats, Kumuliert = Monatsertrag bis zum Tag (rechte Achse).",
         gridPos={"h": 15, "w": 24, "x": 0, "y": 6},
         targets=[{"refId": "A", "datasource": DS, "query": sm_monat_q}],
         options={"xField": "Tag", "legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi", "sort": "none"}},
         fieldConfig={"defaults": {"unit": "kWh", "decimals": 1, "min": 0, "max": 100,
                                   "custom": {"drawStyle": "line", "lineInterpolation": "linear", "fillOpacity": 0,
                                              "lineWidth": 2, "showPoints": "never", "spanNulls": True}},
                      "overrides": [
           ovr("Tag", [("unit", "none"), ("decimals", 0), ("min", 0.5), ("max", 31.5)]),
           ovr("Tagesertrag", [farbe("green"), ("custom.drawStyle", "bars"), ("custom.fillOpacity", 80), ("custom.lineWidth", 0)]),
           ovr("Erwartet", [farbe("blue")]),
           ovr("Durchschnitt", [farbe("yellow")]),
           ovr("Kumuliert", [("unit", "kwatth"), ("max", 1000), farbe("text"), ("custom.lineWidth", 1), ("custom.axisPlacement", "right")]),
         ]})
solarmax_monat = dict(SM_BASE, links=nav_links("solarmax-monat", "monat", "◀", "▶") + heute_link("solarmax-monat", "monat") + SM_BASE["links"],
                      title="SolarMax – Monat", uid="solarmax-monat", version=7, refresh="15m",
                      time={"from": "now/M", "to": "now/M"}, timepicker={"hidden": True},
                      templating={"list": [DSVAR, lvar("jahr", "Jahr", JAHRE_Q), lvar("monat", "Monat", MONATE_Q, MONATE_RE)]
                                          + nav_vars("monat") + heute_vars("monat", "solarmax")},
                      panels=sm_m.panels)

# ---------- SolarMax Jahr
sm_j = D()
sm_kopf(sm_j)
sm_zeitraum(sm_j, "Ertrag ${jahr}", RANGE_YEAR, repr(sum(ERW_MON)), PRE,
            quelle=sm_monate, desc="Summe der Monatszähler (kmt), wie in der alten Web-Oberfläche.")
sm_jahr_q = PRE + f"erw = {flux_arr(ERW_MON)}\n" + sm_monate(RANGE_YEAR) + """  |> map(fn: (r) => ({Monat: float(v: date.month(t: r._time)), Monatsertrag: r._value,
       Erwartet: erw[date.month(t: r._time) - 1],
       Anteil: r._value / erw[date.month(t: r._time) - 1] * 100.0}))"""
MONATSNAMEN = {"type": "value", "options": {str(i + 1): {"text": n, "index": i} for i, n in
               enumerate(["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"])}}
sm_j.add(type="trend", title="Ertrag pro Monat",
         description="Monatsertrag aus dem Monatszähler (kmt). Erwartet = erwarteter Monatsertrag; Anteil (nur im Tooltip) = Ertrag in Prozent davon.",
         gridPos={"h": 15, "w": 24, "x": 0, "y": 6},
         targets=[{"refId": "A", "datasource": DS, "query": sm_jahr_q}],
         options={"xField": "Monat", "legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi", "sort": "none"}},
         fieldConfig={"defaults": {"unit": "kWh", "decimals": 0, "min": 0, "max": 2200,
                                   "custom": {"drawStyle": "line", "lineInterpolation": "linear", "fillOpacity": 0,
                                              "lineWidth": 2, "showPoints": "always", "pointSize": 6, "spanNulls": True}},
                      "overrides": [
           ovr("Monat", [("unit", "none"), ("decimals", 0), ("min", 0.5), ("max", 12.5), ("mappings", [MONATSNAMEN])]),
           ovr("Monatsertrag", [farbe("green"), ("custom.drawStyle", "bars"), ("custom.fillOpacity", 80),
                                ("custom.lineWidth", 0), ("custom.showPoints", "never")]),
           ovr("Erwartet", [farbe("blue")]),
           ovr("Anteil", [("unit", "percent"), ("custom.hideFrom", {"viz": True, "legend": True, "tooltip": False}),
                          ("custom.axisPlacement", "hidden")]),
         ]})
solarmax_jahr = dict(SM_BASE, links=nav_links("solarmax-jahr", "jahr", "◀", "▶") + heute_link("solarmax-jahr", "jahr") + SM_BASE["links"],
                     title="SolarMax – Jahr", uid="solarmax-jahr", version=7,
                     time={"from": "now/y", "to": "now/y"}, timepicker={"hidden": True},
                     templating={"list": [DSVAR, lvar("jahr", "Jahr", JAHRE_Q)] + nav_vars("jahr") + heute_vars("jahr", "solarmax")},
                     panels=sm_j.panels)

for name, dash in (("solarmax-tag.json", solarmax_tag), ("solarmax-monat.json", solarmax_monat), ("solarmax-jahr.json", solarmax_jahr)):
    json.dump(dash, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboards", name), "w"), ensure_ascii=False, indent=2)
    print(name, len(dash["panels"]), [p["title"] for p in dash["panels"]])
