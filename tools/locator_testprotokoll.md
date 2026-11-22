# Property Locator – Testprotokoll

## Was bereits getestet ist

Diese Prüfungen liefen automatisiert in der Entwicklungsumgebung und sind bestanden.

| Prüfung | Ergebnis |
| --- | --- |
| Parser gegen 20 Textvarianten in Schweizer Inseratsformaten | 20/20 bestanden |
| Portal- und Inseratsnummernerkennung (Homegate, ImmoScout24, Newhome, Neho, Flatfox, ungültiger Link) | bestanden |
| Koordinatenumrechnung LV95 → WGS84 gegen swisstopo-Referenzpunkt 2600000/1200000 | 46.95108 / 7.43864, Abweichung < 1 m |
| JavaScript-Syntax des gesamten `cockpit.html` | fehlerfrei |
| Alle 53 DOM-Referenzen des Locators haben ein Gegenstück im HTML | vollständig |
| `locator_schema.sql` gegen den echten PostgreSQL-Parser | Syntax und PL/pgSQL-Body akzeptiert |
| Importskript: Zahlenformate, Dateierkennung im ZIP, Adressjoin, Dublettenabweisung, Abbruch ohne DB-URL | bestanden |

Der Parser-Selbsttest läuft auch im Browser: Cockpit öffnen, Entwicklerkonsole,
`loSelfTest()` eingeben. Die Ergebnisse erscheinen unten im Locator-Tab.

## Was noch nicht getestet ist

Die Entwicklungsumgebung hatte keinen Netzzugang zu `api3.geo.admin.ch`,
`public.madd.bfs.admin.ch` und den Immobilienportalen. Darum ist **nicht**
getestet:

- die echten Antwortformate der GeoAdmin-API (Feldnamen in `SearchServer` und
  `identify`),
- die Kartenkacheln von swisstopo,
- der tatsächliche Spaltenumfang des öffentlichen GWR-Exports,
- der Durchlauf mit echten Inseraten.

Das sind die Punkte, die der Abnahmetest unten abdeckt. Wenn ein Feldname der
API abweicht, zeigt der Locator das als nicht verifizierbar an und bricht nicht
ab – aber die Information fehlt dann. Konsole offen halten und Fehlermeldungen
notieren.

## Reihenfolge der Inbetriebnahme

1. `tools/locator_schema.sql` im Supabase SQL Editor ausführen.
2. `python3 tools/locator_import_gwr.py --inspect` – zeigt, welche Felder der
   öffentliche Export enthält. Hier steht, ob Zimmerzahl und Wohnungsfläche
   verfügbar sind.
3. `export SUPABASE_DB_URL='postgresql://...'` setzen, dann
   `python3 tools/locator_import_gwr.py` – Import Kanton Zürich.
4. Im SQL Editor gegenprüfen:
   `select * from public.locator_kandidaten('Niederglatt', 8172, 2006, 5.5, 151, 0.10);`
5. Abnahmetest mit 20 echten Inseraten, Tabelle unten ausfüllen.

## Abnahmetest mit 20 echten Inseraten

Die Mischung bewusst breit halten: Einfamilienhäuser, Eigentumswohnungen,
Neubauten, alte Gebäude, Mehrfamilienhäuser, Inserate mit und ohne Adresse,
sowie Inserate mit sehr wenigen Angaben. Mindestens fünf aus einer kleinen
Gemeinde und fünf aus Zürich oder Winterthur – dort zeigt sich, wie stark die
Kandidatenmenge auseinandergeht.

Keine Ergebnisse schätzen. Ist ein Inserat nicht abrufbar oder fehlt eine
Angabe, wird das so eingetragen.

| Nr. | Portal | Objektart | Gemeinde | Inserat eingelesen | Merkmale extrahiert | Geodaten gefunden | Standort verifiziert | Mehrdeutigkeit erkannt | Fehler korrekt angezeigt | Kandidaten (Anzahl) | Bemerkung |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 |  |  |  |  |  |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |  |  |  |  |  |
| 3 |  |  |  |  |  |  |  |  |  |  |  |
| 4 |  |  |  |  |  |  |  |  |  |  |  |
| 5 |  |  |  |  |  |  |  |  |  |  |  |
| 6 |  |  |  |  |  |  |  |  |  |  |  |
| 7 |  |  |  |  |  |  |  |  |  |  |  |
| 8 |  |  |  |  |  |  |  |  |  |  |  |
| 9 |  |  |  |  |  |  |  |  |  |  |  |
| 10 |  |  |  |  |  |  |  |  |  |  |  |
| 11 |  |  |  |  |  |  |  |  |  |  |  |
| 12 |  |  |  |  |  |  |  |  |  |  |  |
| 13 |  |  |  |  |  |  |  |  |  |  |  |
| 14 |  |  |  |  |  |  |  |  |  |  |  |
| 15 |  |  |  |  |  |  |  |  |  |  |  |
| 16 |  |  |  |  |  |  |  |  |  |  |  |
| 17 |  |  |  |  |  |  |  |  |  |  |  |
| 18 |  |  |  |  |  |  |  |  |  |  |  |
| 19 |  |  |  |  |  |  |  |  |  |  |  |
| 20 |  |  |  |  |  |  |  |  |  |  |  |

### Auswertung

- Inserate eingelesen: ___ / 20
- Merkmale vollständig extrahiert: ___ / 20
- Standort amtlich bestätigt: ___ / 20
- Kandidatenmenge 1–5 Gebäude: ___ / 20
- Median der Kandidatenmenge: ___

Die Quote „amtlich bestätigt“ wird bei anonymisierten Inseraten nahe null
liegen, weil eine Bestätigung eine im Inserat genannte Adresse voraussetzt.
Die aussagekräftige Zahl ist die Kandidatenmenge: je kleiner, desto brauchbarer.
Ab etwa zehn Kandidaten ist das Ergebnis praktisch wertlos – dann lieber
Merkmale ergänzen als die Liste durchgehen.

## Grenzen, die sich nicht wegtesten lassen

- Die GWR-Wohnungsfläche ist anders definiert als die Flächenangabe im Inserat.
  Der Abgleich läuft mit ±10 % Toleranz; exakte Übereinstimmung ist nicht zu
  erwarten.
- Baujahr im Inserat und im GWR weichen ab, wenn das Inserat das Bezugsjahr
  nennt. Die Suche deckt deshalb ±1 Jahr ab.
- Die Grundstücksnummer liefert die GeoAdmin-API nicht als abfragbares
  Attribut. Der Locator verlinkt in den amtlichen Kataster; die Nummer wird
  dort abgelesen und von Hand nachgetragen.
- Eigentümerdaten führt der Locator nicht. Eine Auskunft zu einem einzelnen
  Grundstück erteilt das Grundbuchamt auf Gesuch.
