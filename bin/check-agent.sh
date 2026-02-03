#!/bin/bash

# This function runs a command silently. If it fails, it prints
# the error output and exits the script immediately.
# Arguments:
#   $1: A human-readable description of the check.
#   $2: The command to execute.
run_check() {
    local description="$1"
    local command="$2"
    output=$(eval "$command" 2>&1)
    exit_code=$?

    if [ $exit_code -ne 0 ]; then
        echo "❌ CHECK FAILED: $description"
        echo "$output"
        exit 1
    fi
}


# --- Main Execution ---

echo "❯ Running all checks..."

# --- Python Checks ---
run_check "Format" "make format"
run_check "Lint" "make lint"
run_check "Typecheck" "make typecheck"
run_check "Dead code" "uv run python bin/check-dead-code.py src"
run_check "Test" "make test"

# --- Client Checks ---
run_check "Client format" "make format-client"
run_check "Client lint" "make lint-client"
run_check "Client typecheck" "make typecheck-client"

# If the script reaches this line, it's because no check failed and the script never exited.
echo "🎉 All checks are good, thank you!"
