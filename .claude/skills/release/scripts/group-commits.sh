#!/usr/bin/env bash
# Group commits between two refs by prefix (feat/bug/chore).
# Usage: bin/group-commits.sh <from-ref> <to-ref>
# Output: markdown-formatted grouped commit list to stdout.

set -euo pipefail

from_ref="${1:?Usage: bin/group-commits.sh <from-ref> <to-ref>}"
to_ref="${2:-HEAD}"

repo_url="https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)"

features=()
bugs=()
maintenance=()
other=()

while IFS= read -r line; do
    # Split into short hash and message
    sha="${line%% *}"
    msg="${line#* }"
    full_sha=$(git rev-parse "$sha")
    link="${repo_url}/commit/${full_sha}"
    entry="${msg} (${link})"

    if [[ "$msg" =~ ^feat:\ (.+) ]]; then
        features+=("$entry")
    elif [[ "$msg" =~ ^bug:\ (.+) ]]; then
        bugs+=("$entry")
    elif [[ "$msg" =~ ^chore:\ (.+) ]]; then
        maintenance+=("$entry")
    else
        other+=("$entry")
    fi
done < <(git log "${from_ref}..${to_ref}" --oneline)

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

print_section "Features" "${features[@]}"
print_section "Bug Fixes" "${bugs[@]}"
print_section "Maintenance" "${maintenance[@]}"
print_section "Other" "${other[@]}"
