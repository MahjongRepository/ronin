#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BOT_ROOT="${BOT_ROOT:-$HOME/work/mahjong-bot}"

BOT_LOG_DIR="$BOT_ROOT/project/logs"

PYTHON_WARNING_PATTERN=':[0-9]+: [A-Za-z]*Warning: '
SERVER_ISSUE_PATTERN="\\[(warning|error|critical) *\\]|^(WARNING|ERROR|CRITICAL):|Traceback|$PYTHON_WARNING_PATTERN|timeout, auto-|auth timeout,|replaced player with AI|player reconnected|connection taken over|stale game action"
BOT_CONSOLE_NOISE_PATTERN='^(.\[[0-9]+m)?[0-9-]{10} [0-9:,]{8,12} [^ ]+ (DEBUG|INFO): '
BOT_ISSUE_PATTERN="ERROR|WARNING|CRITICAL|Traceback|$PYTHON_WARNING_PATTERN"

MAX_GAMES="${1:-10}"
TABLES="${TABLES:-1}"
PROFILE="${PROFILE:-0}"

if ! [[ $MAX_GAMES =~ ^[1-9][0-9]*$ && $TABLES =~ ^[1-9][0-9]*$ ]]; then
    echo "games and tables must be positive integers, got GAMES=$MAX_GAMES TABLES=$TABLES"
    exit 1
fi

BOT_NAMES=(Akagi Tetsuya Ichihime Miki)
BOT_GAMES_DIR="$PROJECT_ROOT/backend/data/bot-games"
PROFILE_DIR="$PROJECT_ROOT/backend/profiles"
PROFILE_FILE="$PROFILE_DIR/games_$(date +%Y-%m-%d_%H-%M-%S).samples.txt"
PROFILE_RATE=100
PY_SPY="py-spy@0.4.2"
FAILED_RUN_DIR="$PROJECT_ROOT/backend/data/failed-runs/$(date +%Y-%m-%d_%H-%M-%S)"
HARNESS_LOG="$BOT_GAMES_DIR/harness.log"

GAME_PORT=8711
LOBBY_PORT=8710
MAX_RETRIES=10
BATCH_TIMEOUT=120
SHUTDOWN_TIMEOUT=15

SERVER_PIDS=()
BOT_PIDS=()
PLAYED=0
GAME_LAUNCHER=()
BOT_ACCOUNTS=()
BOT_KEYS=()

kill_tree() {
    local pid="$1"
    for child in $(pgrep -P "$pid" 2>/dev/null); do
        kill_tree "$child"
    done
    kill "$pid" 2>/dev/null || true
}

list_tree() {
    local pid="$1"
    echo "$pid"
    for child in $(pgrep -P "$pid" 2>/dev/null); do
        list_tree "$child"
    done
}

wait_for_exit() {
    local exited=0
    local deadline=$(( $(date +%s) + SHUTDOWN_TIMEOUT ))
    for pid in "$@"; do
        while kill -0 "$pid" 2>/dev/null; do
            if [[ $(date +%s) -ge $deadline ]]; then
                echo "process $pid still running ${SHUTDOWN_TIMEOUT}s after stop, killing it"
                kill -9 "$pid" 2>/dev/null || true
                exited=1
                break
            fi
            sleep 0.1
        done
    done

    return $exited
}

free_port() {
    local port="$1"
    local pids
    pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        echo "killing existing processes on port $port..."
        echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
}

stop_servers() {
    if [[ ${#SERVER_PIDS[@]} -eq 0 ]]; then
        return 0
    fi

    echo ""
    echo "stopping servers..."
    local server_tree=()
    for pid in "${SERVER_PIDS[@]}"; do
        server_tree+=($(list_tree "$pid"))
    done

    for pid in "${SERVER_PIDS[@]}"; do
        kill_tree "$pid"
    done
    local exited=0
    wait_for_exit "${server_tree[@]}" || exited=1
    for pid in "${SERVER_PIDS[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
    SERVER_PIDS=()

    return $exited
}

wait_for_server() {
    local port="$1"
    local retries=0

    while [[ $retries -lt $MAX_RETRIES ]]; do
        if curl -sf --max-time 5 "http://localhost:$port/health" > /dev/null 2>&1; then
            return 0
        fi
        retries=$((retries + 1))
        sleep 1
    done

    return 1
}

start_server() {
    local name="$1"
    local module="$2"
    local port="$3"
    local ws_max_size="$4"
    local log_dir="$5"
    local launcher=("${@:6}")

    echo "starting $name server on port $port..."
    cd "$PROJECT_ROOT" && "${launcher[@]}" --factory "$module" --host 0.0.0.0 --port "$port" --timeout-graceful-shutdown 5 --ws websockets-sansio --ws-ping-interval 20 --ws-ping-timeout 20 --ws-max-size "$ws_max_size" > "$log_dir/stdout.log" 2> "$log_dir/stderr.log" &
    SERVER_PIDS+=($!)

    if ! wait_for_server "$port" || ! kill -0 "${SERVER_PIDS[-1]}" 2>/dev/null; then
        echo "$name server failed to start after $MAX_RETRIES retries"
        exit 1
    fi
    echo "$name server ready"
}

scan_logs() {
    local label="$1"
    local dir="$2"
    local pattern="$3"

    local matches
    local status=0
    matches=$(grep -rnaE "$pattern" "$dir") || status=$?
    if [[ $status -eq 1 ]]; then
        return 0
    fi

    if [[ $status -ne 0 ]]; then
        echo "=== $label LOGS ($dir): grep failed with status $status ==="
        return 1
    fi

    echo "=== $label LOGS ($dir) ==="
    echo "$matches"
    echo ""
    return 1
}

analyze_logs() {
    local has_issues=0

    scan_logs GAME "$GAME_LOG_DIR" "$SERVER_ISSUE_PATTERN" || has_issues=1
    scan_logs LOBBY "$LOBBY_LOG_DIR" "$SERVER_ISSUE_PATTERN" || has_issues=1
    scan_logs BOT "$BOT_LOG_DIR" "$BOT_ISSUE_PATTERN" || has_issues=1

    return $has_issues
}

verify_games() {
    local expected_count="$1"

    local game_ids
    game_ids=$(grep -rhoaE 'Game started, game_id=[0-9a-f-]+' "$BOT_LOG_DIR" 2>/dev/null | sed 's/.*game_id=//' | sort -u || true)

    local count
    count=$(echo "$game_ids" | grep -c . || true)
    if [[ $count -ne $expected_count ]]; then
        echo "bots played $count game(s), expected $expected_count"
        return 1
    fi

    local new_ids
    new_ids=$(comm -13 <(sed '/^$/d' <<< "$VERIFIED_GAMES") <(echo "$game_ids"))
    # shellcheck disable=SC2086
    (cd "$PROJECT_ROOT" && uv run --project backend python bin/verify_games.py $new_ids) || return 1
    VERIFIED_GAMES="$game_ids"
}

VERIFIED_GAMES=""
BATCH_TIMES=()
BATCH_TABLES=()
BATCH_SERVER_TICKS=()
TOTAL_START=0
GAME_SERVER_PID=""

server_cpu_ticks() {
    awk '{print $14 + $15}' "/proc/$GAME_SERVER_PID/stat"
}

print_stats() {
    if [[ ${#BATCH_TIMES[@]} -eq 0 ]]; then
        return
    fi

    local games=0
    local play_seconds=0
    local server_ticks=0
    echo ""
    echo "--- stats ---"
    for idx in "${!BATCH_TIMES[@]}"; do
        echo "  batch $((idx + 1)): ${BATCH_TABLES[$idx]} table(s) in ${BATCH_TIMES[$idx]}s"
        games=$((games + BATCH_TABLES[idx]))
        play_seconds=$((play_seconds + BATCH_TIMES[idx]))
        server_ticks=$((server_ticks + BATCH_SERVER_TICKS[idx]))
    done

    echo ""
    echo "  total: $games game(s), ${play_seconds}s of play, $(( $(date +%s) - TOTAL_START ))s with verification"
    awk -v games="$games" -v seconds="$play_seconds" -v ticks="$server_ticks" -v hz="$(getconf CLK_TCK)" 'BEGIN {
        cpu = ticks / hz
        printf "  games per minute of play: %.1f\n", games * 60 / (seconds > 0 ? seconds : 1)
        printf "  game server CPU during play: %.2fs, %.3fs per game, %.0f%% of one core\n",
            cpu, cpu / games, 100 * cpu / (seconds > 0 ? seconds : 1)
    }'
}

filter_bot_console() {
    local raw_file="$1"
    local console_file="$2"

    local status=0
    grep -vaE "$BOT_CONSOLE_NOISE_PATTERN" "$raw_file" > "$console_file" || status=$?
    if [[ $status -gt 1 ]]; then
        echo "filtering bot console output failed with status $status"
        return 1
    fi

    rm "$raw_file"
}

register_bots() {
    local names=()
    for table in $(seq 1 "$TABLES"); do
        for bot in "${BOT_NAMES[@]}"; do
            names+=("${bot}_$table")
        done
    done

    local output
    local status=0
    output=$(cd "$PROJECT_ROOT" && uv run --project backend python backend/scripts/register_bot.py "${names[@]}" 2>&1) ||
        status=$?
    mapfile -t BOT_KEYS < <(sed -n 's/^API key: //p' <<< "$output")
    if [[ $status -ne 0 || ${#BOT_KEYS[@]} -ne ${#names[@]} ]]; then
        echo "registering bots failed with status $status:"
        grep -v '^API key: ' <<< "$output" || true
        exit 1
    fi

    BOT_ACCOUNTS=("${names[@]}")
}

start_bots() {
    local batch="$1"
    local tables="$2"

    BOT_PIDS=()
    for idx in $(seq 0 $((tables * ${#BOT_NAMES[@]} - 1))); do
        local name="${BOT_ACCOUNTS[$idx]}"
        PYTHONPATH="$BOT_ROOT/project" "$BOT_ROOT/.venv/bin/python" "$BOT_ROOT/project/run_ronin.py" \
            -p "$name" -k "${BOT_KEYS[$idx]}" > "$BOT_LOG_DIR/console-$batch-$name.raw" 2>&1 &
        BOT_PIDS+=($!)
    done
}

any_bot_running() {
    for pid in "${BOT_PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    done

    return 1
}

stop_bots() {
    if [[ ${#BOT_PIDS[@]} -eq 0 ]]; then
        return 0
    fi

    local bot_tree=()
    for pid in "${BOT_PIDS[@]}"; do
        bot_tree+=($(list_tree "$pid"))
    done

    for pid in "${BOT_PIDS[@]}"; do
        kill_tree "$pid"
    done
    local exited=0
    wait_for_exit "${bot_tree[@]}" || exited=1
    for pid in "${BOT_PIDS[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
    BOT_PIDS=()

    return $exited
}

probe_health() {
    local port="$1"
    local result
    local status=0
    result=$(curl -sS -o /dev/null --max-time 5 -w '%{http_code} %{time_total}s' "http://localhost:$port/health" 2>&1) ||
        status=$?
    if [[ $status -eq 0 && $result == "200 "* ]]; then
        return 0
    fi

    echo "$(date -u +%FT%T.%3NZ) health check of the server on port $port failed: curl exit $status, $result"
    return 1
}

wait_for_bots() {
    local deadline=$(( $(date +%s) + BATCH_TIMEOUT ))
    while any_bot_running; do
        if [[ $(date +%s) -ge $deadline ]]; then
            echo "batch timed out after ${BATCH_TIMEOUT}s, stopping"
            return 1
        fi
        if ! probe_health "$GAME_PORT" || ! probe_health "$LOBBY_PORT"; then
            return 1
        fi
        sleep 1
    done

    local failed=0
    for pid in "${BOT_PIDS[@]}"; do
        local status=0
        wait "$pid" || status=$?
        if [[ $status -ne 0 ]]; then
            echo "bot process $pid exited with code $status"
            failed=1
        fi
    done
    BOT_PIDS=()

    return $failed
}

stop_profiler() {
    local profiler=""
    for pid in $(list_tree "${SERVER_PIDS[0]}"); do
        if [[ $(ps -o comm= -p "$pid" 2>/dev/null) == py-spy ]]; then
            profiler="$pid"
            break
        fi
    done

    if [[ -z $profiler ]]; then
        echo "py-spy is not running under the game server"
        return 1
    fi

    local server
    server=$(pgrep -P "$profiler" || true)
    if [[ -z $server ]]; then
        echo "the game server is not running under py-spy"
        return 1
    fi

    kill -TERM "$server"
    wait_for_exit "$server" "$profiler" || return 1

    local status=0
    wait "${SERVER_PIDS[0]}" || status=$?
    SERVER_PIDS=("${SERVER_PIDS[@]:1}")
    if [[ $status -ne 0 ]] &&
        ! { [[ $status -eq 1 ]] && grep -qa 'No child process' "$GAME_LOG_DIR/stdout.log" "$GAME_LOG_DIR/stderr.log"; }; then
        echo "py-spy exited with code $status"
        return 1
    fi
}

record_process_state() {
    local pids=()
    for pid in "${SERVER_PIDS[@]}" "${BOT_PIDS[@]}"; do
        pids+=($(list_tree "$pid"))
    done

    mkdir -p "$FAILED_RUN_DIR"
    {
        date -u +%FT%T.%3NZ
        if [[ ${#pids[@]} -gt 0 ]]; then
            ps -o pid,ppid,stat,etime,time,comm -p "$(IFS=,; echo "${pids[*]}")" || true
        fi
    } > "$FAILED_RUN_DIR/processes.txt"
}

archive_failed_run() {
    local status="$1"
    mkdir -p "$FAILED_RUN_DIR"
    cp -r "$GAME_LOG_DIR" "$LOBBY_LOG_DIR" "$FAILED_RUN_DIR/" 2>/dev/null || true
    cp -r "$BOT_LOG_DIR" "$FAILED_RUN_DIR/bot-logs" 2>/dev/null || true
    cp "$HARNESS_LOG" "$FAILED_RUN_DIR/" 2>/dev/null || true
    {
        echo "exit status: $status"
        echo "games: $PLAYED of $MAX_GAMES played, tables: $TABLES, profile: $PROFILE"
        if [[ $PROFILE == 1 ]]; then
            echo "profiler: ${GAME_LAUNCHER[*]:0:9}"
            echo "profile: $PROFILE_FILE"
        fi
        echo "batch seconds: ${BATCH_TIMES[*]}"
        echo "batch game server CPU ticks: ${BATCH_SERVER_TICKS[*]}"
    } > "$FAILED_RUN_DIR/run.txt"
    echo "failed run kept in $FAILED_RUN_DIR"
}

on_exit() {
    local status=$?
    if [[ $status -ne 0 ]]; then
        record_process_state
    fi

    stop_bots || true
    stop_servers || true
    if [[ $status -ne 0 ]]; then
        archive_failed_run "$status"
    fi

    exit "$status"
}

trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [ -f "$PROJECT_ROOT/.env.local" ]; then
    set -a && . "$PROJECT_ROOT/.env.local" && set +a
fi
. "$SCRIPT_DIR/local-settings.sh"
export AUTH_DATABASE_PATH="$BOT_GAMES_DIR/storage.db"
if [[ $PROFILE == 1 ]]; then
    export LOG_LEVEL=info
else
    export LOG_LEVEL=debug
fi
export LOG_FORMAT=console
export GAME_LOG_DIR="$PROJECT_ROOT/backend/logs/game"
export LOBBY_LOG_DIR="$PROJECT_ROOT/backend/logs/lobby"

find "$PROJECT_ROOT/backend/data/replays" "$PROJECT_ROOT/backend/data/tenhou_replays" -mindepth 1 -delete 2>/dev/null || true
for dir in "$GAME_LOG_DIR" "$LOBBY_LOG_DIR" "$BOT_LOG_DIR" "$BOT_GAMES_DIR"; do
    find "$dir" -mindepth 1 -delete 2>/dev/null || true
    mkdir -p "$dir"
done
exec > >(tee "$HARNESS_LOG") 2>&1

register_bots

GAME_LAUNCHER=(uv run --project backend uvicorn)
if [[ $PROFILE == 1 ]]; then
    mkdir -p "$PROFILE_DIR"
    GAME_LAUNCHER=(uvx "$PY_SPY" record --function --gil --rate "$PROFILE_RATE" --format raw --output "$PROFILE_FILE"
        -- backend/.venv/bin/python -m uvicorn)
fi

free_port "$GAME_PORT"
free_port "$LOBBY_PORT"
start_server "game" "game.server.app:get_app" "$GAME_PORT" 262144 "$GAME_LOG_DIR" "${GAME_LAUNCHER[@]}"
start_server "lobby" "lobby.server.app:get_app" "$LOBBY_PORT" 8192 "$LOBBY_LOG_DIR" uv run --project backend uvicorn

echo ""
echo "running $MAX_GAMES game(s), up to $TABLES at a time..."
echo ""

GAME_SERVER_PID=$(lsof -ti tcp:"$GAME_PORT" -sTCP:LISTEN | head -1)
TOTAL_START=$(date +%s)
PLAYED=0
BATCH=0

while [[ $PLAYED -lt $MAX_GAMES ]]; do
    BATCH=$((BATCH + 1))
    BATCH_SIZE=$(( MAX_GAMES - PLAYED < TABLES ? MAX_GAMES - PLAYED : TABLES ))
    echo "=== Games $((PLAYED + 1))-$((PLAYED + BATCH_SIZE)) of $MAX_GAMES ==="

    BATCH_START=$(date +%s)
    TICKS_START=$(server_cpu_ticks)
    start_bots "$BATCH" "$BATCH_SIZE"
    if ! wait_for_bots; then
        print_stats
        exit 1
    fi

    BATCH_SERVER_TICKS+=($(( $(server_cpu_ticks) - TICKS_START )))
    BATCH_ELAPSED=$(( $(date +%s) - BATCH_START ))
    BATCH_TIMES+=("$BATCH_ELAPSED")
    BATCH_TABLES+=("$BATCH_SIZE")
    PLAYED=$((PLAYED + BATCH_SIZE))

    for raw_file in "$BOT_LOG_DIR"/console-"$BATCH"-*.raw; do
        filter_bot_console "$raw_file" "${raw_file%.raw}.log"
    done

    if ! verify_games "$PLAYED"; then
        echo ""
        echo "batch $BATCH failed verification, stopping"
        print_stats
        exit 1
    fi

    if ! analyze_logs; then
        echo ""
        echo "issues found in batch $BATCH, stopping"
        print_stats
        exit 1
    fi

    echo "clean (${BATCH_ELAPSED}s)"
    echo ""
done

if [[ $PROFILE == 1 ]] && ! stop_profiler; then
    echo "stopping py-spy failed"
    print_stats
    exit 1
fi

if ! stop_servers || ! analyze_logs; then
    echo ""
    echo "issues found during server shutdown"
    print_stats
    exit 1
fi

print_stats

if [[ $PROFILE == 1 ]]; then
    echo ""
    if ! (cd "$PROJECT_ROOT" && uv run --project backend python bin/sampled_profile.py --rate "$PROFILE_RATE" \
        --py-spy-log "$GAME_LOG_DIR/stdout.log" "$PROFILE_FILE"); then
        echo "the game server profile is invalid"
        exit 1
    fi
fi

echo "=== all $MAX_GAMES game(s) completed successfully ==="
