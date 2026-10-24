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

export function buildChatMessage(text: string) {
    return { t: CLIENT_MESSAGE_TYPE.CHAT, text } as const;
}

// --- Game action messages ---

export function buildDiscardAction(tileId: number, waitId: number) {
    return {
        a: GAME_ACTION.DISCARD,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        ti: tileId,
        wi: waitId,
    } as const;
}

export function buildRiichiAction(tileId: number, waitId: number) {
    return {
        a: GAME_ACTION.DECLARE_RIICHI,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        ti: tileId,
        wi: waitId,
    } as const;
}

export function buildTsumoAction(waitId: number) {
    return {
        a: GAME_ACTION.DECLARE_TSUMO,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        wi: waitId,
    } as const;
}

export function buildRonAction(waitId: number) {
    return {
        a: GAME_ACTION.CALL_RON,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        wi: waitId,
    } as const;
}

export function buildPonAction(tileId: number, waitId: number) {
    return {
        a: GAME_ACTION.CALL_PON,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        ti: tileId,
        wi: waitId,
    } as const;
}

export function buildChiAction(tileId: number, sequenceTiles: [number, number], waitId: number) {
    return {
        a: GAME_ACTION.CALL_CHI,
        sequence_tiles: sequenceTiles,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        ti: tileId,
        wi: waitId,
    } as const;
}

export function buildKanAction(tileId: number, kanType: KanType, waitId: number) {
    return {
        a: GAME_ACTION.CALL_KAN,
        kan_type: kanType,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        ti: tileId,
        wi: waitId,
    } as const;
}

export function buildKyuushuAction(waitId: number) {
    return {
        a: GAME_ACTION.CALL_KYUUSHU,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        wi: waitId,
    } as const;
}

export function buildPassAction(waitId: number) {
    return {
        a: GAME_ACTION.PASS,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        wi: waitId,
    } as const;
}

export function buildConfirmRoundAction(waitId: number) {
    return {
        a: GAME_ACTION.CONFIRM_ROUND,
        t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
        wi: waitId,
    } as const;
}
