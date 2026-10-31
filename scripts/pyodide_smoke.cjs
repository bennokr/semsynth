// Runs scripts/pyodide_smoke.py in Pyodide 0.27.x: node scripts/pyodide_smoke.cjs <semsynth wheel>
// Needs `npm i --no-save pyodide@0.27.7` (or PYODIDE_DIR pointing at an installed copy).
const fs = require('fs');
const path = require('path');

const LINKED_CODEBOOK_WHEEL = 'https://bennokr.github.io/linked-codebook/linked_codebook-0.7.0-py3-none-any.whl';

(async () => {
  const { loadPyodide } = require(process.env.PYODIDE_DIR || 'pyodide');
  const wheel = process.argv[2];
  if (!wheel) throw new Error('usage: pyodide_smoke.cjs <semsynth wheel>');
  const py = await loadPyodide();
  await py.loadPackage(['micropip', 'numpy', 'pandas', 'scipy', 'scikit-learn', 'statsmodels', 'pyarrow', 'polars', 'jinja2', 'pyyaml']);
  py.FS.writeFile(`/${path.basename(wheel)}`, fs.readFileSync(wheel));
  py.globals.set('SEMSYNTH_WHEEL', `emfs:/${path.basename(wheel)}`);
  py.globals.set('LINKED_CODEBOOK_WHEEL', LINKED_CODEBOOK_WHEEL);
  const started = Date.now();
  const source = fs.readFileSync(path.join(__dirname, 'pyodide_smoke.py'), 'utf8');
  const result = await py.runPythonAsync(source);
  const out = result.toJs ? Object.fromEntries(result.toJs()) : result;
  console.log(JSON.stringify(out), `${((Date.now() - started) / 1000).toFixed(1)}s`);
  if (!(out.privbayes_rows > 0) || out.missingness_wrapped !== true || !(out.sign_match_rate >= 0)) process.exit(1);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
