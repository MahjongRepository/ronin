// Type-safe factory functions for constructing client-to-server messages.
// Each function returns a correctly shaped object ready for MessagePack encoding.

import { CLIENT_MESSAGE_TYPE, GAME_ACTION, type KanType } from "@/shared/protocol/constants";

// --- Session messages ---

export function buildJoinGameMessage(gameTicket: string) {
    return { game_ticket: gameTicket, t: CLIENT_MESSAGE_TYPE.JOIN_GAME } as const;
}

export function buildReconnectMessage(gameTicket: string) {
    return {
        game_ticket: gameTicket,
        t: CLIENT_MESSAGE_TYPE.RECONNECT,
    } as const;
}

export function buildPingMessage() {
    return { t: CLIENT_MESSAGE_TYPE.PING } as const;
}

export function buildChatMessage(text: string) {
    return { t: CLIENT_MESSAGE_TYPE.CHAT, text } as const;
}

// --- Game action messages ---

export function buildDiscardAction(tileId: number) {
    return {
        a: GAME_ACTION.DISCARD,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        ti: tileId,
    } as const;
}

export function buildRiichiAction(tileId: number) {
    return {
        a: GAME_ACTION.DECLARE_RIICHI,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        ti: tileId,
    } as const;
}

export function buildTsumoAction() {
    return {
        a: GAME_ACTION.DECLARE_TSUMO,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
    } as const;
}

export function buildRonAction() {
    return {
        a: GAME_ACTION.CALL_RON,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
    } as const;
}

export function buildPonAction(tileId: number) {
    return {
        a: GAME_ACTION.CALL_PON,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        ti: tileId,
    } as const;
}

export function buildChiAction(tileId: number, sequenceTiles: [number, number]) {
    return {
        a: GAME_ACTION.CALL_CHI,
        sequence_tiles: sequenceTiles,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        ti: tileId,
    } as const;
}

export function buildKanAction(tileId: number, kanType: KanType) {
    return {
        a: GAME_ACTION.CALL_KAN,
        kan_type: kanType,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        ti: tileId,
    } as const;
}

export function buildKyuushuAction() {
    return {
        a: GAME_ACTION.CALL_KYUUSHU,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
    } as const;
}

export function buildPassAction() {
    return {
        a: GAME_ACTION.PASS,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
    } as const;
}

export function buildConfirmRoundAction() {
    return {
        a: GAME_ACTION.CONFIRM_ROUND,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
    } as const;
}
