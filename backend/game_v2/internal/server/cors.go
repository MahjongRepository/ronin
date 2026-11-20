package server

import (
	"net/http"
	"slices"
	"strings"
)

const (
	corsAllowMethods = "GET, POST"
	corsAllowHeaders = "Accept, Accept-Language, Content-Language, Content-Type"
	corsMaxAge       = "600"
	corsAnyOrigin    = "*"
	corsPreflightVar = "Origin, Access-Control-Request-Method, Access-Control-Request-Headers, " +
		"Access-Control-Request-Private-Network"
)

type cors struct {
	origins   []string
	anyOrigin bool
	next      http.Handler
}

func newCORS(origins []string, next http.Handler) cors {
	return cors{origins: origins, anyOrigin: slices.Contains(origins, corsAnyOrigin), next: next}
}

func (c cors) allows(origin string) bool {
	return c.anyOrigin || slices.Contains(c.origins, origin)
}

func (c cors) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	origin := r.Header.Get("Origin")
	switch {
	case origin == "":
	case r.Method == http.MethodOptions && r.Header.Get("Access-Control-Request-Method") != "":
		c.preflight(w, r, origin)
		return
	case c.anyOrigin:
		w.Header().Set("Access-Control-Allow-Origin", corsAnyOrigin)
		w.Header().Add("Vary", "Origin")
	case c.allows(origin):
		w.Header().Set("Access-Control-Allow-Origin", origin)
		w.Header().Add("Vary", "Origin")
	default:
		w.Header().Add("Vary", "Origin")
	}
	c.next.ServeHTTP(w, r)
}

func (c cors) preflight(w http.ResponseWriter, r *http.Request, origin string) {
	h := w.Header()
	h.Set("Vary", corsPreflightVar)
	h.Set("Access-Control-Allow-Methods", corsAllowMethods)
	h.Set("Access-Control-Max-Age", corsMaxAge)
	h.Set("Access-Control-Allow-Headers", corsAllowHeaders)

	var failures []string
	switch {
	case c.anyOrigin:
		h.Set("Access-Control-Allow-Origin", corsAnyOrigin)
	case c.allows(origin):
		h.Set("Access-Control-Allow-Origin", origin)
	default:
		failures = append(failures, "origin")
	}
	method := r.Header.Get("Access-Control-Request-Method")
	if method != http.MethodGet && method != http.MethodPost {
		failures = append(failures, "method")
	}
	if !allowedHeaders(r.Header.Get("Access-Control-Request-Headers")) {
		failures = append(failures, "headers")
	}
	if r.Header.Get("Access-Control-Request-Private-Network") != "" {
		failures = append(failures, "private-network")
	}

	h.Set("Content-Type", "text/plain; charset=utf-8")
	if len(failures) > 0 {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte("Disallowed CORS " + strings.Join(failures, ", ")))
		return
	}
	_, _ = w.Write([]byte("OK"))
}

func allowedHeaders(requested string) bool {
	if requested == "" {
		return true
	}
	allowed := strings.Split(strings.ToLower(corsAllowHeaders), ", ")
	for header := range strings.SplitSeq(requested, ",") {
		if !slices.Contains(allowed, strings.ToLower(strings.TrimSpace(header))) {
			return false
		}
	}
	return true
}
