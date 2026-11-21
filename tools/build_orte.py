#!/usr/bin/env python3
"""Erzeugt die Ortsseiten von Eigenhand aus tools/orte.json.

Aufruf im Projektordner:   python3 tools/build_orte.py

Erzeugt pro Ort eine Datei immobilie-verkaufen-<slug>.html, aktualisiert die
Ortsliste in der sitemap.xml und die Footer-Links in index.html und ratgeber.html.
"""

import json
import os
import re
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://eigenhand.ch"
PREISE = {"Selbst": 1490, "Pro": 2490, "Begleitet": 6900}
PROVISION = 0.025  # Vergleichswert Maklerprovision


def chf(v):
    return "CHF " + f"{round(v):,}".replace(",", "'")


def esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def seite(o, alle):
    name, slug = o["name"], o["slug"]
    flaeche = o["beispiel_flaeche"]
    ist_haus = flaeche >= 130
    typ = "Haus" if ist_haus else "Wohnung"
    satz = o["h"] if ist_haus else o["w"]
    wert = round(flaeche * satz / 10000) * 10000
    prov = wert * PROVISION
    spar_b = prov - PREISE["Begleitet"]
    spar_s = prov - PREISE["Selbst"]

    titel = f"Immobilie verkaufen in {name} – ohne Makler, zum Festpreis | Eigenhand"
    beschr = (f"Wohnung oder Haus in {name} ohne Maklerprovision verkaufen: Festpreis ab "
              f"CHF 1'490 statt rund {chf(prov)} Provision. Richtwerte, Ablauf und "
              f"kostenlose Wertberechnung.")
    url = f"{BASE}/immobilie-verkaufen-{slug}.html"

    nachbarn = [x for x in alle if x["slug"] != slug][:5]
    nachbar_links = " · ".join(
        f'<a href="immobilie-verkaufen-{n["slug"]}.html">{esc(n["name"])}</a>' for n in nachbarn)

    faq = [
        (f"Was kostet es, eine Immobilie in {name} ohne Makler zu verkaufen?",
         f"Bei Eigenhand zahlen Sie einen Festpreis: CHF 1'490 für das Paket «Selbst», "
         f"CHF 2'490 für «Pro» und CHF 6'900 für «Begleitet». Ein Makler verlangt bei einem "
         f"Objekt um {chf(wert)} mit 2.5 Prozent rund {chf(prov)}. Dazu kommen unabhängig vom "
         f"Anbieter die Notariats- und Grundbuchgebühren sowie die Grundstückgewinnsteuer."),
        (f"Wer beurkundet den Kaufvertrag in {name}?",
         f"Im Kanton Zürich muss jeder Kaufvertrag öffentlich beurkundet werden, mit oder ohne "
         f"Makler. Zuständig ist das Notariat und Grundbuchamt des Kreises, in dem die "
         f"Liegenschaft liegt; {name} gehört zum Bezirk {o['bezirk']}. Die Grundstückgewinnsteuer "
         f"erhebt im Kanton Zürich die Gemeinde, in diesem Fall also {name}."),
        (f"Wie lange dauert ein Verkauf in {name}?",
         "Von der Aufschaltung bis zur Beurkundung dauert es je nach Objekt und Preis meist "
         "zwei bis sechs Monate. Den grössten Einfluss hat ein realistischer Startpreis: Ein zu "
         "hoher Preis kostet die ersten Wochen, in denen ein Inserat am meisten gesehen wird."),
    ]

    faq_html = "\n".join(
        f'    <details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in faq)

    ld_faq = json.dumps({
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": q,
                        "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]
    }, ensure_ascii=False)

    ld_service = json.dumps({
        "@context": "https://schema.org", "@type": "Service",
        "name": f"Immobilienverkauf zum Festpreis in {name}",
        "serviceType": "Immobilienverkauf ohne Maklerprovision",
        "provider": {"@type": "RealEstateAgent", "name": "Eigenhand", "url": BASE + "/",
                     "email": "info@eigenhand.ch",
                     "address": {"@type": "PostalAddress", "postalCode": "8302",
                                 "addressLocality": "Kloten", "addressRegion": "ZH",
                                 "addressCountry": "CH"}},
        "areaServed": {"@type": "City", "name": name, "postalCode": o["plz"],
                       "addressRegion": "ZH", "addressCountry": "CH"},
        "url": url,
        "offers": [{"@type": "Offer", "name": k, "price": str(v), "priceCurrency": "CHF"}
                   for k, v in PREISE.items()]
    }, ensure_ascii=False)

    ld_crumb = json.dumps({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Startseite", "item": BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": f"Verkaufen in {name}", "item": url}]
    }, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="de-CH">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(titel)}</title>
<meta name="description" content="{esc(beschr)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:url" content="{url}">
<meta property="og:title" content="Immobilie verkaufen in {esc(name)} – zum Festpreis statt Provision">
<meta property="og:description" content="{esc(beschr)}">
<meta property="og:image" content="{BASE}/img/hero.jpg">
<meta property="og:site_name" content="Eigenhand">
<meta property="og:locale" content="de_CH">
<meta name="theme-color" content="#123D2F">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/img/favicon-32.png">
<link rel="apple-touch-icon" href="/img/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/orte.css">
<script type="application/ld+json">{ld_service}</script>
<script type="application/ld+json">{ld_faq}</script>
<script type="application/ld+json">{ld_crumb}</script>
</head>
<body>

<header>
  <div class="bar">
    <a class="brand" href="/" aria-label="Eigenhand Startseite">
      <img src="/img/logo.png" alt="" style="height:27px;width:auto;display:block">Eigenhand
    </a>
    <nav class="links" aria-label="Hauptnavigation">
      <a href="/#ablauf">Ablauf</a>
      <a href="/#preise">Preise</a>
      <a href="/ratgeber.html">Ratgeber</a>
      <a href="/?g={slug}#bewertung" class="btn">Wert berechnen</a>
    </nav>
  </div>
</header>

<div class="wrap">
  <p class="crumb"><a href="/">Eigenhand</a> › Verkaufen in {esc(name)}</p>

  <div class="top">
    <h1>Immobilie verkaufen in {esc(name)} – ohne Makler, zum Festpreis</h1>
    <p class="lead">{esc(o['intro'])}</p>
    <div class="cta">
      <a href="/?g={slug}#bewertung" class="btn">Was ist mein Zuhause wert?</a>
      <a href="/#preise" class="btn sec">Pakete ansehen</a>
    </div>
    <p class="hint">Kostenlos · Richtwert und Ersparnis in 60 Sekunden · ohne Anruf</p>
  </div>
</div>

<div class="wrap">
  <section>
    <h2>Was Sie in {esc(name)} sparen</h2>
    <p class="body">Die Maklerprovision wird in Prozent des Verkaufspreises berechnet und steigt
      deshalb mit dem Wert Ihrer Immobilie. Bei Eigenhand zahlen Sie unabhängig vom Preis einen
      festen Betrag. Ein Beispiel für {esc(name)}:</p>

    <div class="calc">
      <div class="row"><span>{flaeche} m² {typ} in {esc(name)}<small>rund {chf(satz)} pro m² (Richtwert)</small></span><b>{chf(wert)}</b></div>
      <div class="row"><span>Makler, 2.5 % Provision</span><b>{chf(prov)}</b></div>
      <div class="row"><span>Eigenhand «Begleitet»<small>wir übernehmen Besichtigungen und Verhandlung</small></span><b>{chf(PREISE['Begleitet'])}</b></div>
      <div class="row tot"><span>Bleibt Ihnen mehr</span><b>{chf(spar_b)}</b></div>
      <p class="note">Machen Sie mehr selbst («Selbst», {chf(PREISE['Selbst'])}), sind es bis {chf(spar_s)}.
        Vor Steuern. Richtwerte, Stand November 2026, keine amtlichen Daten und keine verbindliche
        Bewertung.{' Bei Häusern ist der Landwert nicht eingerechnet.' if ist_haus else ''}</p>
    </div>

    <div class="prices">
      <div><span>Richtwert Eigentumswohnungen in {esc(name)}</span><b>ca. {chf(o['w'])} / m²</b></div>
      <div><span>Richtwert Häuser in {esc(name)}</span><b>ca. {chf(o['h'])} / m²</b></div>
    </div>
    <p class="hint"><a href="/?g={slug}#bewertung">Mit Ihren eigenen Angaben rechnen →</a></p>
  </section>

  <section>
    <h2>Der Markt in {esc(name)}</h2>
    <p class="body">{esc(o['markt'])}</p>
    <div class="tip"><b>Tipp für Ihr Inserat:</b> {esc(o['tipp'])}</div>
  </section>

  <section>
    <h2>So läuft der Verkauf ab</h2>
    <p class="body">Sie bleiben Verkäufer und entscheiden alles selbst. Eigenhand übernimmt genau
      so viel, wie Sie möchten.</p>
    <div class="pk">
      <a href="/#preise"><span class="n">Selbst</span><span class="d">Exposé, Preisschätzung und
        Inserate auf Homegate, ImmoScout24 und Acheter-Louer. Anfragen und Besichtigungen
        übernehmen Sie.</span><span class="p">CHF 1'490</span></a>
      <a href="/#preise"><span class="n">Pro</span><span class="d">Zusätzlich professionelle
        Objektfotos, ausführliche Marktanalyse und Beratung bei Angeboten und Verhandlung.
        Inserat online, bis verkauft ist.</span><span class="p">CHF 2'490</span></a>
      <a href="/#preise"><span class="n">Begleitet</span><span class="d">Wir führen die
        Besichtigungen in {esc(name)} durch, prüfen die Käufer, verhandeln und bereiten die
        Notariatsunterlagen vor.</span><span class="p">CHF 6'900</span></a>
    </div>
    <p class="hint">{esc(o['lokal'])}</p>
  </section>

  <section>
    <h2>Häufige Fragen zum Verkauf in {esc(name)}</h2>
{faq_html}
  </section>

  <div class="end">
    <h2>Was ist Ihre Immobilie in {esc(name)} wert?</h2>
    <p>Vier Angaben genügen. Sie sehen sofort einen Richtwert und wie viel Ihnen gegenüber einem
      Makler bleibt. Danach erhalten Sie auf Wunsch gratis eine genaue Einschätzung per E-Mail,
      innert 24 Stunden und ohne Anruf.</p>
    <a href="/?g={slug}#bewertung" class="btn">Jetzt kostenlos berechnen</a>
  </div>

  <p class="nearby">Auch in der Nähe: {nachbar_links}</p>
</div>

<footer>
  <div class="row">
    <span><strong style="color:#fff">Eigenhand</strong> · Festpreis statt Provision. Schwerpunkt Kanton Zürich, Deutschschweiz auf Anfrage.</span>
    <span><a href="/ratgeber.html">Ratgeber</a> · <a href="/#impressum">Impressum</a> · <a href="/#datenschutz">Datenschutz</a> · <a href="/#agb">AGB</a> · <a href="mailto:info@eigenhand.ch">info@eigenhand.ch</a></span>
  </div>
</footer>

</body>
</html>
"""


def footer_links(orte):
    links = " · ".join(
        f'<a href="/immobilie-verkaufen-{o["slug"]}.html">{o["name"]}</a>' for o in orte)
    return ('<div class="wrap row orte-links"><span>Verkaufen in Ihrer Gemeinde: '
            + links + "</span></div>")


def main():
    data = json.load(open(os.path.join(ROOT, "tools", "orte.json"), encoding="utf-8"))
    orte = data["orte"]
    heute = date.today().isoformat()

    for o in orte:
        pfad = os.path.join(ROOT, f"immobilie-verkaufen-{o['slug']}.html")
        open(pfad, "w", encoding="utf-8").write(seite(o, orte))
        print("geschrieben:", os.path.basename(pfad))

    # sitemap.xml
    eintraege = "".join(
        f"\n  <url>\n    <loc>{BASE}/immobilie-verkaufen-{o['slug']}.html</loc>"
        f"\n    <lastmod>{heute}</lastmod>\n    <changefreq>monthly</changefreq>"
        f"\n    <priority>0.8</priority>\n  </url>" for o in orte)
    sm = open(os.path.join(ROOT, "sitemap.xml"), encoding="utf-8").read()
    sm = re.sub(r"\n\s*<!-- orte:start -->.*?<!-- orte:end -->", "", sm, flags=re.S)
    sm = sm.replace("</urlset>",
                    f"  <!-- orte:start -->{eintraege}\n  <!-- orte:end -->\n</urlset>")
    open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8").write(sm)
    print("sitemap.xml aktualisiert")

    # Footer-Links auf Startseite und Ratgeber
    block = footer_links(orte)
    for datei in ("index.html", "ratgeber.html"):
        pfad = os.path.join(ROOT, datei)
        if not os.path.exists(pfad):
            continue
        html = open(pfad, encoding="utf-8").read()
        html = re.sub(r"\n?\s*<!-- orte:start -->.*?<!-- orte:end -->", "", html, flags=re.S)
        html = html.replace("</footer>",
                            f"  <!-- orte:start -->\n  {block}\n  <!-- orte:end -->\n</footer>", 1)
        open(pfad, "w", encoding="utf-8").write(html)
        print(datei, "Footer aktualisiert")


if __name__ == "__main__":
    main()
