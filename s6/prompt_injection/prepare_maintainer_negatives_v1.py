"""Freeze unmodified maintainer-document excerpts as benign review candidates.

These are NOT automatically labeled benign training examples. No repository code
or instructions from these documents are executed.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from supervised_data import ROOT


DATA = ROOT / "data/bipia/maintainer_negatives_v1"
SOURCES = {
    "requests": {"checkout": ROOT / "external/requests-benign", "commit": "611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60",
                 "license": "Apache-2.0", "paths": ("README.md", "docs/dev/contributing.rst", "docs/community/release-process.rst")},
    "flask": {"checkout": ROOT / "external/flask-benign", "commit": "d73fa1cdcbd8b1465c151db8924ba58b1dd14e35",
              "license": "BSD-3-Clause", "paths": ("docs/testing.rst", "docs/web-security.rst", "docs/quickstart.rst")},
    "pytest": {"checkout": ROOT / "external/pytest-benign", "commit": "b1de564f337c63db919a65253b931dd099909618",
               "license": "MIT", "paths": ("CONTRIBUTING.rst", "doc/en/how-to/usage.rst", "doc/en/explanation/ci.rst")},
}
KEYWORDS = re.compile(r"\b(?:must|should|required|run|test|install|security|token|secret|permission|review|release|commit|delete|remove|ignore|build|ci)\b", re.I)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def paragraphs(text: str) -> list[tuple[int, int, str]]:
    lines = text.splitlines()
    output = []
    start = None
    for index, line in enumerate(lines + [""], 1):
        if line.strip():
            if start is None:
                start = index
        elif start is not None:
            block = "\n".join(lines[start - 1:index - 1]).strip()
            if 90 <= len(block) <= 1400 and KEYWORDS.search(block):
                output.append((start, index - 1, block))
            start = None
    return output


def prepare() -> None:
    if DATA.exists():
        raise FileExistsError("Maintainer candidate set already frozen")
    rows = []
    source_files = {}
    for repo, config in SOURCES.items():
        checkout = config["checkout"]
        actual_commit = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        if actual_commit != config["commit"]:
            raise ValueError(f"Source commit changed for {repo}: {actual_commit}")
        candidates = []
        for relative in config["paths"]:
            path = checkout / relative
            raw = path.read_bytes()
            source_files[f"{repo}/{relative}"] = sha(raw)
            for first, last, content in paragraphs(raw.decode("utf-8")):
                keyword_count = len({match.group().lower() for match in KEYWORDS.finditer(content)})
                candidates.append((keyword_count, relative, first, last, content))
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        chosen = []
        per_file = {}
        for score, relative, first, last, content in candidates:
            if per_file.get(relative, 0) >= 4:
                continue
            chosen.append((score, relative, first, last, content))
            per_file[relative] = per_file.get(relative, 0) + 1
            if len(chosen) == 10:
                break
        if len(chosen) != 10 or len(per_file) < 3:
            raise ValueError(f"Insufficient diverse candidate excerpts for {repo}")
        for _, relative, first, last, content in chosen:
            rows.append({"source_id": f"{repo}/{relative}:{first}-{last}", "repo": repo,
                         "path": relative, "first_line": first, "last_line": last,
                         "source_file_sha256": source_files[f"{repo}/{relative}"],
                         "content": content, "label": "unreviewed_benign_candidate"})
    if len(rows) != 30 or len({r["source_id"] for r in rows}) != 30:
        raise ValueError("Candidate sample count or uniqueness mismatch")
    raw = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    protocol = {"status": "FROZEN_BEFORE_ANNOTATION", "selection": "top keyword-diverse paragraphs, max four per file; not detector-selected",
                "count": len(rows), "repos": {key: {"url": f"https://github.com/{'psf/requests' if key == 'requests' else 'pallets/flask' if key == 'flask' else 'pytest-dev/pytest'}",
                                               "commit": cfg["commit"], "license": cfg["license"]}
                                         for key, cfg in SOURCES.items()},
                "source_file_sha256": source_files, "samples_sha256": sha(raw),
                "limitations": ["Unmodified maintainer-document excerpts are candidates, not independently adjudicated benign labels.",
                                "Keyword-based sampling enriches instruction-like text; it is not a random prevalence sample.",
                                "Selection is based on text and source only, never detector output."]}
    DATA.mkdir(parents=True, exist_ok=False)
    (DATA / "samples.jsonl").write_bytes(raw)
    (DATA / "protocol.json").write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FROZEN {len(rows)} candidate excerpts; sha256={sha(raw)}")


if __name__ == "__main__":
    prepare()
