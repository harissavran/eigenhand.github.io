#!/usr/bin/env python3
"""
GWR-Import fuer den Eigenhand Property Locator
==============================================

Laedt die oeffentlichen Daten des eidg. Gebaeude- und Wohnungsregisters
(Bundesamt fuer Statistik, Berechtigungsstufe A) und schreibt sie in die
Supabase-Datenbank.

VORHER EINMALIG:  tools/locator_schema.sql im Supabase SQL Editor ausfuehren.

BENUTZUNG
---------
  # 1. Nur hineinschauen: welche Spalten enthaelt der Export wirklich?
  python3 tools/locator_import_gwr.py --inspect

  # 2. Importieren (Kanton Zuerich)
  export SUPABASE_DB_URL='postgresql://postgres.xxxx:PASSWORT@aws-0-eu-central-1.pooler.supabase.com:5432/postgres'
  python3 tools/locator_import_gwr.py

  # Weitere Optionen
  --kanton zh        Kantonskuerzel, oder "ch" fuer die ganze Schweiz (Standard: zh)
  --zip PFAD         bereits heruntergeladene ZIP verwenden statt neu laden
  --inspect          nur Spalten und Zeilenzahlen anzeigen, nichts schreiben

DIE VERBINDUNGSZEICHENFOLGE findest du im Supabase-Dashboard unter
Project Settings > Database > Connection string > URI. Sie gehoert in die
Umgebungsvariable, NIE in eine Datei im Repository und nie ins Frontend.

QUELLENANGABE (Pflicht gemaess Nutzungsbedingungen)
Bundesamt fuer Statistik, Eidgenoessisches Gebaeude- und Wohnungsregister,
oeffentlich zugaengliche Daten: https://www.housing-stat.ch/de/madd/public.html
"""

import argparse
import csv
import io
import os
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

BASE_URL = "https://public.madd.bfs.admin.ch/{kanton}.zip"
QUELLE = ("Bundesamt fuer Statistik, Eidg. Gebaeude- und Wohnungsregister, "
          "oeffentliche Daten (Stufe A)")

# Dateinamen im Export. Erkennung ueber Namensbestandteile, damit kleine
# Aenderungen an der Lieferung den Import nicht brechen.
DATEIEN = {
    "gebaeude": ("gebaeude", "batiment", "edificio"),
    "eingang":  ("eingang", "entree", "entrata"),
    "wohnung":  ("wohnung", "logement", "abitazione"),
}

# Gesuchte Merkmale je Datei. Erster vorhandener Name gewinnt.
# Kuerzel nach Merkmalskatalog GWR (BFS).
SPALTEN = {
    "gebaeude": {
        "egid":    ["EGID"],
        "gdenr":   ["GDENR"],
        "gdename": ["GDENAME", "GGDENAME"],
        "gbauj":   ["GBAUJ"],
        "gbaup":   ["GBAUP"],
        "gastw":   ["GASTW"],
        "garea":   ["GAREA"],
        "ganzwhg": ["GANZWHG"],
        "gkat":    ["GKAT"],
        "gklas":   ["GKLAS"],
        "gkode":   ["GKODE"],
        "gkodn":   ["GKODN"],
    },
    "eingang": {
        "egid":    ["EGID"],
        "edid":    ["EDID"],
        "strname": ["STRNAME", "STRNAMK"],
        "deinr":   ["DEINR"],
        "plz4":    ["PLZ4"],
        "plzname": ["PLZNAME"],
        "doffadr": ["DOFFADR"],
    },
    "wohnung": {
        "egid":    ["EGID"],
        "ewid":    ["EWID"],
        "wstwk":   ["WSTWK"],
        "wazim":   ["WAZIM"],
        "warea":   ["WAREA"],
        "wmehrg":  ["WMEHRG"],
    },
}

# Ohne diese Felder ist der jeweilige Teil wertlos.
PFLICHT = {
    "gebaeude": ["egid"],
    "eingang":  ["egid"],
    "wohnung":  ["egid", "ewid"],
}


def log(msg=""):
    print(msg, flush=True)


def zip_holen(kanton: str, pfad: str | None) -> Path:
    if pfad:
        p = Path(pfad).expanduser()
        if not p.is_file():
            sys.exit(f"ZIP nicht gefunden: {p}")
        log(f"Verwende lokale Datei: {p} ({p.stat().st_size/1e6:.1f} MB)")
        return p
    url = BASE_URL.format(kanton=kanton.lower())
    ziel = Path(tempfile.gettempdir()) / f"gwr_{kanton.lower()}.zip"
    log(f"Lade {url} ...")
    try:
        with urllib.request.urlopen(url, timeout=300) as r, open(ziel, "wb") as f:
            total = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                total += len(chunk)
                print(f"\r  {total/1e6:6.1f} MB", end="", flush=True)
    except Exception as e:
        sys.exit(f"\nDownload fehlgeschlagen: {e}\n"
                 f"Lade die Datei manuell von https://www.housing-stat.ch/de/madd/public.html "
                 f"und starte neu mit --zip PFAD")
    log(f"\n  fertig: {ziel} ({ziel.stat().st_size/1e6:.1f} MB)")
    return ziel


def tabelle_lesen(zf: zipfile.ZipFile, art: str):
    """Findet die Datei im ZIP und liest sie als Liste von dicts (tab-separiert, UTF-8)."""
    name = None
    for n in zf.namelist():
        kurz = n.rsplit("/", 1)[-1].lower()
        if kurz.endswith((".csv", ".dsv", ".txt")) and any(k in kurz for k in DATEIEN[art]):
            name = n
            break
    if not name:
        return None, None, []

    raw = zf.read(name).decode("utf-8-sig", errors="replace")
    # Die Lieferung ist tab-separiert ohne Textqualifizierer; Semikolon als Rueckfall.
    probe = raw[:4000]
    trenner = "\t" if probe.count("\t") >= probe.count(";") else ";"
    leser = csv.DictReader(io.StringIO(raw), delimiter=trenner, quoting=csv.QUOTE_NONE)
    kopf = [h.strip().upper() for h in (leser.fieldnames or [])]
    zeilen = []
    for z in leser:
        zeilen.append({(k or "").strip().upper(): v for k, v in z.items()})
    return name, kopf, zeilen


def mapping(art: str, kopf: list[str]) -> dict:
    """Ordnet Zielspalten den tatsaechlich vorhandenen Kopfzeilen zu."""
    m = {}
    for ziel, kandidaten in SPALTEN[art].items():
        for k in kandidaten:
            if k in kopf:
                m[ziel] = k
                break
    return m


def zahl(v, dez=False):
    if v is None:
        return ""
    s = str(v).strip().replace("'", "").replace("’", "")
    if s in ("", "-", "NULL", "null"):
        return ""
    s = s.replace(",", ".")
    try:
        return str(float(s)) if dez else str(int(float(s)))
    except ValueError:
        return ""


def text(v):
    if v is None:
        return ""
    return str(v).strip()


def main():
    ap = argparse.ArgumentParser(description="GWR-Import fuer den Property Locator")
    ap.add_argument("--kanton", default="zh", help='Kantonskuerzel, oder "ch" (Standard: zh)')
    ap.add_argument("--zip", dest="zippfad", default=None, help="bereits geladene ZIP verwenden")
    ap.add_argument("--inspect", action="store_true", help="nur analysieren, nichts schreiben")
    args = ap.parse_args()

    dburl = os.environ.get("SUPABASE_DB_URL", "").strip()
    if not args.inspect and not dburl:
        sys.exit("SUPABASE_DB_URL ist nicht gesetzt.\n"
                 "Supabase-Dashboard > Project Settings > Database > Connection string > URI\n"
                 "  export SUPABASE_DB_URL='postgresql://...'\n"
                 "Zum reinen Pruefen des Exports genuegt: --inspect")

    zpfad = zip_holen(args.kanton, args.zippfad)
    log()
    log(f"Quelle: {QUELLE}")
    log("=" * 68)

    daten, kopfzeilen, mappings = {}, {}, {}
    with zipfile.ZipFile(zpfad) as zf:
        for art in ("gebaeude", "eingang", "wohnung"):
            name, kopf, zeilen = tabelle_lesen(zf, art)
            if not name:
                log(f"{art:9s}  NICHT im Export enthalten")
                daten[art] = []
                continue
            daten[art] = zeilen
            kopfzeilen[art] = kopf
            m = mapping(art, kopf)
            mappings[art] = m
            fehlt_pflicht = [p for p in PFLICHT[art] if p not in m]
            gefunden = sorted(m.keys())
            fehlt = sorted(set(SPALTEN[art]) - set(m))
            log(f"{art:9s}  {len(zeilen):>9,} Zeilen   Datei: {name.rsplit('/',1)[-1]}")
            log(f"{'':9s}  gefunden: {', '.join(gefunden) or '-'}")
            if fehlt:
                log(f"{'':9s}  fehlt:    {', '.join(fehlt)}")
            if fehlt_pflicht:
                log(f"{'':9s}  ACHTUNG: Pflichtfeld(er) fehlen: {', '.join(fehlt_pflicht)}")

    log("=" * 68)

    whg = daten.get("wohnung") or []
    hat_zim = "wazim" in mappings.get("wohnung", {})
    hat_area = "warea" in mappings.get("wohnung", {})
    if not whg:
        log("ERGEBNIS: Der oeffentliche Export enthaelt KEINE Wohnungsdaten.")
        log("          Die Kandidatensuche filtert dann nur auf Gebaeudeebene")
        log("          (Baujahr, Geschosse, Anzahl Wohnungen) - nicht auf")
        log("          Zimmerzahl und Wohnungsflaeche. Das Cockpit sagt das offen an.")
    else:
        log(f"ERGEBNIS: Wohnungsdaten vorhanden ({len(whg):,} Zeilen).")
        log(f"          Zimmerzahl (WAZIM): {'ja' if hat_zim else 'NEIN'}   "
            f"Wohnungsflaeche (WAREA): {'ja' if hat_area else 'NEIN'}")
        if hat_zim and hat_area:
            log("          Kandidatensuche auf Wohnungsebene ist moeglich.")
        else:
            log("          Kandidatensuche nur eingeschraenkt moeglich.")
    log()

    if args.inspect:
        log("--inspect: es wurde nichts geschrieben.")
        return

    # ---------- Gebaeude mit offizieller Adresse zusammenfuehren ----------
    # Strasse, Hausnummer und PLZ stehen in der Eingangsdatei, nicht in der
    # Gebaeudedatei. Pro EGID wird die offizielle Adresse bevorzugt.
    mg = mappings.get("gebaeude", {})
    me = mappings.get("eingang", {})
    if "egid" not in mg:
        sys.exit("Abbruch: die Gebaeudedatei hat keine EGID-Spalte.")

    adr = {}
    for z in daten.get("eingang") or []:
        egid = zahl(z.get(me.get("egid")))
        if not egid:
            continue
        offiziell = text(z.get(me.get("doffadr"))) in ("1", "true", "True") if "doffadr" in me else False
        if egid in adr and not offiziell:
            continue
        adr[egid] = {
            "strname": text(z.get(me.get("strname"))),
            "deinr":   text(z.get(me.get("deinr"))),
            "plz4":    zahl(z.get(me.get("plz4"))),
            "plzname": text(z.get(me.get("plzname"))),
        }

    tmp = Path(tempfile.mkdtemp(prefix="gwr_"))
    geb_csv, whg_csv = tmp / "gebaeude.csv", tmp / "wohnung.csv"

    GEB_COLS = ["egid", "gdenr", "gdename", "plz4", "plzname", "strname", "deinr",
                "gkode", "gkodn", "gbauj", "gbaup", "gastw", "garea", "ganzwhg",
                "gkat", "gklas"]
    n_geb = 0
    with open(geb_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(GEB_COLS)
        gesehen = set()
        for z in daten["gebaeude"]:
            egid = zahl(z.get(mg["egid"]))
            if not egid or egid in gesehen:
                continue
            gesehen.add(egid)
            a = adr.get(egid, {})
            w.writerow([
                egid,
                zahl(z.get(mg.get("gdenr"))),
                text(z.get(mg.get("gdename"))),
                a.get("plz4", ""), a.get("plzname", ""),
                a.get("strname", ""), a.get("deinr", ""),
                zahl(z.get(mg.get("gkode")), True), zahl(z.get(mg.get("gkodn")), True),
                zahl(z.get(mg.get("gbauj"))), zahl(z.get(mg.get("gbaup"))),
                zahl(z.get(mg.get("gastw"))), zahl(z.get(mg.get("garea"))),
                zahl(z.get(mg.get("ganzwhg"))),
                zahl(z.get(mg.get("gkat"))), zahl(z.get(mg.get("gklas"))),
            ])
            n_geb += 1

    WHG_COLS = ["egid", "ewid", "wstwk", "wazim", "warea", "wmehrg"]
    n_whg = 0
    mw = mappings.get("wohnung", {})
    with open(whg_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(WHG_COLS)
        if whg and "egid" in mw and "ewid" in mw:
            paare = set()
            for z in whg:
                egid, ewid = zahl(z.get(mw["egid"])), zahl(z.get(mw["ewid"]))
                if not egid or not ewid or (egid, ewid) in paare:
                    continue
                paare.add((egid, ewid))
                w.writerow([
                    egid, ewid,
                    zahl(z.get(mw.get("wstwk"))),
                    zahl(z.get(mw.get("wazim")), True),
                    zahl(z.get(mw.get("warea"))),
                    zahl(z.get(mw.get("wmehrg"))),
                ])
                n_whg += 1

    log(f"Aufbereitet: {n_geb:,} Gebaeude, {n_whg:,} Wohnungen")
    log(f"Schreibe nach Supabase ...")

    # Laden ueber Zwischentabellen, damit die bestehenden Daten bis zum
    # erfolgreichen Abschluss unveraendert bleiben.
    sql = f"""
\\set ON_ERROR_STOP on
begin;
create temporary table t_geb (like public.gwr_gebaeude including defaults) on commit drop;
\\copy t_geb ({",".join(GEB_COLS)}) from '{geb_csv}' with (format csv, header true, null '')
delete from public.gwr_gebaeude;
insert into public.gwr_gebaeude ({",".join(GEB_COLS)})
  select {",".join(GEB_COLS)} from t_geb;
"""
    if n_whg:
        sql += f"""
create temporary table t_whg (like public.gwr_wohnung including defaults) on commit drop;
\\copy t_whg ({",".join(WHG_COLS)}) from '{whg_csv}' with (format csv, header true, null '')
delete from public.gwr_wohnung;
insert into public.gwr_wohnung ({",".join(WHG_COLS)})
  select {",".join(WHG_COLS)} from t_whg;
"""
    sql += """
commit;
analyze public.gwr_gebaeude;
"""
    if n_whg:
        sql += "analyze public.gwr_wohnung;\n"
    sql += """
select 'Gebaeude' as tabelle, count(*) from public.gwr_gebaeude
union all
select 'Wohnungen', count(*) from public.gwr_wohnung;
"""

    skript = tmp / "load.sql"
    skript.write_text(sql, encoding="utf-8")
    r = subprocess.run(["psql", dburl, "-v", "ON_ERROR_STOP=1", "-f", str(skript)],
                       capture_output=True, text=True)
    log(r.stdout.strip())
    if r.returncode != 0:
        log(r.stderr.strip())
        sys.exit(f"\npsql ist mit Code {r.returncode} abgebrochen. "
                 f"Es wurde nichts veraendert (Transaktion zurueckgerollt).\n"
                 f"Pruefe: ist tools/locator_schema.sql ausgefuehrt? Stimmt SUPABASE_DB_URL?")

    log()
    log("Import abgeschlossen. Testabfrage im Supabase SQL Editor:")
    log("  select * from public.locator_kandidaten('Niederglatt', 8172, 2006, 5.5, 151, 0.10);")


if __name__ == "__main__":
    main()
