#!/usr/bin/env bash
set -euo pipefail

version="${1:?Usage: bin/release-notes.sh <version> <from-ref> <summary-file> [to-ref]}"
from_ref="${2:?Usage: bin/release-notes.sh <version> <from-ref> <summary-file> [to-ref]}"
summary_file="${3:?Usage: bin/release-notes.sh <version> <from-ref> <summary-file> [to-ref]}"
to_ref="${4:-HEAD}"

repo_url="https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)"

features=()
bugs=()
maintenance=()
other=()

while IFS= read -r line; do
    sha="${line%% *}"
    msg="${line#* }"
    entry="${msg} (${repo_url}/commit/${sha})"

    if [[ "$msg" =~ ^feat:\ (.+) ]]; then
        features+=("$entry")
    elif [[ "$msg" =~ ^bug:\ (.+) ]]; then
        bugs+=("$entry")
    elif [[ "$msg" =~ ^chore:\ (.+) ]]; then
        maintenance+=("$entry")
    else
        other+=("$entry")
    fi
done < <(git log "${from_ref}..${to_ref}" --format='%H %s')

print_section() {
    local title="$1"
    shift
    local items=("$@")
    if [[ ${#items[@]} -gt 0 ]]; then
        echo "## ${title}"
        for item in "${items[@]}"; do
            echo "- ${item}"
        done
        echo
    fi
}

echo "# Release ${version}"
echo
echo "## Summary"
echo
cat "$summary_file"
echo

print_section "Features" "${features[@]}"
print_section "Bug Fixes" "${bugs[@]}"
print_section "Maintenance" "${maintenance[@]}"
print_section "Other" "${other[@]}"

stats=$(git diff "${from_ref}..${to_ref}" --shortstat -- ':!*.lock' ':!bun.lock' ':!*.svg' | sed 's/^ *//')
echo "## Stats"
echo
echo "- Code changes (lock files and SVG assets excluded): ${stats}"
