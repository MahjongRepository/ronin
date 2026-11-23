CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    api_key_hash TEXT,
    data TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_players_username
    ON players (username COLLATE NOCASE);

CREATE UNIQUE INDEX IF NOT EXISTS idx_players_api_key_hash
    ON players (api_key_hash) WHERE api_key_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS played_games (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    end_reason TEXT,
    data TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_played_games_started_at
    ON played_games (started_at DESC);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    is_guest INTEGER NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
    ON sessions (expires_at);

CREATE TABLE IF NOT EXISTS tournaments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tournaments_owner_user_id
    ON tournaments (owner_user_id);

CREATE TABLE IF NOT EXISTS tournament_games (
    game_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL,
    players TEXT NOT NULL,
    created_at REAL NOT NULL,
    ended_at REAL,
    end_reason TEXT,
    result TEXT
);

CREATE INDEX IF NOT EXISTS idx_tournament_games_tournament_id
    ON tournament_games (tournament_id);
