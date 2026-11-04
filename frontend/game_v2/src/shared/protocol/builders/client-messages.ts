import { CLIENT_MESSAGE_TYPE, GAME_ACTION, type KanType } from "@/shared/protocol/constants";
import { WIRE_KEY } from "@/shared/protocol/wire-keys";

// --- Session messages ---

export function buildJoinGameMessage(gameTicket: string) {
    return {
        [WIRE_KEY.GAME_TICKET]: gameTicket,
        [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.JOIN_GAME,
    } as const;
}

export function buildReconnectMessage(gameTicket: string) {
    return {
        [WIRE_KEY.GAME_TICKET]: gameTicket,
        [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.RECONNECT,
    } as const;
}

/**
 * Ask the server, on the socket that holds the seat, for the seat's snapshot and its pending wait again, after the
 * client lost step with the server's messages.
 */
export function buildResyncMessage() {
    return { [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.RESYNC } as const;
}

// --- Game action messages ---

export function buildDiscardAction(tileId: number, waitId: number) {
    return {
        [WIRE_KEY.ACTION]: GAME_ACTION.DISCARD,
        [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        [WIRE_KEY.TILE_ID]: tileId,
        [WIRE_KEY.WAIT_ID]: waitId,
    } as const;
}

export function buildRiichiAction(tileId: number, waitId: number) {
    return {
        [WIRE_KEY.ACTION]: GAME_ACTION.DECLARE_RIICHI,
        [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        [WIRE_KEY.TILE_ID]: tileId,
        [WIRE_KEY.WAIT_ID]: waitId,
    } as const;
}

export function buildTsumoAction(waitId: number) {
    return {
        [WIRE_KEY.ACTION]: GAME_ACTION.DECLARE_TSUMO,
        [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        [WIRE_KEY.WAIT_ID]: waitId,
    } as const;
}

export function buildRonAction(waitId: number) {
    return {
        [WIRE_KEY.ACTION]: GAME_ACTION.CALL_RON,
        [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        [WIRE_KEY.WAIT_ID]: waitId,
    } as const;
}

export function buildPonAction(tileId: number, waitId: number) {
    return {
        [WIRE_KEY.ACTION]: GAME_ACTION.CALL_PON,
        [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        [WIRE_KEY.TILE_ID]: tileId,
        [WIRE_KEY.WAIT_ID]: waitId,
    } as const;
}

export function buildChiAction(tileId: number, sequenceTiles: [number, number], waitId: number) {
    return {
        [WIRE_KEY.ACTION]: GAME_ACTION.CALL_CHI,
        [WIRE_KEY.SEQUENCE_TILES]: sequenceTiles,
        [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        [WIRE_KEY.TILE_ID]: tileId,
        [WIRE_KEY.WAIT_ID]: waitId,
    } as const;
}

export function buildKanAction(tileId: number, kanType: KanType, waitId: number) {
    return {
        [WIRE_KEY.ACTION]: GAME_ACTION.CALL_KAN,
        [WIRE_KEY.ACTION_KAN_TYPE]: kanType,
        [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        [WIRE_KEY.TILE_ID]: tileId,
        [WIRE_KEY.WAIT_ID]: waitId,
    } as const;
}

export function buildKyuushuAction(waitId: number) {
    return {
        [WIRE_KEY.ACTION]: GAME_ACTION.CALL_KYUUSHU,
        [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        [WIRE_KEY.WAIT_ID]: waitId,
    } as const;
}

export function buildPassAction(waitId: number) {
    return {
        [WIRE_KEY.ACTION]: GAME_ACTION.PASS,
        [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        [WIRE_KEY.WAIT_ID]: waitId,
    } as const;
}

export function buildConfirmRoundAction(waitId: number) {
    return {
        [WIRE_KEY.ACTION]: GAME_ACTION.CONFIRM_ROUND,
        [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        [WIRE_KEY.WAIT_ID]: waitId,
    } as const;
}

/** Every message the client sends, as the builders above construct it. */
export type ClientMessage = ReturnType<
    | typeof buildJoinGameMessage
    | typeof buildReconnectMessage
    | typeof buildResyncMessage
    | typeof buildDiscardAction
    | typeof buildRiichiAction
    | typeof buildTsumoAction
    | typeof buildRonAction
    | typeof buildPonAction
    | typeof buildChiAction
    | typeof buildKanAction
    | typeof buildKyuushuAction
    | typeof buildPassAction
    | typeof buildConfirmRoundAction
>;
