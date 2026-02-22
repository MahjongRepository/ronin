export enum ClientMessageType {
    JOIN_ROOM = 0,
    LEAVE_ROOM = 1,
    SET_READY = 2,
    GAME_ACTION = 3,
    CHAT = 4,
    PING = 5,
    RECONNECT = 6,
}

export enum SessionMessageType {
    ROOM_JOINED = "room_joined",
    ROOM_LEFT = "room_left",
    PLAYER_JOINED = "player_joined",
    PLAYER_LEFT = "player_left",
    PLAYER_READY_CHANGED = "player_ready_changed",
    GAME_STARTING = "game_starting",
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

export interface RoomPlayerInfo {
    name: string;
    ready: boolean;
}

export const LOG_TYPE_SYSTEM = "system";
export const LOG_TYPE_UNKNOWN = "unknown";
