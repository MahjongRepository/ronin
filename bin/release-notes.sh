#!/usr/bin/env bash
set -euo pipefail

usage="Usage: bin/release-notes.sh [--no-commits] <version> <from-ref> <summary-file> [to-ref]"

list_commits=true
if [[ "${1:-}" == "--no-commits" ]]; then
    list_commits=false
    shift
fi

version="${1:?$usage}"
from_ref="${2:?$usage}"
summary_file="${3:?$usage}"
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

if [[ "$list_commits" == true ]]; then
    print_section "Features" "${features[@]}"
    print_section "Bug Fixes" "${bugs[@]}"
    print_section "Maintenance" "${maintenance[@]}"
    print_section "Other" "${other[@]}"
else
    echo "## Changes"
    echo
    [[ ${#features[@]} -gt 0 ]] && echo "- Features: ${#features[@]}"
    [[ ${#bugs[@]} -gt 0 ]] && echo "- Bug fixes: ${#bugs[@]}"
    [[ ${#maintenance[@]} -gt 0 ]] && echo "- Maintenance: ${#maintenance[@]}"
    [[ ${#other[@]} -gt 0 ]] && echo "- Other: ${#other[@]}"
    echo "- Full changelog: ${repo_url}/compare/${from_ref}...${version}"
    echo
fi

stats=$(git diff "${from_ref}..${to_ref}" --shortstat -- ':!*.lock' ':!package-lock.json' ':!*.svg' | sed 's/^ *//')
echo "## Stats"
echo
echo "- Code changes (lock files and SVG assets excluded): ${stats}"
