package server_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/coder/websocket"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/server"
)

func TestHealth_ShouldAnswerOKStatus(t *testing.T) {
	recorder := httptest.NewRecorder()
	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/health", nil)

	server.NewHandler().ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("GET /health status = %d, want %d", recorder.Code, http.StatusOK)
	}

	var body map[string]string
	err := json.Unmarshal(recorder.Body.Bytes(), &body)
	if err != nil {
		t.Fatalf("decode body %q: %v", recorder.Body.String(), err)
	}
	if len(body) != 1 || body["status"] != "ok" {
		t.Errorf("GET /health body = %v, want only status ok", body)
	}
}

func TestSocket_WhenClientDials_ShouldUpgradeAndCloseNormally(t *testing.T) {
	srv := httptest.NewServer(server.NewHandler())
	t.Cleanup(srv.Close)

	conn, _, err := websocket.Dial(t.Context(), srv.URL+"/ws", &websocket.DialOptions{HTTPClient: srv.Client()})
	if err != nil {
		t.Fatalf("dial /ws: %v", err)
	}
	t.Cleanup(func() { _ = conn.CloseNow() })

	_, _, readErr := conn.Read(t.Context())
	if status := websocket.CloseStatus(readErr); status != websocket.StatusNormalClosure {
		t.Errorf("read after upgrade: close status = %d (%v), want %d", status, readErr, websocket.StatusNormalClosure)
	}
}
