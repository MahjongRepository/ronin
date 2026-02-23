export enum ClientMessageType {
    GAME_ACTION = 3,
    CHAT = 4,
    PING = 5,
    RECONNECT = 6,
    JOIN_GAME = 7,
}

export enum SessionMessageType {
    CHAT = "chat",
    ERROR = "session_error",
    PONG = "pong",
    GAME_RECONNECTED = "game_reconnected",
    PLAYER_RECONNECTED = "player_reconnected",
}

export enum EventType {
    MELD = 0,
    DRAW = 1,
    DISCARD = 2,
    CALL_PROMPT = 3,
    ROUND_END = 4,
    RIICHI_DECLARED = 5,
    DORA_REVEALED = 6,
    ERROR = 7,
    GAME_STARTED = 8,
    ROUND_STARTED = 9,
    GAME_END = 10,
    FURITEN = 11,
}

export enum GameAction {
    DISCARD = 0,
    DECLARE_RIICHI = 1,
    DECLARE_TSUMO = 2,
    CALL_RON = 3,
    CALL_PON = 4,
    CALL_CHI = 5,
    CALL_KAN = 6,
    CALL_KYUUSHU = 7,
    PASS = 8,
    CONFIRM_ROUND = 9,
}

export enum ConnectionStatus {
    CONNECTING = "connecting",
    CONNECTED = "connected",
    DISCONNECTED = "disconnected",
    ERROR = "error",
}

export enum InternalMessageType {
    DECODE_ERROR = "decode_error",
}

export const LOG_TYPE_SYSTEM = "system";
export const LOG_TYPE_UNKNOWN = "unknown";
