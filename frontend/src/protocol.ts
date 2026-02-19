export enum ClientMessageType {
    JOIN_ROOM = "join_room",
    LEAVE_ROOM = "leave_room",
    SET_READY = "set_ready",
    GAME_ACTION = "game_action",
    CHAT = "chat",
    PING = "ping",
    RECONNECT = "reconnect",
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
    DISCARD = "discard",
    DECLARE_RIICHI = "declare_riichi",
    DECLARE_TSUMO = "declare_tsumo",
    CALL_RON = "call_ron",
    CALL_PON = "call_pon",
    CALL_CHI = "call_chi",
    CALL_KAN = "call_kan",
    CALL_KYUUSHU = "call_kyuushu",
    PASS = "pass",
    CONFIRM_ROUND = "confirm_round",
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
