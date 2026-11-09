#!/bin/sh
# Downloads the JavaScript that the catalog page loads (YASGUI and the Comunica query engine) into a directory,
# checking each file against a pinned SHA-256. The Pages workflow runs this; run it yourself to preview the catalog
# locally: scripts/fetch_site_assets.sh output/templates (the catalog page loads ../templates/ next to its output).
# The Comunica file is a moving alias upstream, so a changed download fails here instead of changing the site.
set -eu
dest="${1:?usage: fetch_site_assets.sh <directory>}"
mkdir -p "$dest"

fetch() { # url file sha256
  curl -fsSL --retry 3 "$1" -o "$dest/$2"
  echo "$3  $dest/$2" | sha256sum -c -
}

yasgui=https://cdn.jsdelivr.net/npm/@triply/yasgui@4.2.28/build
fetch "$yasgui/yasgui.min.js" yasgui.min.js 8ac1354b751281f554e58e4370f0da3939d5e6e2a4accd1ebaf49bba04c412ea
fetch "$yasgui/yasgui.min.css" yasgui.min.css 0371a8344c0bc4d81280921df537c186cd33dafff2406b3648c383c484cf04ae
fetch https://rdf.js.org/comunica-browser/versions/v4/engines/query-sparql/comunica-browser.js comunica-browser.js \
  dd19a33e2c03f03913223364272247001654b7c10c8c539afd8e31785019ad4f
