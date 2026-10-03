"""Validated and atomic local research artifacts."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import tempfile
from typing import Callable, Iterator, BinaryIO


def file_sha256(path: Path) -> str:
    """Hash a file without loading model weights into Python memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_hash(path: Path, expected: str) -> None:
    if file_sha256(path) != expected:
        raise ValueError(f"Artifact hash mismatch: {path}")


def read_json(path: Path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def atomic_binary(path: Path, writer: Callable[[BinaryIO], None]) -> None:
    """Publish a whole file, or leave its prior version unchanged on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".s6-", delete=False) as stream:
            temporary = Path(stream.name)
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()  # Only the exact temporary file created by this call.


def write_json(path: Path, value: object) -> None:
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    atomic_binary(path, lambda stream: stream.write(raw))


def environment() -> dict:
    packages = {}
    for name in ("numpy", "scipy", "scikit-learn", "torch", "transformers", "tokenizers"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {"python": platform.python_version(), "platform": platform.platform(), "packages": packages}


@contextmanager
def new_run(path: Path, protocol: dict) -> Iterator[Path]:
    """Claim a version exactly once; failed runs remain inspectable, never overwritten."""
    path.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    write_json(path / "status.json", {"state": "RUNNING", "started": started})
    try:
        write_json(path / "protocol.json", {**protocol, "environment": environment()})
        yield path
    except BaseException as error:
        write_json(path / "status.json", {"state": "FAILED", "started": started,
                                         "error_type": type(error).__name__, "error": str(error)})
        raise
    else:
        write_json(path / "status.json", {"state": "COMPLETE", "started": started,
                                         "finished": datetime.now(timezone.utc).isoformat()})
