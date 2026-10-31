# The checks that CI runs. `make check` before every push.
CORE = semsynth/codebook.py semsynth/metrics.py semsynth/missingness.py semsynth/result.py

.PHONY: check lint types ty test size

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
	pytest -q --ignore=tests/test_sparql_playwright.py

# Budgets only go down. Run `python scripts/check_size.py --update` after shrinking a module.
size:
	python scripts/check_size.py
