#!/bin/bash

# Find errors/warnings in game and bot logs and show correlated context.
#
# For the log containing the error: shows everything up to the error line.
# For the other log: shows everything up to the matching timestamp + 5 lines.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

GAME_LOG_DIR="$PROJECT_ROOT/logs/game"
BOT_LOG_DIR="$PROJECT_ROOT/bot/project/logs"
TAIL_LINES=200

game_log=$(ls -t "$GAME_LOG_DIR"/*.log 2>/dev/null | head -1 || true)
bot_log=$(ls -t "$BOT_LOG_DIR"/*.log 2>/dev/null | head -1 || true)

if [[ -z "$game_log" ]]; then
    echo "no game logs found in $GAME_LOG_DIR"
    exit 1
fi

if [[ -z "$bot_log" ]]; then
    echo "no bot logs found in $BOT_LOG_DIR"
    exit 1
fi

game_lines=$(tail -"$TAIL_LINES" "$game_log")
bot_lines=$(tail -"$TAIL_LINES" "$bot_log")

# find last ERROR or WARNING line number in each (within our tail window)
game_error_ln=$(echo "$game_lines" | grep -nE 'ERROR|WARNING' | tail -1 | cut -d: -f1 || true)
bot_error_ln=$(echo "$bot_lines" | grep -nE 'ERROR|WARNING' | tail -1 | cut -d: -f1 || true)

if [[ -z "$game_error_ln" && -z "$bot_error_ln" ]]; then
    echo "no errors or warnings found, cleaning up log folders"
    rm -f "$GAME_LOG_DIR"/*.log
    rm -f "$BOT_LOG_DIR"/*.log
    echo "  removed game logs from $GAME_LOG_DIR"
    echo "  removed bot logs from $BOT_LOG_DIR"
    exit 0
fi

# pick the log with the error as primary (prefer game log)
if [[ -n "$game_error_ln" ]]; then
    primary_label="GAME"
    primary_path="$game_log"
    primary_lines="$game_lines"
    primary_error_ln="$game_error_ln"
    secondary_label="BOT"
    secondary_path="$bot_log"
    secondary_lines="$bot_lines"
else
    primary_label="BOT"
    primary_path="$bot_log"
    primary_lines="$bot_lines"
    primary_error_ln="$bot_error_ln"
    secondary_label="GAME"
    secondary_path="$game_log"
    secondary_lines="$game_lines"
fi

# show primary log truncated at error line
echo "=== $primary_label LOG ($primary_path) ==="
echo "$primary_lines" | head -n "$primary_error_ln"

# extract timestamp from error line (format: YYYY-MM-DD HH:MM:SS)
timestamp=$(echo "$primary_lines" | sed -n "${primary_error_ln}p" | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}' || true)

if [[ -z "$timestamp" ]]; then
    echo ""
    echo "=== could not extract timestamp from error line ==="
    exit 1
fi

# find matching timestamp in secondary log, show up to that line + 5
secondary_match_ln=$(echo "$secondary_lines" | grep -n "$timestamp" | tail -1 | cut -d: -f1 || true)

echo ""
if [[ -n "$secondary_match_ln" ]]; then
    cut_at=$((secondary_match_ln + 5))
    echo "=== $secondary_label LOG ($secondary_path) ==="
    echo "$secondary_lines" | head -n "$cut_at"
else
    echo "=== no matching timestamp ($timestamp) in $secondary_label log ==="
fi
