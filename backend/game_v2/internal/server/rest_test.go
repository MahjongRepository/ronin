package server_test

import (
	"bytes"
	"maps"
	"net/http"
	"os"
	"regexp"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/auth"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
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
