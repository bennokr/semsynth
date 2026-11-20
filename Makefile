# The checks that CI runs. `make check` before every push.
CORE = semsynth/utility.py semsynth/crossval.py semsynth/report_scorecard.py semsynth/codebook.py semsynth/iris.py semsynth/catalog.py semsynth/structure.py semsynth/subgroups.py semsynth/benchmark.py semsynth/provenance.py semsynth/browser.py semsynth/metrics.py semsynth/privacy_metrics.py semsynth/distance.py semsynth/uncertainty.py semsynth/joint_fidelity.py semsynth/baselines.py semsynth/missingness.py semsynth/result.py semsynth/model_run.py \
	semsynth/app.py semsynth/backends/metasyn.py semsynth/dataproviders/_helpers.py \
	semsynth/dataproviders/uci_archive.py semsynth/datasets.py semsynth/mappings.py \
	semsynth/specs.py semsynth/sssom_codebook.py semsynth/synthesis.py semsynth/workflow.py

.PHONY: check lint types ty test size site site-bundle

check: lint types test size

lint:
	ruff check .

# Strict on the cleaned core; the other modules join this list as they are cleaned up.
types:
	mypy --strict --ignore-missing-imports --follow-imports=silent $(CORE)

# Advisory: ty is still a beta. Compare its findings with mypy's before it replaces it.
ty:
	-ty check semsynth

test:
	pytest -q

# Budgets only go down. Run `python scripts/check_size.py --update` after shrinking a module.
size:
	python scripts/check_size.py

# The reports of the demo site take hours, so they are built here and not on CI. `make site` builds them with the demo
# configuration, checks them and packs them into dist-site/semsynth-site.tar.gz with its checksum; the commit must be clean.
# Upload both files to a release (see "Publishing the site" in README.md): the Pages workflow pulls the latest release.
site:
	python -m semsynth --conf @prov-config.toml mappings --pipeline-configs configs/demo_config.toml --outdir output/
	$(MAKE) site-bundle

# Check what is in output/ and pack it, without building it again.
site-bundle:
	python scripts/check_output.py output
	python scripts/site_bundle.py pack --output output --docs-data downloads-cache/uciml/45.csv.gz --dest dist-site
