"""Reproducible structural inventory; findings are review candidates, not dead-code proof."""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import hashlib
from pathlib import Path

from s6.engineering.artifacts import new_run, read_json, write_json

ROOT = Path(__file__).resolve().parents[2]


def inventory(root: Path) -> dict:
    files, functions = [], []
    clones = defaultdict(list)
    protected = read_json(root / "s6/engineering/frozen_assets.json")["files"]
    for path in sorted((root / "s6").rglob("*.py")):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        relative = path.relative_to(root).as_posix()
        files.append({"path": relative, "lines": len(source.splitlines()),
                      "protection": "explicitly_protected" if relative in protected else "requires_review",
                      "imports": sorted({n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module})})
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            lines = node.end_lineno - node.lineno + 1
            branches = sum(isinstance(n, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.IfExp)) for n in ast.walk(node))
            item = {"path": relative, "name": node.name, "line": node.lineno,
                    "lines": lines, "branch_nodes": branches}
            functions.append(item)
            if lines >= 8:
                digest = hashlib.sha256(ast.dump(ast.Module(body=node.body, type_ignores=[])).encode()).hexdigest()
                clones[digest].append(item)
    frontends = []
    for path in [root / "index.html", *sorted((root / "s6").rglob("*.html"))]:
        text = path.read_text(encoding="utf-8")
        frontends.append({"path": path.relative_to(root).as_posix(), "lines": len(text.splitlines()),
                          "inline_script_blocks": text.count("<script>"), "inline_style_blocks": text.count("<style>")})
    return {"scope": "s6 production Python plus HTML; tests and external data excluded",
            "limitations": "Line/branch counts are heuristics, not formal complexity; AST clones may be intentional frozen copies; no automatic deletion recommendation.",
            "files": sorted(files, key=lambda r:r["lines"], reverse=True),
            "functions": sorted(functions, key=lambda r:r["lines"], reverse=True),
            "exact_body_clone_groups": [group for group in clones.values() if len(group) > 1],
            "frontends": frontends}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label", choices=("before_v1", "after_v1"))
    args = parser.parse_args()
    out = ROOT / "results/engineering" / f"structure_{args.label}"
    with new_run(out, {"kind": "structure-audit", "label": args.label}):
        report = inventory(ROOT)
        write_json(out / "inventory.json", report)
        print({"files": len(report["files"]), "functions": len(report["functions"]),
               "clone_groups": len(report["exact_body_clone_groups"]), "largest_functions": report["functions"][:5],
               "frontends": report["frontends"]})


if __name__ == "__main__":
    main()
