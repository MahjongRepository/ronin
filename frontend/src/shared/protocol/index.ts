// Public API for the protocol module.
export {
    NUM_TILES,
    NUM_TILE_TYPES,
    NUM_PLAYERS,
    WIRE_SCORE_DIVISOR,
    SEAT_TILE_SPACE,
    NUM_DISCARD_FLAGS,
    EVENT_TYPE,
    CLIENT_MESSAGE_TYPE,
    GAME_ACTION,
    SESSION_MESSAGE_TYPE,
    PLAYER_ACTION,
    CALL_TYPE,
    MELD_CALL_TYPE,
    ROUND_RESULT_TYPE,
    WIND,
    KAN_TYPE,
    MELD_TYPE,
    CONNECTION_STATUS,
    ABORTIVE_DRAW_TYPE,
    SESSION_ERROR_CODE,
    INTERNAL_MESSAGE_TYPE,
    LOG_TYPE_SYSTEM,
    LOG_TYPE_UNKNOWN,
} from "./constants";

export type {
    EventType,
    ClientMessageType,
    GameAction,
    SessionMessageType,
    PlayerAction,
    CallType,
    MeldCallType,
    RoundResultType,
    Wind,
    KanType,
    MeldType,
    ConnectionStatus,
    AbortiveDrawType,
    SessionErrorCode,
    InternalMessageType,
} from "./constants";

export { decodeDraw } from "./decoders/draw";
export type { DecodedDraw } from "./decoders/draw";
export { decodeDiscard } from "./decoders/discard";
export type { DecodedDiscard } from "./decoders/discard";
export { decodeMeldCompact } from "./decoders/meld";
export type { DecodedMeld } from "./decoders/meld";

export { parseServerMessage } from "./schemas/message";
export type { GameEvent, ParsedServerMessage, ParseResult } from "./schemas/message";

export { parseSessionMessage } from "./schemas/session";
export { parseCallPrompt } from "./schemas/call-prompt";
export { parseRoundEnd } from "./schemas/round-results";

export {
    buildJoinGameMessage,
    buildReconnectMessage,
    buildPingMessage,
    buildChatMessage,
    buildDiscardAction,
    buildRiichiAction,
    buildTsumoAction,
    buildRonAction,
    buildPonAction,
    buildChiAction,
    buildKanAction,
    buildKyuushuAction,
    buildPassAction,
    buildConfirmRoundAction,
} from "./builders/client-messages";

export type {
    GameStartedEvent,
    RoundStartedEvent,
    DrawEvent,
    DiscardEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    DoraRevealedEvent,
    ErrorEvent,
    FuritenEvent,
    GameEndEvent,
    RonPromptEvent,
    ChankanPromptEvent,
    MeldPromptEvent,
    CallPromptEvent,
    TsumoRoundEnd,
    RonRoundEnd,
    DoubleRonRoundEnd,
    ExhaustiveDrawRoundEnd,
    AbortiveDrawRoundEnd,
    NagashiManganRoundEnd,
    RoundEndEvent,
    SessionErrorMessage,
    PongMessage,
    PlayerReconnectedMessage,
    SessionChatMessage,
    PlayerLeftMessage,
    GameLeftMessage,
    SessionMessage,
    GameReconnectedEvent,
} from "./types";
