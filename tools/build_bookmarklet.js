/* Baut aus tools/import-bookmarklet.js den Lesezeichen-Link und setzt ihn im Cockpit ein.
   Aufruf: node tools/build_bookmarklet.js  (braucht das npm-Paket terser) */
const fs = require("fs");
const path = require("path");
const { minify } = require("terser");

(async () => {
  const root = path.join(__dirname, "..");
  const src = fs.readFileSync(path.join(__dirname, "import-bookmarklet.js"), "utf8");
  const min = (await minify(src, { compress: true, mangle: true, format: { comments: false } })).code;
  const href = "javascript:" + encodeURIComponent(min);
  const file = path.join(root, "cockpit.html");
  let html = fs.readFileSync(file, "utf8");
  const re = /(<a id="x_bm" [^>]*href=")[^"]*(")/;
  if (!re.test(html)) throw new Error("Lesezeichen-Link (id=x_bm) nicht im Cockpit gefunden");
  html = html.replace(re, (_, a, b) => a + href + b);
  fs.writeFileSync(file, html);
  console.log("Lesezeichen aktualisiert:", href.length, "Zeichen");
})();
