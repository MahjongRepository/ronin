BAD_NET_TRAEFIK_IMAGE="traefik:v3.7"
BAD_NET_TOXIPROXY_IMAGE="ghcr.io/shopify/toxiproxy:2.13.0"
BAD_NET_LABEL="ronin.run-games=bad-network"
BAD_NET_TRAEFIK="ronin-bad-net-traefik"
BAD_NET_TOXIPROXY="ronin-bad-net-toxiproxy"
BAD_NET_PUBLIC_PORT=8720
BAD_NET_TRAEFIK_PORT=8730
BAD_NET_TOXIPROXY_API="http://127.0.0.1:8740"
BAD_NET_PUBLIC_ORIGIN="http://localhost:$BAD_NET_PUBLIC_PORT"
BAD_NET_READINESS_PATH="/health?bad-net-readiness"

BAD_NET_LATENCY_MS=100
BAD_NET_JITTER_MS=50
BAD_NET_SLICE_BYTES=24
BAD_NET_SLICE_VARIATION=20
BAD_NET_SLICE_DELAY_US=200

BAD_NET_CALM_MIN=15
BAD_NET_CALM_MAX=45
BAD_NET_STALL_MS=60000
BAD_NET_STALL_MIN=20
BAD_NET_STALL_MAX=70
BAD_NET_STALL_TOXICITY=0.04
BAD_NET_HOLE_TIMEOUT_MIN_MS=5000
BAD_NET_HOLE_TIMEOUT_MAX_MS=15000
BAD_NET_HOLE_MIN=50
BAD_NET_HOLE_MAX=65
BAD_NET_HOLE_TOXICITY=0.03
BAD_NET_RESET_MIN=2
BAD_NET_RESET_MAX=6
BAD_NET_RESET_TOXICITY=0.05

BAD_NET_EXPECTED_EVENTS="player reconnected|replaced player with AI|connection taken over|stale game action|meld timeout, auto-passing|turn timeout, auto-discarding"
BAD_NET_EXPECTED_SESSION_ERRORS="reconnect_no_session"

BAD_NET_TRAEFIK_ISSUE_PATTERN='"level":"(warn|error|fatal|panic)"|"DownstreamStatus":[1-9]'
BAD_NET_TRAEFIK_EXPECTED_PATTERN='"DownstreamStatus":(101|200|499),|"DownstreamStatus":404,.*"RequestPath":"/health\?bad-net-readiness"|"level":"warn".*"(Traefik can reject some encoded characters in the request path|A new release of Traefik has been found)'
BAD_NET_TOXICS_ISSUE_PATTERN='FAILED'
BAD_NET_TOXIPROXY_ISSUE_PATTERN='"level":"(error|fatal|panic)"|panic:'
BAD_NET_TOXIPROXY_EXPECTED_PATTERN='"level":"error".*"message":"Could not write last packets after interrupt to Output"'

BAD_NET_CONTROLLER_PID=""

bad_net_usage() {
    echo "NET=bad: bots -> toxiproxy :$BAD_NET_PUBLIC_PORT -> Traefik :$BAD_NET_TRAEFIK_PORT -> lobby :$LOBBY_PORT and game :$GAME_PORT."
    echo "Traefik runs production's routers, priorities and middlewares (deploy/config/traefik-dynamic.yml)"
    echo "on plain HTTP for localhost. Toxiproxy always adds ${BAD_NET_LATENCY_MS}+-${BAD_NET_JITTER_MS} ms of latency and slices"
    echo "writes into ~$BAD_NET_SLICE_BYTES-byte chunks both ways; a controller opens random windows of stalls, resets"
    echo "and black holes on a few connections at a time, logged to backend/logs/net/toxics.log. Black holes are"
    echo "toggled by toxicity and never removed, since removing a timeout toxic closes every connection, and each lasts"
    echo "past the server's ping interval plus timeout, so the server has closed every link it held before it lifts."
}

bad_net_toxic() {
    local method="$1"
    local path="$2"
    local body="${3:-}"
    local args=(-sS -f --max-time 60 -X "$method" "$BAD_NET_TOXIPROXY_API$path")
    if [[ -n $body ]]; then
        args+=(-H 'Content-Type: application/json' -d "$body")
    fi
    curl "${args[@]}" > /dev/null
}

bad_net_log() {
    echo "$(date -u +%FT%T.%3NZ) $*" >> "$NET_LOG_DIR/toxics.log"
}

bad_net_report() {
    local change="$1"
    local started
    started=$(date +%s.%N)
    if ! "${@:2}"; then
        bad_net_log "FAILED $change"
        return 1
    fi
    bad_net_log "$change ($(awk -v start="$started" -v now="$(date +%s.%N)" 'BEGIN { printf "%.1fs", now - start }'))"
}

bad_net_add() {
    local name="$1"
    local type="$2"
    local stream="$3"
    local toxicity="$4"
    local attributes="$5"
    bad_net_report "add $name type=$type stream=$stream toxicity=$toxicity attributes=$attributes" \
        bad_net_toxic POST /proxies/ronin/toxics \
        "{\"name\":\"$name\",\"type\":\"$type\",\"stream\":\"$stream\",\"toxicity\":$toxicity,\"attributes\":$attributes}"
}

bad_net_remove() {
    local name="$1"
    bad_net_report "remove $name" bad_net_delete "$name"
}

bad_net_delete() {
    local name="$1"
    if bad_net_toxic DELETE "/proxies/ronin/toxics/$name"; then
        return 0
    fi

    echo "toxiproxy answered the removal of $name with an error (its API times out after about 25s while the toxic"
    echo "tries to flush held bytes into links already closed); checking that the toxic is gone..."
    for _ in $(seq 1 60); do
        local status
        status=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BAD_NET_TOXIPROXY_API/proxies/ronin/toxics/$name")
        if [[ $status == 404 ]]; then
            return 0
        fi
        sleep 2
    done

    return 1
}

bad_net_set() {
    local name="$1"
    local toxicity="$2"
    local attributes="$3"
    bad_net_report "set $name toxicity=$toxicity attributes=$attributes" \
        bad_net_toxic POST "/proxies/ronin/toxics/$name" "{\"toxicity\":$toxicity,\"attributes\":$attributes}"
}

bad_net_between() {
    local low="$1"
    local high="$2"
    echo $(( low + RANDOM % (high - low + 1) ))
}

bad_net_window() {
    local kind="$1"
    local toxicity="$2"
    local seconds="$3"
    local type="$4"
    local attributes="$5"
    bad_net_log "window $kind for ${seconds}s"
    bad_net_add "${kind}_up" "$type" upstream "$toxicity" "$attributes" &&
        bad_net_add "${kind}_down" "$type" downstream "$toxicity" "$attributes" &&
        sleep "$seconds"
    bad_net_remove "${kind}_up" || true
    bad_net_remove "${kind}_down" || true
}

bad_net_black_hole() {
    local seconds="$1"
    local attributes="{\"timeout\":$(bad_net_between "$BAD_NET_HOLE_TIMEOUT_MIN_MS" "$BAD_NET_HOLE_TIMEOUT_MAX_MS")}"
    bad_net_log "window black_hole for ${seconds}s"
    bad_net_set black_hole_upstream "$BAD_NET_HOLE_TOXICITY" "$attributes" &&
        bad_net_set black_hole_downstream "$BAD_NET_HOLE_TOXICITY" "$attributes" &&
        sleep "$seconds"
    bad_net_set black_hole_upstream 0 "$attributes" || true
    bad_net_set black_hole_downstream 0 "$attributes" || true
}

bad_net_controller() {
    trap 'exit 0' TERM INT
    while true; do
        sleep "$(bad_net_between "$BAD_NET_CALM_MIN" "$BAD_NET_CALM_MAX")"
        local roll=$(( RANDOM % 10 ))
        if [[ $roll -lt 4 ]]; then
            bad_net_window stall "$BAD_NET_STALL_TOXICITY" "$(bad_net_between "$BAD_NET_STALL_MIN" "$BAD_NET_STALL_MAX")" \
                latency "{\"latency\":$BAD_NET_STALL_MS,\"jitter\":0}"
        elif [[ $roll -lt 7 ]]; then
            bad_net_black_hole "$(bad_net_between "$BAD_NET_HOLE_MIN" "$BAD_NET_HOLE_MAX")"
        else
            bad_net_window reset "$BAD_NET_RESET_TOXICITY" "$(bad_net_between "$BAD_NET_RESET_MIN" "$BAD_NET_RESET_MAX")" \
                reset_peer '{"timeout":0}'
        fi
    done
}

bad_net_render_traefik_config() {
    local source="$PROJECT_ROOT/deploy/config/traefik-dynamic.yml"
    local target="$NET_LOG_DIR/traefik-dynamic.yml"
    sed -e 's/%%DOMAIN%%/localhost/g' \
        -e 's/\["websecure"\]/["web"]/g' \
        -e '/^ *tls: *$/d' \
        -e '/^ *certResolver: /d' \
        -e "s#http://lobby:8710#http://127.0.0.1:$LOBBY_PORT#" \
        -e "s#http://game:8711#http://127.0.0.1:$GAME_PORT#" \
        "$source" > "$target"

    if grep -nE '%%|websecure|certResolver|tls:|//(lobby|game):' "$target"; then
        echo "rendering $source for the local proxy left production-only lines (above), update bad-network.sh"
        return 1
    fi
}

bad_net_remove_containers() {
    local ids
    ids=$(docker ps -aq --filter "label=$BAD_NET_LABEL")
    if [[ -n $ids ]]; then
        echo "$ids" | xargs docker rm -f > /dev/null
    fi
}

bad_net_wait_for() {
    local url="$1"
    for _ in $(seq 1 30); do
        if curl -sf --max-time 5 "$url" > /dev/null 2>&1; then
            return 0
        fi
        sleep 0.5
    done
    echo "$url did not answer through the proxy chain"
    return 1
}

start_bad_network() {
    mkdir -p "$NET_LOG_DIR"
    bad_net_remove_containers
    bad_net_render_traefik_config

    echo "starting Traefik ($BAD_NET_TRAEFIK_IMAGE) on :$BAD_NET_TRAEFIK_PORT and toxiproxy on :$BAD_NET_PUBLIC_PORT..."
    docker run -d --name "$BAD_NET_TRAEFIK" --label "$BAD_NET_LABEL" --network host \
        -v "$NET_LOG_DIR/traefik-dynamic.yml:/etc/traefik/dynamic.yml:ro" \
        "$BAD_NET_TRAEFIK_IMAGE" \
        --providers.file.filename=/etc/traefik/dynamic.yml \
        --providers.file.watch=true \
        "--entrypoints.web.address=127.0.0.1:$BAD_NET_TRAEFIK_PORT" \
        --entrypoints.web.http.aliasheadersstrategy=delete \
        --api.dashboard=false \
        --log.level=INFO \
        --log.format=json \
        --accesslog=true \
        --accesslog.format=json \
        --accesslog.fields.headers.defaultmode=drop > /dev/null
    docker run -d --name "$BAD_NET_TOXIPROXY" --label "$BAD_NET_LABEL" --network host \
        "$BAD_NET_TOXIPROXY_IMAGE" -host 127.0.0.1 -port "${BAD_NET_TOXIPROXY_API##*:}" > /dev/null

    bad_net_wait_for "http://localhost:$BAD_NET_TRAEFIK_PORT$BAD_NET_READINESS_PATH"
    bad_net_wait_for "$BAD_NET_TOXIPROXY_API/version"
    bad_net_toxic POST /proxies \
        "{\"name\":\"ronin\",\"listen\":\"127.0.0.1:$BAD_NET_PUBLIC_PORT\",\"upstream\":\"127.0.0.1:$BAD_NET_TRAEFIK_PORT\"}"
    for stream in upstream downstream; do
        bad_net_add "latency_$stream" latency "$stream" 1 \
            "{\"latency\":$BAD_NET_LATENCY_MS,\"jitter\":$BAD_NET_JITTER_MS}"
        bad_net_add "slicer_$stream" slicer "$stream" 1 \
            "{\"average_size\":$BAD_NET_SLICE_BYTES,\"size_variation\":$BAD_NET_SLICE_VARIATION,\"delay\":$BAD_NET_SLICE_DELAY_US}"
        bad_net_add "black_hole_$stream" timeout "$stream" 0 "{\"timeout\":$BAD_NET_HOLE_TIMEOUT_MIN_MS}"
    done
    bad_net_wait_for "$BAD_NET_PUBLIC_ORIGIN$BAD_NET_READINESS_PATH"

    bad_net_controller &
    BAD_NET_CONTROLLER_PID=$!
    echo "proxy chain ready, toxics logged to $NET_LOG_DIR/toxics.log"
}

collect_bad_network_logs() {
    docker logs "$BAD_NET_TRAEFIK" > "$NET_LOG_DIR/traefik.log" 2>&1 || true
    docker logs "$BAD_NET_TOXIPROXY" > "$NET_LOG_DIR/toxiproxy.log" 2>&1 || true
}

stop_bad_network() {
    if [[ -n $BAD_NET_CONTROLLER_PID ]]; then
        kill_tree "$BAD_NET_CONTROLLER_PID"
        wait "$BAD_NET_CONTROLLER_PID" 2>/dev/null || true
        BAD_NET_CONTROLLER_PID=""
    fi

    if [[ -d $NET_LOG_DIR ]]; then
        collect_bad_network_logs
    fi
    bad_net_remove_containers
}

bad_network_running() {
    local container
    for container in "$BAD_NET_TRAEFIK" "$BAD_NET_TOXIPROXY"; do
        if [[ $(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null) != true ]]; then
            echo "$(date -u +%FT%T.%3NZ) container $container is not running"
            return 1
        fi
    done
}
