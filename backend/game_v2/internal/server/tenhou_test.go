package server_test

import (
	"net/http"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/tenhou"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	unfinishedReplayPath = "../wire/testdata/rewritten/chankan_added.msgpack"
	storedGameID         = "stored-game"
	failedGameID         = "failed-game"
)

func unfinishedReplay(t *testing.T) []byte {
	t.Helper()
	content, err := os.ReadFile(unfinishedReplayPath)
	if err != nil {
		t.Fatalf("read %s: %v", unfinishedReplayPath, err)
	}

	return content
}

func finishedReplay(t *testing.T) []byte {
	t.Helper()
	records, err := wire.DecodeReplay(unfinishedReplay(t))
	if err != nil {
		t.Fatalf("DecodeReplay error = %v", err)
	}

	var standings wire.Array
	for seat, score := range []int{250, 130, 370, 250} {
		standings = append(standings, wire.Map{
			{Key: wire.KeySeat, Value: wire.Int(seat)},
			{Key: wire.KeyScore, Value: wire.Int(score)},
			{Key: wire.KeyFinalScore, Value: wire.Int(0)},
		})
	}

	records = append(records, wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(wire.EventGameEnd)},
		{Key: wire.KeyWinnerSeat, Value: wire.Int(2)},
		{Key: wire.KeyStandings, Value: standings},
		{Key: wire.KeyLeftoverBonus, Value: wire.Int(0)},
		{Key: wire.KeyLeftoverRiichi, Value: wire.Int(0)},
		{Key: wire.KeyRoundCount, Value: wire.Int(1)},
		{Key: wire.KeyEndCause, Value: wire.Str("length")},
	})
	content, err := wire.EncodeReplay(records)
	if err != nil {
		t.Fatalf("EncodeReplay error = %v", err)
	}

	return content
}

func (h *harness) storeReplay(gameID string, content []byte) {
	h.t.Helper()
	err := h.replays.Save(gameID, content)
	if err != nil {
		h.t.Fatalf("Save(%s) error = %v", gameID, err)
	}
}

func TestTenhouReplay_WhenTheReplayIsStored_ShouldAnswerItsTenhouXMLAndOtherwise404(t *testing.T) {
	h := newHarness(t)
	content := finishedReplay(t)
	h.storeReplay(storedGameID, content)
	want, err := tenhou.Convert(content)
	if err != nil {
		t.Fatalf("Convert error = %v", err)
	}

	got := h.internal(http.MethodGet, "/replays/"+storedGameID+"/tenhou")
	if got.status != http.StatusOK || got.header.Get("Content-Type") != "application/xml" || got.text != want {
		t.Errorf("GET tenhou = %d %q %q, want 200 application/xml %q", got.status, got.header.Get("Content-Type"), got.text, want)
	}

	missing := h.internal(http.MethodGet, "/replays/missing-game/tenhou")
	if missing.status != http.StatusNotFound || !cmp.Equal(missing.body, map[string]any{"error": "Replay not found"}) {
		t.Errorf("GET tenhou of a missing replay = %d %v, want 404", missing.status, missing.body)
	}
}

func TestTenhouReplay_WhenTheReplayIsAFailedGame_ShouldAnswer422NotATruncatedLog(t *testing.T) {
	h := newHarness(t)
	h.storeReplay(failedGameID, unfinishedReplay(t))

	got := h.internal(http.MethodGet, "/replays/"+failedGameID+"/tenhou")
	if got.status != http.StatusUnprocessableEntity || !cmp.Equal(got.body, map[string]any{"error": "Replay has no game end"}) {
		t.Errorf("GET tenhou = %d %v, want 422", got.status, got.body)
	}
}

func TestTenhouReplay_WhenCallerLacksTheInternalSecret_ShouldAnswer401(t *testing.T) {
	h := newHarness(t)
	h.storeReplay(storedGameID, finishedReplay(t))

	got := h.request(http.MethodGet, "/replays/"+storedGameID+"/tenhou", nil, map[string]string{"Authorization": "Bearer wrong"})
	if got.status != http.StatusUnauthorized || got.body["error"] != "Unauthorized" {
		t.Errorf("GET tenhou = %d %v, want 401", got.status, got.body)
	}
}
