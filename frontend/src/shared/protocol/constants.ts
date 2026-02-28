// Wire protocol constants as const objects with derived union types.
// Replaces legacy TypeScript enums from protocol.ts.

// --- Numeric constants ---

export const NUM_TILES = 136;
export const NUM_TILE_TYPES = 34;
export const NUM_PLAYERS = 4;
export const WIRE_SCORE_DIVISOR = 100;
export const SEAT_TILE_SPACE = 544; // NUM_PLAYERS * NUM_TILES
export const NUM_DISCARD_FLAGS = 4;

// --- Game event types (integer `t` field, 0-11) ---

export const EVENT_TYPE = {
    CALL_PROMPT: 3,
    DISCARD: 2,
    DORA_REVEALED: 6,
    DRAW: 1,
    ERROR: 7,
    FURITEN: 11,
    GAME_END: 10,
    GAME_STARTED: 8,
    MELD: 0,
    RIICHI_DECLARED: 5,
    ROUND_END: 4,
    ROUND_STARTED: 9,
} as const;

export type EventType = (typeof EVENT_TYPE)[keyof typeof EVENT_TYPE];

// --- Client message types (integer `t` field) ---

export const CLIENT_MESSAGE_TYPE = {
    CHAT: 4,
    GAME_ACTION: 3,
    JOIN_GAME: 7,
    PING: 5,
    RECONNECT: 6,
} as const;

export type ClientMessageType = (typeof CLIENT_MESSAGE_TYPE)[keyof typeof CLIENT_MESSAGE_TYPE];

// --- Game actions (integer `a` field, 0-9) ---

export const GAME_ACTION = {
    CALL_CHI: 5,
    CALL_KAN: 6,
    CALL_KYUUSHU: 7,
    CALL_PON: 4,
    CALL_RON: 3,
    CONFIRM_ROUND: 9,
    DECLARE_RIICHI: 1,
    DECLARE_TSUMO: 2,
    DISCARD: 0,
    PASS: 8,
} as const;

export type GameAction = (typeof GAME_ACTION)[keyof typeof GAME_ACTION];

// --- Session message types (string `type` field) ---

export const SESSION_MESSAGE_TYPE = {
    CHAT: "chat",
    ERROR: "session_error",
    GAME_LEFT: "game_left",
    GAME_RECONNECTED: "game_reconnected",
    PLAYER_LEFT: "player_left",
    PLAYER_RECONNECTED: "player_reconnected",
    PONG: "pong",
} as const;

export type SessionMessageType = (typeof SESSION_MESSAGE_TYPE)[keyof typeof SESSION_MESSAGE_TYPE];

// --- Player actions (integer, in draw event `aa` array) ---

export const PLAYER_ACTION = {
    ADDED_KAN: 4,
    DISCARD: 0,
    KAN: 3,
    KYUUSHU: 5,
    RIICHI: 1,
    TSUMO: 2,
} as const;

export type PlayerAction = (typeof PLAYER_ACTION)[keyof typeof PLAYER_ACTION];

// --- Call types (in call_prompt `clt` field) ---

export const CALL_TYPE = {
    CHANKAN: 2,
    MELD: 1,
    RON: 0,
} as const;

export type CallType = (typeof CALL_TYPE)[keyof typeof CALL_TYPE];

// --- Meld call types (in available_calls `clt` field) ---

export const MELD_CALL_TYPE = {
    CHI: 1,
    OPEN_KAN: 2,
    PON: 0,
} as const;

export type MeldCallType = (typeof MELD_CALL_TYPE)[keyof typeof MELD_CALL_TYPE];

// --- Round result types (integer `rt` field, 0-5) ---

export const ROUND_RESULT_TYPE = {
    ABORTIVE_DRAW: 4,
    DOUBLE_RON: 2,
    EXHAUSTIVE_DRAW: 3,
    NAGASHI_MANGAN: 5,
    RON: 1,
    TSUMO: 0,
} as const;

export type RoundResultType = (typeof ROUND_RESULT_TYPE)[keyof typeof ROUND_RESULT_TYPE];

// --- Wind values (integer, 0-3) ---

export const WIND = {
    EAST: 0,
    NORTH: 3,
    SOUTH: 1,
    WEST: 2,
} as const;

export type Wind = (typeof WIND)[keyof typeof WIND];

// --- Kan types (string, client -> server) ---

export const KAN_TYPE = {
    ADDED: "added",
    CLOSED: "closed",
    OPEN: "open",
} as const;

export type KanType = (typeof KAN_TYPE)[keyof typeof KAN_TYPE];

// --- Meld types (string, decoded from IMME) ---

export const MELD_TYPE = {
    ADDED_KAN: "added_kan",
    CHI: "chi",
    CLOSED_KAN: "closed_kan",
    OPEN_KAN: "open_kan",
    PON: "pon",
} as const;

export type MeldType = (typeof MELD_TYPE)[keyof typeof MELD_TYPE];

// --- Connection status (client-only) ---

export const CONNECTION_STATUS = {
    CONNECTED: "connected",
    CONNECTING: "connecting",
    DISCONNECTED: "disconnected",
    ERROR: "error",
} as const;

export type ConnectionStatus = (typeof CONNECTION_STATUS)[keyof typeof CONNECTION_STATUS];

// --- Abortive draw types (string) ---

export const ABORTIVE_DRAW_TYPE = {
    FOUR_KANS: "four_kans",
    FOUR_RIICHI: "four_riichi",
    FOUR_WINDS: "four_winds",
    NINE_TERMINALS: "nine_terminals",
    TRIPLE_RON: "triple_ron",
} as const;

export type AbortiveDrawType = (typeof ABORTIVE_DRAW_TYPE)[keyof typeof ABORTIVE_DRAW_TYPE];

// --- Session error codes (string) ---

export const SESSION_ERROR_CODE = {
    ACTION_FAILED: "action_failed",
    ALREADY_IN_GAME: "already_in_game",
    GAME_NOT_STARTED: "game_not_started",
    INVALID_MESSAGE: "invalid_message",
    INVALID_TICKET: "invalid_ticket",
    JOIN_GAME_ALREADY_STARTED: "join_game_already_started",
    JOIN_GAME_NOT_FOUND: "join_game_not_found",
    JOIN_GAME_NO_SESSION: "join_game_no_session",
    NOT_IN_GAME: "not_in_game",
    RATE_LIMITED: "rate_limited",
    RECONNECT_ALREADY_ACTIVE: "reconnect_already_active",
    RECONNECT_GAME_GONE: "reconnect_game_gone",
    RECONNECT_GAME_MISMATCH: "reconnect_game_mismatch",
    RECONNECT_NO_SEAT: "reconnect_no_seat",
    RECONNECT_NO_SESSION: "reconnect_no_session",
    RECONNECT_RETRY_LATER: "reconnect_retry_later",
    RECONNECT_SNAPSHOT_FAILED: "reconnect_snapshot_failed",
} as const;

export type SessionErrorCode = (typeof SESSION_ERROR_CODE)[keyof typeof SESSION_ERROR_CODE];

// --- Internal message types (client-only) ---

export const INTERNAL_MESSAGE_TYPE = {
    DECODE_ERROR: "decode_error",
} as const;

export type InternalMessageType =
    (typeof INTERNAL_MESSAGE_TYPE)[keyof typeof INTERNAL_MESSAGE_TYPE];

// --- Log type constants ---

export const LOG_TYPE_SYSTEM = "system";
export const LOG_TYPE_UNKNOWN = "unknown";
