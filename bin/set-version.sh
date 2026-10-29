#!/usr/bin/env bash
set -euo pipefail

version="${1:?Usage: bin/set-version.sh <version>}"
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Version must be X.Y.Z, got: $version" >&2
    exit 1
fi

cd "$(dirname "$0")/../backend"
sed -i "s/^version = \".*\"/version = \"${version}\"/" pyproject.toml
grep -q "^version = \"${version}\"$" pyproject.toml
uv lock
