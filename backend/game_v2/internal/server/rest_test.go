package server_test

import (
	"bytes"
	"maps"
	"net/http"
	"os"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/coder/websocket"
	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/auth"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/server"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func TestHealth_ShouldAnswerOKWithVersionAndCommit(t *testing.T) {
	h := newHarness(t)

	got := h.get("/health")

	want := map[string]any{"status": "ok", "version": testVersion, "commit": testCommit}
	if got.status != http.StatusOK || !cmp.Equal(got.body, want) {
		t.Errorf("GET /health = %d %v, want 200 %v", got.status, got.body, want)
	}
}

var telegrafGameStatus = regexp.MustCompile(`(?s)name_override = "game_status".*?fieldinclude = \[([^\]]*)\]`)

func telegrafFields(t *testing.T) []string {
	t.Helper()
	conf, err := os.ReadFile("../../../../deploy/config/telegraf.conf")
	if err != nil {
		t.Fatalf("read telegraf.conf: %v", err)
	}
	match := telegrafGameStatus.FindSubmatch(conf)
	if match == nil {
		t.Fatal("telegraf.conf has no game_status fieldinclude")
	}
	var fields []string
	for item := range strings.SplitSeq(string(match[1]), ",") {
		if name := strings.Trim(strings.TrimSpace(item), `"`); name != "" {
			fields = append(fields, name)
		}
	}
	return fields
}

func TestStatus_ShouldCarryTheTelegrafFieldsAndOnlyTheLobbysOthers(t *testing.T) {
	h := newHarness(t)
	stranger := h.dial(testGameID, nil)
	send(t, stranger, passOutsideAGame(wire.Int(1)))
	readUntil(t, stranger, func(m wire.Map) bool { return errorCode(m) == string(messaging.SessionNotInGame) })

	status := h.status()

	var unlisted []string
	listed := telegrafFields(t)
	for _, key := range slices.Sorted(maps.Keys(status)) {
		if !slices.Contains(listed, key) {
			unlisted = append(unlisted, key)
		}
	}
	if want := []string{"capacity_used", "commit", "max_capacity", "status", "version"}; !cmp.Equal(unlisted, want) {
		t.Errorf("/status keys outside the Telegraf allow-list = %v, want %v", unlisted, want)
	}
	for _, field := range listed {
		if _, ok := status[field]; !ok {
			t.Errorf("/status lacks the Telegraf field %s", field)
		}
	}
	startedAt := counter(t, status, "started_at")
	if float64(startedAt) != status["started_at"] || time.Since(time.Unix(int64(startedAt), 0)) > time.Minute {
		t.Errorf("/status started_at = %v, want the process start in whole epoch seconds", status["started_at"])
	}
	if status["loop_lag_max_ms"] != nil {
		t.Errorf("/status loop_lag_max_ms = %v after only a message no game took, want null", status["loop_lag_max_ms"])
	}
}

func TestStatus_WhenAGameIsPending_ShouldCountItAgainstCapacity(t *testing.T) {
	h := newHarness(t)
	h.create("alice")

	status := h.status()

	got := []int{
		counter(t, status, "pending_games"), counter(t, status, "active_games"),
		counter(t, status, "capacity_used"), counter(t, status, "max_capacity"),
	}
	if want := []int{1, 0, 1, 10}; !cmp.Equal(got, want) {
		t.Errorf("/status pending, active, used, max = %v, want %v", got, want)
	}
}

func TestCreateGame_WhenBodyValid_ShouldAnswer201Pending(t *testing.T) {
	h := newHarness(t)

	got := h.postGame(gameBody(testGameID, "alice", strings.Repeat("あ", 50)))

	want := map[string]any{"game_id": testGameID, "status": "pending"}
	if got.status != http.StatusCreated || !cmp.Equal(got.body, want) {
		t.Errorf("POST /games = %d %v, want 201 %v", got.status, got.body, want)
	}
}

func TestCreateGame_WhenBodyInvalid_ShouldAnswer400(t *testing.T) {
	alice := gameBody(testGameID, "alice").Players[0]
	expired := alice
	expired.Ticket = auth.SignTicket(auth.Ticket{
		UserID: alice.UserID, Username: alice.Name, RoomID: testGameID, ExpiresAt: float64(time.Now().Add(-time.Minute).Unix()),
	}, ticketSecret)
	otherGame := alice
	otherGame.Ticket = ticketFor("game-0002", "alice")
	renamed := alice
	renamed.Name = "mallory"
	twoAlices := gameBody(testGameID, "alice", "bob")
	twoAlices.Players[1].Name = "alice"

	tests := []struct {
		name    string
		body    any
		message string
	}{
		{"not json", "{", "Invalid request body"},
		{"unknown key", map[string]any{"game_id": testGameID, "num_ai_players": 3, "players": []any{alice}, "extra": 1}, "Invalid request body"},
		{"game id with a space", gameBody("game 0001", "alice"), "Invalid request body"},
		{"game id too short", gameBody("abc", "alice"), "Invalid request body"},
		{"ai count as a float", map[string]any{"game_id": testGameID, "num_ai_players": 3.5, "players": []any{alice}}, "Invalid request body"},
		{"ai count as a bool", map[string]any{"game_id": testGameID, "num_ai_players": true, "players": []any{alice}}, "Invalid request body"},
		{"ai count missing its players", map[string]any{"game_id": testGameID, "num_ai_players": 2, "players": []any{alice}}, "Invalid request body"},
		{"fixed seats as a string", map[string]any{"game_id": testGameID, "players": []any{alice}, "fixed_seats": "true"}, "Invalid request body"},
		{"duplicate names", twoAlices, "Invalid request body"},
		{"player with an unknown key", map[string]any{"game_id": testGameID, "players": []any{map[string]any{"name": "alice", "user_id": "user-alice", "game_ticket": alice.Ticket, "seat": 0}}}, "Invalid request body"},
		{"name as a number", map[string]any{"game_id": testGameID, "players": []any{map[string]any{"name": 7, "user_id": "user-alice", "game_ticket": alice.Ticket}}}, "Invalid request body"},
		{"name too long", map[string]any{"game_id": testGameID, "players": []any{map[string]any{"name": strings.Repeat("あ", 51), "user_id": "user-alice", "game_ticket": alice.Ticket}}}, "Invalid request body"},
		{"expired ticket", map[string]any{"game_id": testGameID, "players": []any{expired}}, "Invalid or expired game ticket"},
		{"ticket of another game", map[string]any{"game_id": testGameID, "players": []any{otherGame}}, "Ticket game_id mismatch"},
		{"ticket of another name", map[string]any{"game_id": testGameID, "players": []any{renamed}}, "Ticket identity mismatch"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			h := newHarness(t)

			var got answer
			if raw, isRaw := tc.body.(string); isRaw {
				got = h.request(http.MethodPost, "/games", strings.NewReader(raw), nil)
			} else {
				got = h.postGame(tc.body)
			}

			if got.status != http.StatusBadRequest || got.body["error"] != tc.message {
				t.Errorf("POST /games = %d %v, want 400 %q", got.status, got.body, tc.message)
			}
		})
	}
}

func TestPlayingGames_WhenOneFixedSeatGameStartedAndOnePending_ShouldListTheStartedOneEastToNorthToTheInternalCallerOnly(t *testing.T) {
	seed, err := engine.ParseSeed(strings.Repeat("ee", engine.SeedBytes))
	if err != nil {
		t.Fatalf("ParseSeed error = %v", err)
	}
	if dealer, _, _ := engine.FirstDealer(seed); dealer.Index() != 3 || engine.SeatPermutation(seed)[0].Index() == 3 {
		t.Fatalf("seed deals from seat %d and shuffles alice to %v, want a dealer the shuffle would not seat her at", dealer.Index(), engine.SeatPermutation(seed)[0])
	}
	h := newHarness(t, withSeed(seed))
	fixed := map[string]any{"game_id": testGameID, "num_ai_players": 3, "players": gameBody(testGameID, "alice").Players, "fixed_seats": true}
	if got := h.postGame(fixed); got.status != http.StatusCreated {
		t.Fatalf("POST /games with fixed seats = %d %v, want 201", got.status, got.body)
	}
	ws := h.joinAlice()
	readUntil(t, ws, isGameStarted)
	if got := h.postGame(gameBody("game-0002", "bob")); got.status != http.StatusCreated {
		t.Fatalf("POST /games for the pending game = %d %v, want 201", got.status, got.body)
	}

	listed := h.internal(http.MethodGet, "/games")
	refused := h.get("/games")

	games, _ := listed.body["games"].([]any)
	if len(games) != 1 {
		t.Fatalf("GET /games = %d %v, want the one started game", listed.status, listed.body)
	}
	game, _ := games[0].(map[string]any)
	startedAt, _ := game["started_at"].(float64)
	if age := time.Since(time.UnixMicro(int64(startedAt * 1e6))); age < 0 || age > time.Minute {
		t.Errorf("GET /games started_at = %v, want the start in epoch seconds", game["started_at"])
	}
	delete(game, "started_at")
	want := []any{map[string]any{
		"game_id":   testGameID,
		"game_type": "hanchan",
		"players":   []any{"alice", "ai-tsumogiri-1", "ai-tsumogiri-2", "ai-tsumogiri-3"},
	}}
	if listed.status != http.StatusOK || !cmp.Equal(games, want) {
		t.Errorf("GET /games = %d %v, want 200 %v", listed.status, listed.body, want)
	}
	if got := listed.header.Get("Cache-Control"); got != "no-store" {
		t.Errorf("GET /games Cache-Control = %q, want no-store", got)
	}
	if refused.status != http.StatusUnauthorized || refused.body["error"] != "Unauthorized" {
		t.Errorf("GET /games without the secret = %d %v, want 401", refused.status, refused.body)
	}
}

type shiftedClock struct {
	shift atomic.Int64
}

func (c *shiftedClock) Now() time.Time {
	return time.Now().Add(time.Duration(c.shift.Load()))
}

func (c *shiftedClock) AfterFunc(d time.Duration, f func()) func() bool {
	return time.AfterFunc(d, f).Stop
}

func (c *shiftedClock) advance(d time.Duration) {
	c.shift.Add(int64(d))
}

func withObserving(clock session.Clock, delay time.Duration) option {
	return func(_ *server.Config, s *session.Config) { s.Clock, s.ObserveDelay = clock, delay }
}

type observed struct {
	fields  wire.StrMap
	records []wire.Map
}

func (h *harness) observe(from int) observed {
	h.t.Helper()
	got := h.internal(http.MethodGet, "/games/"+testGameID+"/observe?from="+strconv.Itoa(from))
	if got.status != http.StatusOK || got.header.Get("Content-Type") != "application/msgpack" {
		h.t.Fatalf("GET observe from %d = %d %q %q, want 200 msgpack", from, got.status, got.header.Get("Content-Type"), got.text)
	}
	fields, err := wire.DecodeStrMap([]byte(got.text))
	if err != nil {
		h.t.Fatalf("decode the observe answer from %d: %v", from, err)
	}
	raw, _ := fields.Get("records")
	content, ok := raw.(wire.Bin)
	if !ok {
		h.t.Fatalf("observe answer records = %T, want bin", raw)
	}
	var records []wire.Map
	if len(content) > 0 {
		records, err = wire.DecodeRecords(content)
		if err != nil {
			h.t.Fatalf("decode the observed records from %d: %v", from, err)
		}
	}
	return observed{fields: fields, records: records}
}

func (o observed) number(t *testing.T, key string) int {
	t.Helper()
	v, _ := o.fields.Get(key)
	n, ok := v.(wire.Int)
	if !ok {
		t.Fatalf("observe answer %s = %v, want an int", key, v)
	}
	return int(n)
}

func (o observed) stamps(t *testing.T) []int {
	t.Helper()
	v, _ := o.fields.Get("stamps")
	values, ok := v.(wire.Array)
	if !ok {
		t.Fatalf("observe answer stamps = %v, want an array", v)
	}
	stamps := make([]int, 0, len(values))
	for _, value := range values {
		stamp, ok := value.(wire.Int)
		if !ok {
			t.Fatalf("observe answer stamp = %v, want an int", value)
		}
		stamps = append(stamps, int(stamp))
	}
	return stamps
}

func checkStamps(t *testing.T, poll observed, records int) {
	t.Helper()
	stamps, cutoff := poll.stamps(t), poll.number(t, "cutoff_ms")
	if len(stamps) != records || !slices.IsSorted(stamps) || slices.ContainsFunc(stamps, func(s int) bool { return s > cutoff }) {
		t.Fatalf("observe stamps = %v with cutoff %d, want %d non-decreasing stamps none past the cutoff", stamps, cutoff, records)
	}
}

func versionRecords(records []wire.Map) int {
	count := 0
	for _, record := range records {
		if _, ok := record.Get(wire.KeyReplayVersion); ok {
			count++
		}
	}
	return count
}

func seeded(records []wire.Map) bool {
	return slices.ContainsFunc(records, func(record wire.Map) bool {
		_, ok := record.Get(wire.KeySeed)
		return ok
	})
}

func TestObserveGame_WhenPolledAcrossTheDelay_ShouldServeOldRecordsOnceVersionedAndSeedFree(t *testing.T) {
	clock := &shiftedClock{}
	h := newHarness(t, withObserving(clock, time.Minute))
	h.create("alice", "bob")
	alice := h.joinAlice()
	bob := h.dial(testGameID, nil)
	send(t, bob, joinMessage(ticketFor(testGameID, "bob")))
	readUntil(t, alice, isGameStarted)

	early := h.observe(0)
	clock.advance(30 * time.Second)
	later := h.observe(0)
	for _, poll := range []observed{early, later} {
		if poll.number(t, "next") != 0 || len(poll.records) != 0 || poll.number(t, "available_in_ms") <= 0 ||
			len(poll.stamps(t)) != 0 || poll.number(t, "cutoff_ms") >= 0 {
			t.Errorf("observe during the delay = %v, want no records or stamps, next 0, the wait left and a cutoff before the start", poll.fields)
		}
	}
	startedAt := time.UnixMilli(int64(early.number(t, "started_at")))
	if age := time.Since(startedAt); age < 0 || age > time.Minute {
		t.Errorf("observe started_at = %v, want the start in Unix milliseconds", startedAt)
	}

	_ = bob.Close(websocket.StatusNormalClosure, "")
	readUntil(t, alice, func(m wire.Map) bool { return sessionType(m) == "seat_control" })
	clock.advance(31 * time.Second)
	first := h.observe(0)
	clock.advance(30 * time.Second)
	delta := h.observe(first.number(t, "next"))

	if len(first.records) < 2 || versionRecords(first.records) != 1 || versionRecords(first.records[:1]) != 1 ||
		!isGameStarted(first.records[1]) {
		t.Errorf("first observed batch = %v, want the version record and then the start", first.records)
	}
	if first.number(t, "next") != len(first.records)-1 {
		t.Errorf("first observed batch next = %d, want its %d records past the version record", first.number(t, "next"), len(first.records)-1)
	}
	if len(delta.records) == 0 || versionRecords(delta.records) != 0 {
		t.Fatalf("observed delta = %v, want bob's leave and no version record", delta.records)
	}
	checkStamps(t, first, len(first.records)-1)
	checkStamps(t, delta, len(delta.records))
	if slices.Min(delta.stamps(t)) < 30_000 || delta.number(t, "cutoff_ms") < 31_000 {
		t.Errorf("observed delta stamps %v and cutoff %d, want milliseconds since the start, the leave 30 s in",
			delta.stamps(t), delta.number(t, "cutoff_ms"))
	}
	if seeded(first.records) || seeded(delta.records) {
		t.Errorf("an observed record holds the seed")
	}
	if gone := h.internal(http.MethodGet, "/games/game-9999/observe"); gone.status != http.StatusNotFound {
		t.Errorf("GET observe of an unknown game = %d, want 404", gone.status)
	}
	refused := h.get("/games/" + testGameID + "/observe")
	if refused.status != http.StatusUnauthorized || refused.header.Get("Cache-Control") != "no-store" {
		t.Errorf("GET observe without the secret = %d, Cache-Control %q, want 401 no-store",
			refused.status, refused.header.Get("Cache-Control"))
	}
	if negative := h.internal(http.MethodGet, "/games/"+testGameID+"/observe?from=-1"); negative.status != http.StatusBadRequest {
		t.Errorf("GET observe from -1 = %d, want 400", negative.status)
	}
}

func TestCreateGame_WhenIDTaken_ShouldAnswer409(t *testing.T) {
	h := newHarness(t)
	h.create("alice")

	got := h.postGame(gameBody(testGameID, "bob"))

	if got.status != http.StatusConflict || got.body["error"] != "Game with this ID already exists" {
		t.Errorf("POST /games = %d %v, want 409 for the taken id", got.status, got.body)
	}
}

func TestCreateGame_WhenAPlayerIsAlreadyPlaying_ShouldAnswer409(t *testing.T) {
	h := newHarness(t)
	h.create("alice")

	got := h.postGame(gameBody("game-0002", "alice"))

	if got.status != http.StatusConflict || got.body["error"] != "Player already in a game" {
		t.Errorf("POST /games = %d %v, want 409 for the playing player", got.status, got.body)
	}
}

func TestCreateGame_WhenAtCapacity_ShouldAnswer503(t *testing.T) {
	h := newHarness(t, withCapacity(1))
	h.create("alice")

	got := h.postGame(gameBody("game-0002", "bob"))

	if got.status != http.StatusServiceUnavailable || got.body["error"] != "Server at capacity" {
		t.Errorf("POST /games = %d %v, want 503", got.status, got.body)
	}
}

func TestCreateGame_WhenBodyOversized_ShouldAnswer413(t *testing.T) {
	h := newHarness(t)

	got := h.request(http.MethodPost, "/games", bytes.NewReader(bytes.Repeat([]byte(" "), 4097)), nil)

	if got.status != http.StatusRequestEntityTooLarge {
		t.Errorf("POST /games status = %d, want 413", got.status)
	}
}

func TestWithdrawGame_WhenNobodyJoined_ShouldAnswer204AndRefuseTheID(t *testing.T) {
	h := newHarness(t)
	h.create("alice")

	got := h.internal(http.MethodDelete, "/games/"+testGameID)

	if got.status != http.StatusNoContent {
		t.Errorf("DELETE /games/%s status = %d, want 204", testGameID, got.status)
	}
	if again := h.postGame(gameBody(testGameID, "alice")); again.status != http.StatusConflict {
		t.Errorf("POST /games after the withdrawal = %d, want 409", again.status)
	}
}

func TestWithdrawGame_WhenAPlayerJoined_ShouldAnswer409AndKeepIt(t *testing.T) {
	h := newHarness(t)
	h.create("alice", "bob")
	h.joinAlice()

	got := h.internal(http.MethodDelete, "/games/"+testGameID)

	if got.status != http.StatusConflict || got.body["error"] != "Game already joined" {
		t.Errorf("DELETE /games/%s = %d %v, want 409", testGameID, got.status, got.body)
	}
}

func TestWithdrawGame_WhenCallerLacksTheInternalSecret_ShouldAnswer401(t *testing.T) {
	h := newHarness(t)
	h.create("alice")

	got := h.request(http.MethodDelete, "/games/"+testGameID, nil, map[string]string{"Authorization": "Bearer wrong"})

	if got.status != http.StatusUnauthorized {
		t.Errorf("DELETE /games/%s status = %d, want 401", testGameID, got.status)
	}
	if counter(t, h.status(), "pending_games") != 1 {
		t.Error("an unauthorized withdrawal dropped the game")
	}
}

func TestPlayerGame_WhenUserPlays_ShouldAnswerTheGameAndOtherwise404(t *testing.T) {
	h := newHarness(t)
	h.create("alice")

	playing, idle := h.get("/players/user-alice"), h.get("/players/user-bob")

	if playing.status != http.StatusOK || !cmp.Equal(playing.body, map[string]any{"game_id": testGameID}) {
		t.Errorf("GET /players/user-alice = %d %v, want 200 with the game", playing.status, playing.body)
	}
	if idle.status != http.StatusNotFound {
		t.Errorf("GET /players/user-bob status = %d, want 404", idle.status)
	}
}

func TestPlayerGameSession_WhenCallerIsInternal_ShouldAnswerTheTicketUncached(t *testing.T) {
	h := newHarness(t)
	body := gameBody(testGameID, "alice")
	h.postGame(body)

	got := h.internal(http.MethodGet, "/players/user-alice/game-session")

	want := map[string]any{"game_id": testGameID, "game_ticket": body.Players[0].Ticket}
	if got.status != http.StatusOK || !cmp.Equal(got.body, want) {
		t.Errorf("GET game-session = %d %v, want 200 %v", got.status, got.body, want)
	}
	if got.header.Get("Cache-Control") != "no-store" {
		t.Errorf("GET game-session Cache-Control = %q, want no-store", got.header.Get("Cache-Control"))
	}
}

func TestPlayerGameSession_WhenCallerLacksTheInternalSecret_ShouldAnswer401WithoutTheTicket(t *testing.T) {
	h := newHarness(t)
	h.create("alice")

	got := h.get("/players/user-alice/game-session")

	if got.status != http.StatusUnauthorized || got.body["game_ticket"] != nil {
		t.Errorf("GET game-session = %d %v, want 401 without a ticket", got.status, got.body)
	}
	if got.header.Get("Cache-Control") != "no-store" {
		t.Errorf("GET game-session Cache-Control = %q, want no-store", got.header.Get("Cache-Control"))
	}
}

func TestCORS_WhenOriginAllowed_ShouldLetItReadTheAnswer(t *testing.T) {
	h := newHarness(t)

	got := h.request(http.MethodGet, "/health", nil, map[string]string{"Origin": lobbyOrigin})

	if got.header.Get("Access-Control-Allow-Origin") != lobbyOrigin || got.header.Get("Vary") != "Origin" {
		t.Errorf("CORS headers = %v, want the lobby origin allowed", got.header)
	}
}

func TestCORS_WhenPreflightComesFromAForeignOrigin_ShouldAnswer400(t *testing.T) {
	h := newHarness(t)

	got := h.request(http.MethodOptions, "/games", nil, map[string]string{
		"Origin": "http://evil.test", "Access-Control-Request-Method": http.MethodPost,
	})

	if got.status != http.StatusBadRequest || got.header.Get("Access-Control-Allow-Origin") != "" {
		t.Errorf("preflight = %d %v, want 400 with no allowed origin", got.status, got.header)
	}
}
