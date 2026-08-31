#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

case "${1:-}" in
  --check)
    git submodule status --recursive
    git diff --exit-code -- .gitmodules
    ;;
  "")
    git submodule update --init --recursive
    git submodule status --recursive
    ;;
  *)
    printf 'Usage: %s [--check]\n' "$0" >&2
    exit 2
    ;;
esac
