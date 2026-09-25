# CLAUDE.md – SolarMax-Dashboards

Grafana-Dashboards für die Daten des SolarMax-Loggers (InfluxDB 2, Flux). Diese Datei ist
der Entwicklungskontext für die Dashboards und wird laufend nachgeführt: neue Fallstricke,
erledigte oder neue offene Punkte, geänderte Abläufe gleich hier eintragen. Was ein Mensch
zur Bedienung wissen muss, gehört ins `../README.md`.

Pfade unten sind relativ zu diesem Ordner (`grafana/`).

## Regeln

- **Die JSON-Dateien unter `dashboards/` nie von Hand bearbeiten.** Sie werden aus
  `build_dashboards.py` erzeugt; die drei Dashboards teilen sich Flux-Bausteine.
  Änderungen gehören ins Skript, danach neu generieren.
- Nach jeder Änderung `python3 build_dashboards.py` ausführen; die erzeugten JSON-Dateien
  gehören zusammen mit dem Skript ins Repo.
- Bei strukturellen Änderungen die `version` des betroffenen Dashboards im Skript erhöhen.
- **UIDs der Dashboards nie ändern** – Navigationslinks und das Provisioning hängen daran.
- Flux-Abfragen nicht vereinfachen, ohne die Fallstricke unten gelesen zu haben — mehrere
  der umständlich wirkenden Stellen umgehen konkrete Fehler.

## Befehle

```
python3 build_dashboards.py   # erzeugt dashboards/*.json
```

Grafana lädt `dashboards/*.json` per File-Provisioning selbst (`provisioning.yaml`, Ordner
„SolarMax", schreibgeschützt); nach `git pull` auf dem Server innert 30 s aktiv. Kein
manueller Import.

### Prüfen ohne Grafana

Flux-Abfragen direkt gegen InfluxDB testen — zuverlässiger als der Data Explorer:

```
influx query --org <org> '<Flux>'      # im InfluxDB-Container
```

Variablen wie `${jahr}` dabei durch konkrete Werte ersetzen.

## Datengrundlage

InfluxDB 2 (OSS), Grafana-Datenquelle vom Typ InfluxDB mit **Flux** (nicht InfluxQL).
Einzige Quelle ist der Bucket `solarmax`, den der Logger befüllt (`INFLUX*` in
`smw-logger.conf`).

Schema `solarmax`: Measurement `solarmax`, keine Tags, alle Felder `int`, Rohwerte des
SolarMax-Protokolls:

| Feld               | Bedeutung                   | Einheit roh → Anzeige          |
|--------------------|-----------------------------|--------------------------------|
| `pac`              | AC-Einspeiseleistung        | W                              |
| `udc1`..`udc3`     | DC-Spannung String 1–3      | 0.1 V (6843 → 684.3 V)         |
| `idc1`..`idc3`     | DC-Strom String 1–3         | 0.01 A (238 → 2.38 A)          |
| `kdy`              | Ertrag heute                | 0.1 kWh (22 → 2.2)             |
| `kmt` / `kyr`      | Ertrag Monat / Jahr         | kWh                            |
| `kt0`              | Gesamtertrag                | kWh                            |
| `tkk`              | Temperatur Wechselrichter   | °C                             |
| `sys`              | Betriebsstatus (Code)       | 20008 = Netzbetrieb            |

Statuscodes (`STATUS` im Skript, aus der alten Web-Oberfläche): 20001 Service,
20002 Zu wenig Einstrahlung, 20003 Anfahren, 20004 Betrieb auf MPP, 20005 Ventilator an,
20006 Max. AC-Einspeiseleistung, 20007 Temperaturüberschreitung, 20008 Netzbetrieb,
20009 Max. DC-Eingangsleistung. Andere Codes erscheinen ohne Text als Zahl.

## Die drei Dashboards

| Datei                 | UID              | Variablen        |
|-----------------------|------------------|------------------|
| `solarmax-tag.json`   | `solarmax-tag`   | jahr, monat, tag |
| `solarmax-monat.json` | `solarmax-monat` | jahr, monat      |
| `solarmax-jahr.json`  | `solarmax-jahr`  | jahr             |

Nachbau der alten SolarMax-Web-Oberfläche (`../web/`). Alle tragen den Tag `solarmax`;
oben gibt es ein Aufklapp-Menü „SolarMax" (`BASE["links"]`, Dashboard-Links nach Tag
`solarmax`), dazu Pfeile ◀ ▶ und „Heute".

Aufbau aller drei:
1. Kopf (`sm_kopf`, aktuelle Werte, unabhängig vom gewählten Zeitraum): Einspeiseleistung,
   Temperatur WR, DC-Spannung und DC-Strom je String, Betriebsstatus; Ertrag heute,
   Monats-, Jahres-, Gesamtertrag (Zähler `kmt`/`kyr`/`kt0` direkt).
   Live-Kacheln (Leistung, Temperatur, DC-Spannung/-Strom, Status) suchen ihren letzten
   Wert nur in den letzten `OFFLINE` (10 min = fünf verpasste 2-min-Werte). Ist der letzte
   Wert älter: Leistung „0 W", Temperatur/DC „–" (0 °C/0 V sähe wie ein Messwert aus),
   Status „Offline". Ertrag heute bleibt bis Mitternacht stehen, Monat/Jahr/Gesamt sind
   Zählerstände und bleiben ebenfalls.
   Einspeiseleistung fest in W (Einheit `W`, nicht `watt` – die skaliert auf kW).
2. Grafik (Trend-Panel) – Tag: Leistung AC (Fläche), PDC/UDC/IDC je String, Ertrag
   akkumuliert und Vorhersage, x 05:00–22:00. Monat: Balken je Tag plus Linien Erwartet,
   Durchschnitt, Kumuliert (eigene rechte Achse). Jahr: Balken je Monat plus Erwartet;
   Anteil in % nur im Tooltip.
3. Unter der Grafik (`sm_zeitraum`): Ertrag, Erwartet, Anteil am erwarteten Ertrag für
   den gewählten Zeitraum.

Anpassen an die eigene Anlage (alles im Skript):
- `TZ` – Zeitzone für Tages-/Monats-/Jahresfenster.
- `ERW_TAG` / `ERW_MON` – erwarteter Ertrag pro Tag bzw. Monat, z. B. aus PVGIS; feste
  Werte, unabhängig voneinander – nicht ineinander umrechnen.
- Feste Achsen wie im Original: Tag kW 0–13, kWh 0–100, A 0–10, V 0–800; Monat kWh 0–100,
  Kumuliert 0–1000; Jahr kWh 0–2200. `max` der kW-Achse an die Anlagenleistung anpassen.
- `JAHRE_Q` – erstes Jahr der Auswahlliste (`r.j >= 2014`).
- String 3 wird nicht angezeigt; bei drei belegten Strings in `sm_kopf` und `sm_tag_q`
  ergänzen.

Berechnung:
- Tageserträge (Tagesbalken, Tag-Kachel, Kumuliert): Tagesmaximum von `kdy` je lokalem Tag
  (`sm_tage`). `kdy` wird morgens sauber zurückgesetzt.
- Monats- und Jahreserträge (Jahresbalken, Kacheln Monat/Jahr): Monatsmaximum von `kmt`
  (`sm_monate`), Jahr = Summe der Monate. Grund: Läuft der Logger zeitweise nicht, zählt
  der Wechselrichter trotzdem weiter, `kmt` ist deshalb vollständig. Die alte
  Web-Oberfläche rechnete ebenso.
- Folge: In Monaten mit Lücken ist die Monats-Kachel höher als die Summe der Tagesbalken
  bzw. das Ende der Kumuliert-Linie – gewollt, im Kachel-Tooltip erklärt.

Tagesgrafik-Zeitachse: `Uhrzeit` in **Stunden** seit Mitternacht (nicht Sekunden) – Grafana
setzt Achsenstriche auf runde Zahlen, in Sekunden gab das Zeiten wie 01:23:20, in Stunden
volle Stunden. Anzeige als hh:mm über Bereichszuordnungen je Minute (`MINUTEN`, nur
05:00–22:00; Obergrenze knapp unter der nächsten Minute, weil Grafana Bereiche inklusive
beider Grenzen vergleicht). Macht `solarmax-tag.json` gross (~400 KB) – bewusst so. Einen
festen Achsenabstand kann Grafana nicht; bei schmalem Bildschirm werden es 2-h-Schritte,
das kW-Raster (1 kW) hängt von der Panelhöhe ab (daher h=18).

`Uhrzeit` ist Zeit seit Mitternacht, nicht Wanduhrzeit: an den Tagen der Zeitumstellung
(23/25 h) sind Achse und Tooltip nach der Umstellung um 1 h verschoben.

### Aufbau von `build_dashboards.py`

- `PRE` – Imports plus `option location = timezone.location(name: TZ)`.
  Ohne das schneiden Tages-/Monats-/Jahresfenster an UTC-Mitternacht.
- `DS` / `DSVAR` – Datenquelle über die versteckte Variable `ds` (Typ datasource,
  `influxdb`) statt fester UID oder `__inputs`; nötig fürs Laden aus Dateien. Gibt es
  mehrere InfluxDB-Datenquellen, `regex` in `DSVAR` setzen.
- `nav_links` / `nav_vars` / `heute_link` / `heute_vars` – Navigation.
- `JAHRE_Q`, `MONATE_Q` (+ `MONATE_RE`), `TAGE_Q` – die Auswahllisten.
- `sm_*` – Abfragen und Panels der drei Dashboards.

## Fallstricke

**Flux**

- `date.add` nimmt `to:`, `date.sub` nimmt `from:`. Verwechslung gibt keinen Fehler,
  sondern eine leere Variable.
- `union()` prüft Typen **statisch**: beide Ströme brauchen identische Spalten, sonst
  „record is missing label _value".
- `pivot` verliert alle Spalten, die weder im rowKey noch im Gruppenschlüssel stehen –
  `_start`/`_stop` gegebenenfalls in den rowKey aufnehmen.
- Nach `pivot` ist die Reihenfolge nicht garantiert: `sort(columns: ["_time"])` anhängen.
- Imports müssen **vor** allen anderen Anweisungen stehen, auch vor `option location`.
- `import` ist reserviert und kann nicht als Spaltenname nach `pivot` verwendet werden.
- Abfragen mit `findColumn` lieferten in Grafana nichts („No data", „unable to find
  field"); Ursache nicht geklärt. Deshalb vermeiden: Anteil als Kette
  `… |> sum() |> map(…)`, Durchschnitt per `join` über eine feste Spalte `k`.

**Grafana**

- Die Einheit aus `fieldConfig.defaults` gilt auch für das Feld der x-Achse – daher
  Overrides mit `unit: none` auf `Tag`, `Monat` und `Uhrzeit`.
- Der Data Explorer begrenzt Ergebnismengen und zeigt Tabellen ohne Zeitspalte als
  „No results". Kommandozeile nehmen.
- Die Pfeile der Zeitauswahl verschieben um die **halbe** Spanne. Deshalb ist die
  Zeitauswahl ausgeblendet und alles läuft über Variablen.
- Folglich kein Zeitreihen-Panel (x-Achse folgt der Zeitauswahl), sondern **Trend**-Panels
  mit eigener x-Achse.
- Variablenwerte mit `&` funktionieren in Link-URLs nicht – daher eine versteckte
  Variable **pro Feld** für die Pfeile. Dashboard-Links interpolieren Variablen.
- Auswahllisten sind absteigend sortiert mit `current: {}`; Grafana wählt den ersten
  Eintrag, also den jüngsten Zeitraum.
- Variablenabfragen auf die Daten lieferten leere Listen; die Listen werden deshalb rein
  rechnerisch mit `array.from` erzeugt.
- Flux-Variablen liefern nur Werte, keine Beschriftung. Für „Sep" statt `09` liefert
  `MONATE_Q` `09|Sep`, und die Variablen-Regex `MONATE_RE` mit benannten Gruppen
  `(?<value>…)`/`(?<text>…)` trennt beides. Links setzen weiterhin `var-monat=09`; im
  Titel `${monat:text}` für den Namen.

## Offene Punkte

Keine.
