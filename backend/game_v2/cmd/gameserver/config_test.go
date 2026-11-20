package main

import (
	"errors"
	"log/slog"
	"maps"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func env(overrides map[string]string) func(string) string {
	values := map[string]string{
		"GAME_REPLAY_DIR":          "/data/replays",
		"GAME_CORS_ORIGINS":        "http://localhost:8710",
		"AUTH_DATABASE_PATH":       "/data/game.db",
		"AUTH_GAME_TICKET_SECRET":  "ticket-secret",
		"AUTH_INTERNAL_API_SECRET": "internal-secret",
		"APP_VERSION":              "",
		"GIT_COMMIT":               "abc1234",
	}
	maps.Copy(values, overrides)
	return func(name string) string { return values[name] }
}

func TestLoadConfig_WhenOptionalVariablesUnset_ShouldUseThePythonDefaults(t *testing.T) {
	cfg, err := loadConfig(env(nil))
	if err != nil {
		t.Fatalf("loadConfig error = %v", err)
	}

	got := []any{cfg.capacity, cfg.logLevel, cfg.logJSON, cfg.logDir, cfg.version, cfg.commit}
	want := []any{100, slog.LevelInfo, false, "", "dev", "abc1234"}
	if !cmp.Equal(got, want) {
		t.Errorf("capacity, level, json, log dir, version, commit = %v, want %v", got, want)
	}
}

func TestLoadConfig_WhenCORSOriginsListed_ShouldReadAJSONArrayOrACommaList(t *testing.T) {
	want := []string{"http://a.test", "http://b.test"}
	for _, value := range []string{`["http://a.test","http://b.test"]`, " http://a.test, http://b.test ,"} {
		cfg, err := loadConfig(env(map[string]string{"GAME_CORS_ORIGINS": value}))
		if err != nil {
			t.Fatalf("loadConfig(GAME_CORS_ORIGINS=%q) error = %v", value, err)
		}
		if !cmp.Equal(cfg.corsOrigins, want) {
			t.Errorf("GAME_CORS_ORIGINS=%q read as %v, want %v", value, cfg.corsOrigins, want)
		}
	}
}

func TestLoadConfig_WhenAVariableIsMissingOrInvalid_ShouldRefuseNamingIt(t *testing.T) {
	tests := []struct {
		name     string
		variable string
		value    string
		want     error
	}{
		{"no replay dir", "GAME_REPLAY_DIR", "", errMissing},
		{"no ticket secret", "AUTH_GAME_TICKET_SECRET", "", errMissing},
		{"capacity of zero", "GAME_MAX_CAPACITY", "0", errCapacity},
		{"no cors origin", "GAME_CORS_ORIGINS", " , ", errStringList},
		{"cors json of no string", "GAME_CORS_ORIGINS", "[1]", errStringList},
		{"unknown log level", "LOG_LEVEL", "VERBOSE", errLogLevel},
		{"unknown log format", "LOG_FORMAT", "xml", errLogFormat},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			_, err := loadConfig(env(map[string]string{tc.variable: tc.value}))

			if !errors.Is(err, tc.want) {
				t.Errorf("loadConfig(%s=%q) error = %v, want %v", tc.variable, tc.value, err, tc.want)
			}
		})
	}
}
