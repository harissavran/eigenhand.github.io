/* Eigenhand Inserat-Import (Lesezeichen)
   Quelle des Lesezeichens im Cockpit (Exposé > Aus Inserat importieren).
   Läuft im Browser auf der Inseratsseite (Homegate, ImmoScout24 u. a.), liest die
   Objektdaten und Bilder aus und schickt sie per postMessage an das Cockpit.
   Nach Änderungen: node tools/build_bookmarklet.js ausführen und den Link im Cockpit ersetzen. */
(function () {
  var TARGET = "https://eigenhand.ch";
  var win = window.open(TARGET + "/cockpit.html#ehimport", "eh_cockpit");

  function clean(s) { return String(s == null ? "" : s).replace(/ /g, " ").replace(/[ \t]+/g, " ").trim(); }
  function stripHtml(h) {
    var d = document.createElement("div");
    d.innerHTML = String(h || "").replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|div|h\d)>/gi, "\n\n").replace(/<\/li>/gi, "\n").replace(/<li[^>]*>/gi, "\n• ");
    return (d.textContent || "").replace(/ /g, " ").replace(/[ \t]+/g, " ").replace(/\n[ \t]+/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  }
  function meta(n) { var m = document.querySelector('meta[property="' + n + '"],meta[name="' + n + '"]'); return m ? m.getAttribute("content") || "" : ""; }

  /* 1. Datenquellen sammeln */
  var cands = [];
  ["__PINIA_INITIAL_STATE__", "__INITIAL_STATE__", "__NEXT_DATA__", "__NUXT__", "__APOLLO_STATE__", "__PRELOADED_STATE__"].forEach(function (k) {
    try { if (window[k] && typeof window[k] === "object") cands.push(window[k]); } catch (e) {}
  });
  Array.prototype.forEach.call(document.querySelectorAll("script"), function (s) {
    var t = s.textContent || "";
    if (!t || t.length < 50) return;
    if (s.type === "application/json" || s.id === "__NEXT_DATA__") { try { cands.push(JSON.parse(t)); } catch (e) {} return; }
    var m = t.indexOf("__INITIAL_STATE__");
    if (m >= 0) { var i = t.indexOf("{", m), j = t.lastIndexOf("}"); if (i > 0 && j > i) { try { cands.push(JSON.parse(t.slice(i, j + 1))); } catch (e) {} } }
  });
  var ld = [];
  Array.prototype.forEach.call(document.querySelectorAll('script[type="application/ld+json"]'), function (s) {
    try { var o = JSON.parse(s.textContent); (Array.isArray(o) ? o : (o["@graph"] || [o])).forEach(function (x) { ld.push(x); }); } catch (e) {}
  });

  /* 2. Inserats-Objekt suchen (das Objekt mit den meisten typischen Feldern) */
  var best = null, bestScore = 0, seen = new WeakSet(), count = 0;
  function walk(o, d) {
    if (!o || typeof o !== "object" || d > 16 || count > 150000) return;
    if (seen.has(o)) return; seen.add(o); count++;
    if (!Array.isArray(o)) {
      var sc = 0;
      if (o.characteristics) sc += 4; if (o.address) sc += 2; if (o.prices || o.price) sc += 2;
      if (o.localization) sc += 3; if (o.numberOfRooms || o.livingSpace) sc += 3; if (o.offerType) sc += 1;
      if (sc > bestScore) { bestScore = sc; best = o; }
    }
    for (var k in o) { if (Object.prototype.hasOwnProperty.call(o, k)) { try { walk(o[k], d + 1); } catch (e) {} } }
  }
  cands.forEach(function (c) { walk(c, 0); });

  function find(o, keys, d) {
    if (!o || typeof o !== "object" || (d || 0) > 8) return undefined;
    for (var i = 0; i < keys.length; i++) { if (o[keys[i]] != null && o[keys[i]] !== "") return o[keys[i]]; }
    for (var k in o) { if (o[k] && typeof o[k] === "object") { var r = find(o[k], keys, (d || 0) + 1); if (r !== undefined) return r; } }
    return undefined;
  }
  function num(v) { if (v == null) return ""; if (typeof v === "object") v = v.value != null ? v.value : (v.amount != null ? v.amount : ""); var n = parseFloat(String(v).replace(/[^0-9.]/g, "")); return isNaN(n) ? "" : n; }

  var out = { v: 1, src: location.href, host: location.hostname, title: "", desc: "", street: "", plz: "", ort: "", kanton: "",
    price: "", rooms: "", area: "", plot: "", year: "", renov: "", floor: "", type: "", features: [], imgs: [], text: "" };

  if (best) {
    var addr = best.address || {};
    out.street = clean(addr.street || addr.streetAddress || "");
    out.plz = clean(addr.postalCode || addr.zip || "");
    out.ort = clean(addr.locality || addr.city || addr.addressLocality || "");
    out.kanton = clean(addr.region || addr.addressRegion || "");
    var ch = best.characteristics || {};
    out.rooms = num(ch.numberOfRooms || best.numberOfRooms);
    out.area = num(ch.livingSpace || ch.netLivingSpace || best.livingSpace);
    out.plot = num(ch.lotSize || ch.plotArea || ch.propertyArea);
    out.year = num(ch.yearBuilt || best.yearBuilt);
    out.renov = num(ch.yearLastRenovated || ch.yearRenovated);
    var fl = ch.floor != null ? ch.floor : best.floor;
    out.floor = fl === 0 ? "EG" : (fl != null && fl !== "" ? fl + ". OG" : "");
    var pr = best.prices || {};
    out.price = num((pr.buy && (pr.buy.price || pr.buy.gross)) || pr.price || best.price || find(best, ["sellingPrice", "purchasePrice"]));
    var cat = best.categories || best.category || best.objectCategory || "";
    out.type = clean(Array.isArray(cat) ? cat.join(",") : cat);
    out.floors = num(ch.numberOfFloors);
    var loc = best.localization || {};
    var lang = loc[loc.primary || "de"] || loc.de || loc[Object.keys(loc).filter(function (k) { return loc[k] && typeof loc[k] === "object"; })[0]] || {};
    var tx = lang.text || lang;
    out.title = clean(tx.title || find(best, ["title"]) || "");
    out.desc = stripHtml(tx.description || find(best, ["description"]) || "");
    (lang.attachments || find(best, ["attachments", "images", "pictures"]) || []).forEach(function (a) {
      var u = typeof a === "string" ? a : (a && (a.url || a.src || a.href));
      if (u && (!a.type || /IMAGE/i.test(a.type))) out.imgs.push(u);
    });
    for (var key in ch) { if (ch[key] === true) out.features.push(key); }
  }

  /* 3. JSON-LD und Meta-Tags als Ergänzung */
  ld.forEach(function (x) {
    if (!out.title && x.name) out.title = clean(x.name);
    if (!out.desc && x.description) out.desc = stripHtml(x.description);
    var a = x.address || (x.itemOffered && x.itemOffered.address) || {};
    if (!out.plz && a.postalCode) out.plz = clean(a.postalCode);
    if (!out.ort && a.addressLocality) out.ort = clean(a.addressLocality);
    if (!out.street && a.streetAddress) out.street = clean(a.streetAddress);
    if (!out.rooms && x.numberOfRooms) out.rooms = num(x.numberOfRooms);
    if (!out.area && x.floorSize) out.area = num(x.floorSize);
    var off = x.offers || {}; if (!out.price && (off.price || (off.priceSpecification && off.priceSpecification.price))) out.price = num(off.price || off.priceSpecification.price);
    var im = x.image || x.photo; (Array.isArray(im) ? im : (im ? [im] : [])).forEach(function (i) { var u = typeof i === "string" ? i : (i.url || i.contentUrl); if (u) out.imgs.push(u); });
  });
  if (!out.title) out.title = clean(meta("og:title") || (document.querySelector("h1") || {}).textContent || document.title);
  if (!out.desc) out.desc = stripHtml(meta("og:description") || meta("description"));

  /* 4. Bilder aus der Seite (grosse Fotos, höchste Auflösung aus srcset) */
  var fromData = out.imgs.length >= 3;
  if (!fromData) Array.prototype.forEach.call(document.querySelectorAll("img, source"), function (el) {
    var u = el.currentSrc || el.src || "";
    var ss = el.getAttribute("srcset") || el.getAttribute("data-srcset") || "";
    if (ss) { var parts = ss.split(",").map(function (p) { var q = p.trim().split(/\s+/); return { u: q[0], w: parseFloat(q[1]) || 0 }; }).filter(function (p) { return p.u; }).sort(function (a, b) { return b.w - a.w; }); if (parts[0]) u = parts[0].u; }
    try { u = new URL(u, location.href).href; } catch (e) { return; }
    var w = el.naturalWidth || el.width || 0;
    if (u && /^https?:/.test(u) && (w >= 400 || ss) && !/logo|icon|avatar|sprite|placeholder|\.svg/i.test(u)) out.imgs.push(u);
  });
  if (meta("og:image")) out.imgs.push(meta("og:image"));
  var uniq = [], keys = [];
  out.imgs.forEach(function (u) {
    try { u = new URL(u, location.href).href; } catch (e) { return; }
    var k = u.split("?")[0].split("/").pop();
    if (keys.indexOf(k) < 0) { keys.push(k); uniq.push(u); }
  });
  out.imgs = uniq.slice(0, 30);
  out.text = clean((document.querySelector("main") || document.body).innerText || "").slice(0, 12000);
  out.textRaw = ((document.querySelector("main") || document.body).innerText || "").slice(0, 12000);

  /* 5. Bilder als Datei mitgeben, wenn die Seite es erlaubt (sonst bleibt der Link) */
  function toData(u) {
    return new Promise(function (res) {
      var done = false; var t = setTimeout(function () { if (!done) { done = true; res(null); } }, 8000);
      var img = new Image(); img.crossOrigin = "anonymous";
      img.onload = function () {
        try {
          var s = Math.min(1, 1800 / Math.max(img.naturalWidth, img.naturalHeight));
          var c = document.createElement("canvas"); c.width = Math.round(img.naturalWidth * s); c.height = Math.round(img.naturalHeight * s);
          c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
          var d = c.toDataURL("image/jpeg", 0.85); if (!done) { done = true; clearTimeout(t); res(d); }
        } catch (e) { if (!done) { done = true; clearTimeout(t); res(null); } }
      };
      img.onerror = function () { if (!done) { done = true; clearTimeout(t); res(null); } };
      img.src = u;
    });
  }
  Promise.all(out.imgs.map(toData)).then(function (datas) {
    out.imgData = datas;
    if (!win) {
      try { navigator.clipboard.writeText(JSON.stringify(Object.assign({}, out, { imgData: [] }))); } catch (e) {}
      alert("Eigenhand: Das Cockpit konnte nicht geöffnet werden (Pop-up blockiert). Die Daten sind in der Zwischenablage – im Cockpit unter Exposé > «Aus Inserat importieren» einfügen.");
      return;
    }
    var tries = 0, ack = false;
    window.addEventListener("message", function (e) { if (e.origin === TARGET && e.data === "ehimport-ok") ack = true; });
    (function send() {
      if (ack || tries > 120) return;
      tries++;
      try { win.postMessage({ type: "ehimport", data: out }, TARGET); } catch (e) {}
      setTimeout(send, 500);
    })();
  });
})();
