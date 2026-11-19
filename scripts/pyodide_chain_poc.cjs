// Proof of concept: the whole report pipeline with the `chain` backend in Pyodide 0.27.x.
// node scripts/pyodide_chain_poc.cjs <semsynth wheel> <table.csv> <codebook.json> <target>
// Needs `npm i --no-save pyodide@0.27.7`. Writes report.out.json (metric keys and the scorecard) to the working directory.
const fs = require('fs'); const path = require('path');
(async () => {
  const { loadPyodide } = require('pyodide');
  const wheelPath = process.argv[2]; const wheel = path.basename(wheelPath);
  const t0 = Date.now();
  const py = await loadPyodide();
  await py.loadPackage(['micropip', 'numpy', 'pandas', 'scipy', 'scikit-learn', 'pyarrow', 'jinja2', 'pyyaml', 'statsmodels']);
  py.FS.writeFile(`/${wheel}`, fs.readFileSync(wheelPath));
  py.FS.writeFile('/heart.csv', fs.readFileSync(process.argv[3]));
  py.FS.writeFile('/heart.json', fs.readFileSync(process.argv[4]));
  console.log('runtime ready', ((Date.now() - t0) / 1000).toFixed(1) + 's');
  const out = await py.runPythonAsync(`
import micropip, time, json, sys
t=time.time()
await micropip.install("emfs:/${wheel}", deps=False)
await micropip.install(["linked-codebook==0.11.0", "makeprov", "tabulate", "markdown"])
print("install", round(time.time()-t,1))
from semsynth import browser
csv = open("/heart.csv").read(); book = open("/heart.json").read()
cfg = {"pipeline": {"generate_umap": False, "compute_privacy": True, "compute_downstream": True, "compute_joint": True,
                    "compute_baselines": True, "compute_utility": True, "cv_folds": 3},
       "models": [{"name": "chain_mlp", "backend": "chain", "seed": 1, "model": {"learner": "mlp"}},
                  {"name": "chain_hgb", "backend": "chain", "seed": 1, "model": {"learner": "hgb"}}]}
t=time.time()
res = browser.run(csv, config=cfg, codebook=book, target=TARGET, name="heart")
print("run", round(time.time()-t,1))
sc = {k: list(v) for k, v in res["metrics"].items()}
rep = res["files"]["report.md"]; i = rep.find("## Scorecard")
m = res["metrics"]["chain-mlp"]["metrics.json"]
open("/report.md","w").write(rep)
json.dumps({"metric_keys": sorted(m), "cv_folds": m.get("cv",{}).get("folds"), "utility": (m.get("utility") or {}).get("status"), "scorecard": rep[i:i+2600]})
`.replace('TARGET', JSON.stringify(process.argv[5] || 'num')));
  fs.writeFileSync('report.out.json', out); console.log(out.slice(0,200), ((Date.now() - t0) / 1000).toFixed(1) + 's total');
})().catch((e) => { console.error(e); process.exit(1); });
