package main

import (
	"cmp"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"runtime/debug"
	"strconv"
	"strings"
)

const (
	defaultCapacity  = 100
	defaultVersion   = "dev"
	shortCommitChars = 7
	logFormatJSON    = "json"
	logFormatConsole = "console"
)

type config struct {
	capacity       int
	logDir         string
	corsOrigins    []string
	replayDir      string
	databasePath   string
	ticketSecret   string
	internalSecret string
	logLevel       slog.Level
	logJSON        bool
	version        string
	commit         string
}

var errMissing = errors.New("required")

func loadConfig(getenv func(string) string) (config, error) {
	cfg := config{
		logDir:         getenv("GAME_LOG_DIR"),
		replayDir:      getenv("GAME_REPLAY_DIR"),
		databasePath:   getenv("AUTH_DATABASE_PATH"),
		ticketSecret:   getenv("AUTH_GAME_TICKET_SECRET"),
		internalSecret: getenv("AUTH_INTERNAL_API_SECRET"),
		version:        cmp.Or(getenv("APP_VERSION"), defaultVersion),
		commit:         cmp.Or(getenv("GIT_COMMIT"), buildCommit()),
	}
	for _, name := range [...]string{
		"GAME_REPLAY_DIR", "AUTH_DATABASE_PATH", "AUTH_GAME_TICKET_SECRET", "AUTH_INTERNAL_API_SECRET",
	} {
		if getenv(name) == "" {
			return config{}, fmt.Errorf("%s: %w", name, errMissing)
		}
	}

	var err error
	cfg.capacity, err = capacityOf(getenv("GAME_MAX_CAPACITY"))
	if err != nil {
		return config{}, fmt.Errorf("GAME_MAX_CAPACITY: %w", err)
	}
	cfg.corsOrigins, err = stringListOf(getenv("GAME_CORS_ORIGINS"))
	if err != nil {
		return config{}, fmt.Errorf("GAME_CORS_ORIGINS: %w", err)
	}
	cfg.logLevel, err = logLevelOf(getenv("LOG_LEVEL"))
	if err != nil {
		return config{}, fmt.Errorf("LOG_LEVEL: %w", err)
	}
	cfg.logJSON, err = logJSONOf(getenv("LOG_FORMAT"))
	if err != nil {
		return config{}, fmt.Errorf("LOG_FORMAT: %w", err)
	}
	return cfg, nil
}

func buildCommit() string {
	info, ok := debug.ReadBuildInfo()
	if !ok {
		return defaultVersion
	}
	for _, setting := range info.Settings {
		if setting.Key == "vcs.revision" && setting.Value != "" {
			return setting.Value[:min(shortCommitChars, len(setting.Value))]
		}
	}
	return defaultVersion
}

var errCapacity = errors.New("must be an integer of 1 or more")

func capacityOf(value string) (int, error) {
	if value == "" {
		return defaultCapacity, nil
	}
	n, err := strconv.Atoi(strings.TrimSpace(value))
	if err != nil || n < 1 {
		return 0, errCapacity
	}
	return n, nil
}

var errStringList = errors.New("must be a non-empty JSON array of strings or comma-separated list")

func stringListOf(value string) ([]string, error) {
	trimmed := strings.TrimSpace(value)
	if strings.HasPrefix(trimmed, "[") {
		var list []string
		err := json.Unmarshal([]byte(trimmed), &list)
		if err != nil || len(list) == 0 {
			return nil, errStringList
		}
		return list, nil
	}

	var list []string
	for item := range strings.SplitSeq(trimmed, ",") {
		if item = strings.TrimSpace(item); item != "" {
			list = append(list, item)
		}
	}
	if len(list) == 0 {
		return nil, errStringList
	}
	return list, nil
}

var errLogLevel = errors.New("must be one of CRITICAL, DEBUG, ERROR, INFO, WARNING")

const levelCritical = slog.LevelError + 4

func logLevelOf(value string) (slog.Level, error) {
	switch strings.ToUpper(strings.TrimSpace(value)) {
	case "", "INFO":
		return slog.LevelInfo, nil
	case "DEBUG":
		return slog.LevelDebug, nil
	case "WARNING":
		return slog.LevelWarn, nil
	case "ERROR":
		return slog.LevelError, nil
	case "CRITICAL":
		return levelCritical, nil
	}
	return 0, errLogLevel
}

var errLogFormat = errors.New("must be 'json', 'console', or unset")

func logJSONOf(value string) (bool, error) {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case logFormatJSON:
		return true, nil
	case logFormatConsole, "":
		return false, nil
	}
	return false, errLogFormat
}
