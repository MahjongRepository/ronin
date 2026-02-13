export enum ClientMessageType {
    JOIN_ROOM = "join_room",
    LEAVE_ROOM = "leave_room",
    SET_READY = "set_ready",
    GAME_ACTION = "game_action",
    CHAT = "chat",
    PING = "ping",
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
}

export enum EventType {
    DRAW = "draw",
    DISCARD = "discard",
    MELD = "meld",
    CALL_PROMPT = "call_prompt",
    ROUND_END = "round_end",
    RIICHI_DECLARED = "riichi_declared",
    DORA_REVEALED = "dora_revealed",
    ERROR = "error",
    GAME_STARTED = "game_started",
    ROUND_STARTED = "round_started",
    GAME_END = "game_end",
    FURITEN = "furiten",
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
