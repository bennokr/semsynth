"""Fails if a module has more statements than its budget in size-budget.json.

Budgets only go down: `--update` rewrites them to today's counts, and refuses to raise one unless `--allow-growth`
is given. New modules get a budget on the first `--update`.
"""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUDGET = ROOT / "size-budget.json"
PACKAGES = ("semsynth",)


def count(path: Path) -> int:
    """Statements of a module, not counting docstrings."""
    nodes = list(ast.walk(ast.parse(path.read_text())))
    docstrings = [node for node in nodes if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)]
    return sum(isinstance(node, ast.stmt) for node in nodes) - len(docstrings)


def counts() -> dict[str, int]:
    files = sorted(path for package in PACKAGES for path in (ROOT / package).rglob("*.py"))
    return {str(path.relative_to(ROOT)): count(path) for path in files}


def main(argv: list[str]) -> int:
    current = counts()
    budget: dict[str, int] = json.loads(BUDGET.read_text()) if BUDGET.exists() else {}
    if "--update" in argv:
        grown = {name: n for name, n in current.items() if n > budget.get(name, n)}
        if grown and "--allow-growth" not in argv:
            print("Refusing to raise budgets (use --allow-growth with a reason):", grown)
            return 1
        BUDGET.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        return 0
    over = {name: (n, budget[name]) for name, n in current.items() if name in budget and n > budget[name]}
    missing = sorted(name for name in current if name not in budget)
    for name, (n, limit) in over.items():
        print(f"{name}: {n} statements, budget {limit}")
    for name in missing:
        print(f"{name}: no budget; run scripts/check_size.py --update")
    print(f"total: {sum(current.values())} statements in {len(current)} modules")
    return int(bool(over or missing))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
