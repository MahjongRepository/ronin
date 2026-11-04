import { EVENT_TYPE, ROUND_RESULT_TYPE, WIRE_KEY } from "@/shared/protocol";

export type WirePayload = Record<string, unknown>;

export const WIRE_DRAW: WirePayload = {
    [WIRE_KEY.BANK_SECONDS]: 20,
    [WIRE_KEY.PACKED_MOVE]: 0,
    [WIRE_KEY.EVENT_TYPE]: 1,
    [WIRE_KEY.TILES_REMAINING]: 69,
    [WIRE_KEY.WAIT_ID]: 1,
};

export const WIRE_GAME_JOINED: WirePayload = {
    [WIRE_KEY.PENDING_GAME_TIMEOUT]: 30,
    [WIRE_KEY.SESSION_TYPE]: "game_joined",
};

const WIRE_ROUND_ADVANCE_SECONDS = 15;

const WIRE_TIMER: WirePayload = {
    [WIRE_KEY.BANK_SECONDS]: 20,
    [WIRE_KEY.GAME_START_PAUSE]: 3,
    [WIRE_KEY.MAX_BANK_SECONDS]: 20,
    [WIRE_KEY.ROUND_ADVANCE_TIMEOUT]: WIRE_ROUND_ADVANCE_SECONDS,
    [WIRE_KEY.BASE_TURN_SECONDS]: 5,
};

export const WIRE_GAME_STARTED: WirePayload = {
    [WIRE_KEY.DEALER_DICE]: [
        [1, 1],
        [1, 1],
    ],
    [WIRE_KEY.DEALER]: 0,
    [WIRE_KEY.GAME_ID]: "g1",
    [WIRE_KEY.GAME_TYPE]: 0,
    [WIRE_KEY.PLAYERS]: [
        { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "P0", [WIRE_KEY.SEAT]: 0 },
        { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "P1", [WIRE_KEY.SEAT]: 1 },
        { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "P2", [WIRE_KEY.SEAT]: 2 },
        { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "P3", [WIRE_KEY.SEAT]: 3 },
    ],
    [WIRE_KEY.RIICHI_STICK_VALUE]: 10,
    [WIRE_KEY.SEAT]: 0,
    [WIRE_KEY.EVENT_TYPE]: 8,
    [WIRE_KEY.TIMER_SETTINGS]: WIRE_TIMER,
};

/**
 * A replay game start with its compact rules reference and independent viewing fields.
 */
export const REPLAY_GAME_STARTED: WirePayload = {
    [WIRE_KEY.HAS_AKADORA]: true,
    [WIRE_KEY.DEALER_DICE]: [
        [1, 1],
        [1, 1],
    ],
    [WIRE_KEY.DEALER]: 0,
    [WIRE_KEY.GAME_ID]: "g1",
    [WIRE_KEY.GAME_SETTINGS]: { id: 1, overrides: {} },
    [WIRE_KEY.GAME_TYPE]: 0,
    [WIRE_KEY.PLAYERS]: [
        { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "P0", [WIRE_KEY.SEAT]: 0 },
        { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "P1", [WIRE_KEY.SEAT]: 1 },
        { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "P2", [WIRE_KEY.SEAT]: 2 },
        { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "P3", [WIRE_KEY.SEAT]: 3 },
    ],
    [WIRE_KEY.RIICHI_STICK_VALUE]: 10,
    [WIRE_KEY.RNG_VERSION]: "1",
    [WIRE_KEY.SEED]: "00".repeat(96),
    [WIRE_KEY.EVENT_TYPE]: 8,
};

/** A finished round of a snapshot's history: an exhaustive draw with East 1's dealer. */
export const WIRE_ROUND_RECORD: WirePayload = {
    [WIRE_KEY.DEALER]: 0,
    [WIRE_KEY.HONBA]: 0,
    [WIRE_KEY.PAO_SEAT]: [],
    [WIRE_KEY.RIICHI_SEATS]: [],
    [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
    [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
    [WIRE_KEY.TENPAI_SEATS]: [],
    [WIRE_KEY.WIND]: 0,
    [WIRE_KEY.WINNER_SEAT]: [],
};

function wireSeatState(seat: number): WirePayload {
    return {
        [WIRE_KEY.DISCARDS]: [],
        [WIRE_KEY.MELDS]: [],
        [WIRE_KEY.IS_RIICHI]: false,
        [WIRE_KEY.SEAT]: seat,
        [WIRE_KEY.SCORE]: 250,
        [WIRE_KEY.TILE_COUNT]: 13,
    };
}

/** A complete snapshot of the game's second deal in play: every seat's player and state, the first deal's record. */
export const WIRE_GAME_RECONNECTED: WirePayload = {
    [WIRE_KEY.CURRENT_PLAYER]: 0,
    [WIRE_KEY.DICE]: [1, 2],
    [WIRE_KEY.DEALER_DICE]: [
        [1, 2],
        [3, 4],
    ],
    [WIRE_KEY.DORA_INDICATORS]: [0],
    [WIRE_KEY.DEALER]: 0,
    [WIRE_KEY.FURITEN]: false,
    [WIRE_KEY.FIRST_DEALER]: 0,
    [WIRE_KEY.GAME_ID]: "g1",
    [WIRE_KEY.HONBA]: 0,
    [WIRE_KEY.MY_TILES]: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
    [WIRE_KEY.ROUND_NUMBER]: 1,
    [WIRE_KEY.PLAYERS]: [
        { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "P1", [WIRE_KEY.SEAT]: 0 },
        { [WIRE_KEY.AI_PLAYER]: 0, [WIRE_KEY.NAME]: "P2", [WIRE_KEY.SEAT]: 1 },
        { [WIRE_KEY.AI_PLAYER]: 1, [WIRE_KEY.NAME]: "B1", [WIRE_KEY.SEAT]: 2 },
        { [WIRE_KEY.AI_PLAYER]: 1, [WIRE_KEY.NAME]: "B2", [WIRE_KEY.SEAT]: 3 },
    ],
    [WIRE_KEY.PLAYER_STATES]: [0, 1, 2, 3].map(wireSeatState),
    [WIRE_KEY.RIICHI_STICKS]: 0,
    [WIRE_KEY.ROUND_HISTORY]: [WIRE_ROUND_RECORD],
    [WIRE_KEY.RIICHI_STICK_VALUE]: 10,
    [WIRE_KEY.ROUND_IN_WIND]: 2,
    [WIRE_KEY.SEAT]: 0,
    [WIRE_KEY.TIMER_SETTINGS]: WIRE_TIMER,
    [WIRE_KEY.TILES_REMAINING]: 70,
    [WIRE_KEY.SESSION_TYPE]: "game_reconnected",
    [WIRE_KEY.WIND]: 0,
    [WIRE_KEY.WAIT_ID]: 7,
};

/** Thirteen tile ids from `first` on, a dealt hand. */
function dealtTiles(first: number): number[] {
    return Array.from({ length: 13 }, (_unused, index) => first + index);
}

/** A live deal to seat 0: every seat's score, its own hand alone. */
export const WIRE_ROUND_STARTED: WirePayload = {
    [WIRE_KEY.CURRENT_PLAYER]: 0,
    [WIRE_KEY.DORA_INDICATORS]: [0],
    [WIRE_KEY.DEALER]: 0,
    [WIRE_KEY.HONBA]: 0,
    [WIRE_KEY.MY_TILES]: dealtTiles(4),
    [WIRE_KEY.ROUND_NUMBER]: 1,
    [WIRE_KEY.PLAYERS]: [
        { [WIRE_KEY.SEAT]: 0, [WIRE_KEY.SCORE]: 250 },
        { [WIRE_KEY.SEAT]: 1, [WIRE_KEY.SCORE]: 250 },
        { [WIRE_KEY.SEAT]: 2, [WIRE_KEY.SCORE]: 250 },
        { [WIRE_KEY.SEAT]: 3, [WIRE_KEY.SCORE]: 250 },
    ],
    [WIRE_KEY.RIICHI_STICKS]: 0,
    [WIRE_KEY.ROUND_IN_WIND]: 1,
    [WIRE_KEY.SEAT]: 0,
    [WIRE_KEY.EVENT_TYPE]: 9,
    [WIRE_KEY.TILES_REMAINING]: 70,
    [WIRE_KEY.WIND]: 0,
};

/** A replay file's deal: every seat's hand, and no viewer. */
export const REPLAY_ROUND_STARTED: WirePayload = {
    [WIRE_KEY.CURRENT_PLAYER]: 0,
    [WIRE_KEY.DORA_INDICATORS]: [0],
    [WIRE_KEY.DEALER]: 0,
    [WIRE_KEY.HONBA]: 0,
    [WIRE_KEY.ROUND_NUMBER]: 1,
    [WIRE_KEY.PLAYERS]: [0, 1, 2, 3].map((seat) => ({
        [WIRE_KEY.SEAT]: seat,
        [WIRE_KEY.SCORE]: 250,
        [WIRE_KEY.TILES]: dealtTiles(4 + seat * 13),
    })),
    [WIRE_KEY.RIICHI_STICKS]: 0,
    [WIRE_KEY.ROUND_IN_WIND]: 1,
    [WIRE_KEY.EVENT_TYPE]: 9,
    [WIRE_KEY.TILES_REMAINING]: 70,
    [WIRE_KEY.WIND]: 0,
};

export const WIRE_GAME_END: WirePayload = {
    [WIRE_KEY.END_CAUSE]: "length",
    [WIRE_KEY.LEFTOVER_BONUS]: 0,
    [WIRE_KEY.LEFTOVER_RIICHI]: 0,
    [WIRE_KEY.ROUND_COUNT]: 1,
    [WIRE_KEY.STANDINGS]: [0, 1, 2, 3].map((seat) => ({
        [WIRE_KEY.FINAL_SCORE]: 0,
        [WIRE_KEY.SEAT]: seat,
        [WIRE_KEY.SCORE]: 250,
    })),
    [WIRE_KEY.EVENT_TYPE]: 10,
    [WIRE_KEY.WINNER_SEAT]: 0,
};

/**
 * A tsumo round end; a wait id opens the round advance, with its timeout (one result's `ra` unless given), and the
 * game's last round end carries neither.
 */
export function wireRoundEnd(
    waitId: number | null,
    advanceSeconds: number = WIRE_ROUND_ADVANCE_SECONDS,
): WirePayload {
    const roundEnd: WirePayload = {
        [WIRE_KEY.CLOSED_TILES]: [0, 4, 8],
        [WIRE_KEY.DORA_INDICATORS]: [40],
        [WIRE_KEY.DEALER]: 0,
        [WIRE_KEY.HONBA_BONUS]: 0,
        [WIRE_KEY.HAND_RESULT]: {
            [WIRE_KEY.FU]: 30,
            [WIRE_KEY.HAN]: 3,
            [WIRE_KEY.HAND_LIMIT]: "none",
            [WIRE_KEY.POINTS]: 39,
            [WIRE_KEY.YAKU]: [
                { [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_ID]: 0, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
            ],
        },
        [WIRE_KEY.MELDS]: [],
        [WIRE_KEY.RIICHI_STICKS]: 0,
        [WIRE_KEY.RIICHI_COLLECTED]: 0,
        [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.TSUMO,
        [WIRE_KEY.SCORE_CHANGES]: { "0": 30, "1": -10, "2": -10, "3": -10 },
        [WIRE_KEY.SCORES]: { "0": 280, "1": 240, "2": 240, "3": 240 },
        [WIRE_KEY.EVENT_TYPE]: 4,
        [WIRE_KEY.WINNER_SEAT]: 0,
        [WIRE_KEY.WINNING_TILE]: 12,
    };
    return waitId === null
        ? roundEnd
        : {
              ...roundEnd,
              [WIRE_KEY.ROUND_ADVANCE_SECONDS]: advanceSeconds,
              [WIRE_KEY.WAIT_ID]: waitId,
          };
}

/**
 * The snapshot during the second deal's round advance (its result `wireRoundEnd`'s, its history both deals'), the
 * seat's confirm owed or not, on the advance's wait.
 */
export function wireRoundAdvanceSnapshot(owed: boolean, waitId: number): WirePayload {
    return {
        ...WIRE_GAME_RECONNECTED,
        [WIRE_KEY.CONFIRMATION_OWED]: owed,
        [WIRE_KEY.ROUND_RESULT]: wireRoundEnd(null),
        [WIRE_KEY.ROUND_HISTORY]: [WIRE_ROUND_RECORD, WIRE_ROUND_RECORD],
        [WIRE_KEY.WAIT_ID]: waitId,
    };
}

/** A session error; a rate limit names the wait id of the action it refused when that action had one. */
export function wireSessionError(code: string, waitId: number | null = null): WirePayload {
    const error: WirePayload = {
        [WIRE_KEY.SESSION_ERROR_CODE]: code,
        [WIRE_KEY.SESSION_ERROR_MESSAGE]: `server said ${code}`,
        [WIRE_KEY.SESSION_TYPE]: "session_error",
    };
    return waitId === null ? error : { ...error, [WIRE_KEY.WAIT_ID]: waitId };
}

/**
 * A game error refusing the seat's action, `code` one of the server's game error codes (`GameErrorCode`), named by the
 * wait id that action echoed.
 */
export function wireGameError(code: string, waitId: number): WirePayload {
    return {
        [WIRE_KEY.GAME_ERROR_CODE]: code,
        [WIRE_KEY.GAME_ERROR_MESSAGE]: `server said ${code}`,
        [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ERROR,
        [WIRE_KEY.WAIT_ID]: waitId,
    };
}

/** The engine's refusal of a call on a rule judgment, a refusal that is not stale, of the action on `waitId`. */
export function wireRuleRefusal(waitId: number): WirePayload {
    return wireGameError("invalid_pon", waitId);
}

/** The notice the server broadcasts when an AI player takes another player's seat after its socket left. */
export const WIRE_SEAT_TO_AI: WirePayload = {
    [WIRE_KEY.SEAT_CONTROL_REASON]: 0,
    [WIRE_KEY.SEAT]: 3,
    [WIRE_KEY.SESSION_TYPE]: "seat_control",
};

function isWirePayload(value: unknown): value is WirePayload {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** A payload's field holding an object (a snapshot's pending result); throws otherwise. */
export function wirePayloadOf(payload: WirePayload, key: number): WirePayload {
    const value: unknown = payload[key];
    if (!isWirePayload(value)) {
        throw new Error(`${key} is not an object`);
    }
    return value;
}

/** A payload's field holding a list of numbers (a snapshot's own tiles); throws otherwise. */
export function wireNumberList(payload: WirePayload, key: number): readonly number[] {
    const value: unknown = payload[key];
    if (!Array.isArray(value) || !value.every((item) => typeof item === "number")) {
        throw new Error(`${key} is not a list of numbers`);
    }
    return value;
}

/** A payload's field holding a list of objects (a snapshot's seat states, a round end's winners); throws otherwise. */
export function wirePayloadList(payload: WirePayload, key: number): readonly WirePayload[] {
    const value: unknown = payload[key];
    if (!Array.isArray(value) || !value.every(isWirePayload)) {
        throw new Error(`${key} is not a list of objects`);
    }
    return value;
}
