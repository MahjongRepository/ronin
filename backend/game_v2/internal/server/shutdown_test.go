package server_test

import (
	"database/sql"
	"net/http"
	"testing"

	"github.com/coder/websocket"
)

func TestShutdown_ShouldCloseSocketsWith1012AsDisconnectsBeforeTheSessionDrains(t *testing.T) {
	h := newHarness(t)
	h.create("alice")
	ws := h.joinAlice()
	readUntil(t, ws, isGameStarted)

	closed := awaitClose(t, ws)

	h.shutdown()
	if code := websocket.CloseStatus(<-closed); code != websocket.StatusServiceRestart {
		t.Errorf("close = %d, want 1012", code)
	}

	var endReason sql.NullString
	err := h.openDB(t).QueryRowContext(t.Context(), "SELECT end_reason FROM played_games WHERE id = ?", testGameID).Scan(&endReason)
	if err != nil {
		t.Fatalf("read the game's row: %v", err)
	}
	if endReason.String != "abandoned" {
		t.Errorf("end_reason = %q once Shutdown returned, want abandoned through the disconnect", endReason.String)
	}
	if got := h.postGame(gameBody("game-0002", "bob")); got.status != http.StatusServiceUnavailable {
		t.Errorf("POST /games after Shutdown = %d, want 503", got.status)
	}
}
