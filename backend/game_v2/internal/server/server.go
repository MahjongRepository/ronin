// Package server is the game server's HTTP transport.
package server

import (
	"log/slog"
	"net/http"
)

// NewHandler returns the handler serving every game server route.
func NewHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", health)
	return mux
}

func health(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	_, err := w.Write([]byte(`{"status":"ok"}`))
	if err != nil {
		slog.Error("write health response", "error", err)
	}
}
