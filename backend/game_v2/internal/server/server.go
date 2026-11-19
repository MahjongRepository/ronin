// Package server is the game server's HTTP transport.
package server

import (
	"log/slog"
	"net/http"

	"github.com/coder/websocket"
)

// NewHandler returns the handler serving every game server route.
func NewHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", health)
	mux.HandleFunc("GET /ws", acceptSocket)
	return mux
}

func health(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	_, err := w.Write([]byte(`{"status":"ok"}`))
	if err != nil {
		slog.Error("write health response", "error", err)
	}
}

func acceptSocket(w http.ResponseWriter, r *http.Request) {
	conn, err := websocket.Accept(w, r, nil)
	if err != nil {
		slog.Error("accept websocket", "error", err)
		return
	}

	closeErr := conn.Close(websocket.StatusNormalClosure, "")
	if closeErr != nil {
		slog.Error("close websocket", "error", closeErr)
	}
}
