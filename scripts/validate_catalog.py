#!/usr/bin/env python3
"""Validate the hub catalog against checked-out Git submodules."""

import json
import pathlib
import re
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]


def gitmodules():
    text = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    return dict(re.findall(r"path\s*=\s*(\S+)\s*\n\s*url\s*=\s*(\S+)", text))


def main():
    catalog = json.loads((ROOT / "catalog/manifest.json").read_text(encoding="utf-8"))
    entries = catalog.get("entries", [])
    if catalog.get("schema_version") != 1 or not entries:
        raise SystemExit("catalog must define schema_version=1 and at least one entry")

    modules = gitmodules()
    paths = [entry.get("path") for entry in entries]
    if len(paths) != len(set(paths)):
        raise SystemExit("catalog contains duplicate paths")
    if set(paths) != set(modules):
        raise SystemExit("catalog paths and .gitmodules paths differ")

    for entry in entries:
        path = entry.get("path", "")
        repository = entry.get("repository", "")
        if not re.fullmatch(r"https://github\.com/[^/]+/[^/]+", repository):
            raise SystemExit(f"invalid repository URL for {path}: {repository}")
        if modules[path] != repository + ".git":
            raise SystemExit(f"repository mismatch for {path}")
        if not (ROOT / path).is_dir():
            raise SystemExit(f"submodule is not checked out: {path}")

    status = subprocess.run(["git", "submodule", "status", "--recursive"], cwd=ROOT, text=True, capture_output=True)
    if status.returncode:
        raise SystemExit(status.stderr.strip() or "git submodule status failed")
    if any(line.startswith(("-", "+", "U")) for line in status.stdout.splitlines()):
        raise SystemExit("submodules are not initialized or differ from the pinned commits")
    print(f"catalog ok: {len(entries)} entries")


if __name__ == "__main__":
    main()
