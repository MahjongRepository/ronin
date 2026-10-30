import {
    type AbortiveDrawRoundEnd,
    type AiReplacementLine,
    type DiscardEvent,
    type DoraRevealedEvent,
    type DoubleRonRoundEnd,
    type DrawEvent,
    type ExhaustiveDrawRoundEnd,
    GAME_TYPE,
    type GameEndEvent,
    type GameStartedEvent,
    MELD_TYPE,
    type MeldEvent,
    type NagashiManganRoundEnd,
    ROUND_RESULT_TYPE,
    type RiichiDeclaredEvent,
    type RonRoundEnd,
    type RoundStartedEvent,
    SEAT_CONTROL_REASON,
    type TsumoRoundEnd,
} from "@/shared/protocol";

type HandResult = TsumoRoundEnd["handResult"];

export function makeHandResult(overrides: Partial<HandResult> = {}): HandResult {
    return {
        fu: 30,
        han: 4,
        points: 7700,
        yaku: [{ han: 1, yakuId: 0 }],
        ...overrides,
    };
}

export function makeGameStartedEvent(overrides: Partial<GameStartedEvent> = {}): GameStartedEvent {
    return {
        dealerDice: [
            [2, 3],
            [4, 5],
        ],
        dealerSeat: 0,
        gameId: "test-game-1",
        gameType: GAME_TYPE.HANCHAN,
        players: [
            { aiStandIn: null, isAiPlayer: false, name: "Alice", seat: 0 },
            { aiStandIn: null, isAiPlayer: true, name: "Bot-1", seat: 1 },
            { aiStandIn: null, isAiPlayer: true, name: "Bot-2", seat: 2 },
            { aiStandIn: null, isAiPlayer: false, name: "Bob", seat: 3 },
        ],
        seat: null,
        timer: null,
        type: "game_started",
        ...overrides,
    };
}

export function makeRoundStartedEvent(
    overrides: Partial<RoundStartedEvent> = {},
): RoundStartedEvent {
    return {
        currentPlayerSeat: 0,
        dealerSeat: 0,
        dice: [3, 4],
        doraIndicators: [10],
        honbaSticks: 0,
        myTiles: null,
        players: [
            { score: 25_000, seat: 0, tiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] },
            { score: 25_000, seat: 1, tiles: [13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25] },
            { score: 25_000, seat: 2, tiles: [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38] },
            { score: 25_000, seat: 3, tiles: [39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51] },
        ],
        riichiSticks: 0,
        roundNumber: 1,
        seat: null,
        type: "round_started",
        wind: 0,
        ...overrides,
    };
}

export function makeDrawEvent(overrides: Partial<DrawEvent> = {}): DrawEvent {
    return {
        availableActions: [],
        bankSeconds: null,
        elapsedSeconds: null,
        seat: 0,
        tileId: 52,
        type: "draw",
        waitId: null,
        ...overrides,
    };
}

export function makeDiscardEvent(overrides: Partial<DiscardEvent> = {}): DiscardEvent {
    return {
        isRiichi: false,
        isTsumogiri: false,
        seat: 0,
        tileId: 52,
        type: "discard",
        ...overrides,
    };
}

export function makeMeldEvent(overrides: Partial<MeldEvent> = {}): MeldEvent {
    return {
        calledTileId: 0,
        callerSeat: 1,
        fromSeat: 0,
        meldType: MELD_TYPE.PON,
        tileIds: [1, 2, 0],
        type: "meld",
        ...overrides,
    };
}

export function makeRiichiDeclaredEvent(
    overrides: Partial<RiichiDeclaredEvent> = {},
): RiichiDeclaredEvent {
    return {
        seat: 0,
        type: "riichi_declared",
        ...overrides,
    };
}

export function makeDoraRevealedEvent(
    overrides: Partial<DoraRevealedEvent> = {},
): DoraRevealedEvent {
    return {
        tileId: 20,
        type: "dora_revealed",
        ...overrides,
    };
}

export function makeTsumoRoundEnd(overrides: Partial<TsumoRoundEnd> = {}): TsumoRoundEnd {
    return {
        closedTiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        handResult: makeHandResult(),
        melds: [],
        paoSeat: null,
        resultType: ROUND_RESULT_TYPE.TSUMO,
        riichiSticksCollected: 0,
        scoreChanges: { "0": 10_000, "1": -3000, "2": -3000, "3": -4000 },
        scores: { "0": 25_000, "1": 25_000, "2": 25_000, "3": 25_000 },
        type: "round_end",
        uraDoraIndicators: null,
        waitId: null,
        winnerSeat: 0,
        winningTile: 52,
        ...overrides,
    };
}

export function makeRonRoundEnd(overrides: Partial<RonRoundEnd> = {}): RonRoundEnd {
    return {
        closedTiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        handResult: makeHandResult({ han: 3, points: 3900 }),
        headBumpedSeats: [],
        loserSeat: 1,
        melds: [],
        paoSeat: null,
        resultType: ROUND_RESULT_TYPE.RON,
        riichiSticksCollected: 0,
        robbedKan: null,
        scoreChanges: { "0": 8000, "1": -8000, "2": 0, "3": 0 },
        scores: { "0": 25_000, "1": 25_000, "2": 25_000, "3": 25_000 },
        type: "round_end",
        uraDoraIndicators: null,
        waitId: null,
        winnerSeat: 0,
        winningTile: 52,
        ...overrides,
    };
}

type DoubleRonWinner = DoubleRonRoundEnd["winners"][number];

function makeDoubleRonWinner(overrides: Partial<DoubleRonWinner>): DoubleRonWinner {
    return {
        closedTiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        handResult: makeHandResult({ han: 3, points: 3900 }),
        melds: [],
        paoSeat: null,
        riichiSticksCollected: 0,
        scoreChanges: {},
        uraDoraIndicators: null,
        winnerSeat: 0,
        ...overrides,
    };
}

export function makeDoubleRonRoundEnd(
    overrides: Partial<DoubleRonRoundEnd> = {},
): DoubleRonRoundEnd {
    return {
        headBumpedSeats: [],
        loserSeat: 1,
        resultType: ROUND_RESULT_TYPE.DOUBLE_RON,
        robbedKan: null,
        scoreChanges: { "0": 8000, "1": -16_000, "2": 8000, "3": 0 },
        scores: { "0": 25_000, "1": 25_000, "2": 25_000, "3": 25_000 },
        type: "round_end",
        waitId: null,
        winners: [
            makeDoubleRonWinner({ scoreChanges: { "0": 8000, "1": -8000 }, winnerSeat: 0 }),
            makeDoubleRonWinner({
                closedTiles: [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38],
                scoreChanges: { "1": -8000, "2": 8000 },
                winnerSeat: 2,
            }),
        ],
        winningTile: 52,
        ...overrides,
    };
}

export function makeExhaustiveDrawRoundEnd(
    overrides: Partial<ExhaustiveDrawRoundEnd> = {},
): ExhaustiveDrawRoundEnd {
    return {
        notenSeats: [1, 3],
        resultType: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
        scoreChanges: { "0": 1500, "1": -1500, "2": 1500, "3": -1500 },
        scores: { "0": 25_000, "1": 25_000, "2": 25_000, "3": 25_000 },
        tenpaiHands: [
            { closedTiles: [0, 1, 2], melds: [], seat: 0 },
            { closedTiles: [26, 27, 28], melds: [], seat: 2 },
        ],
        tenpaiSeats: [0, 2],
        type: "round_end",
        waitId: null,
        ...overrides,
    };
}

export function makeAbortiveDrawRoundEnd(
    overrides: Partial<AbortiveDrawRoundEnd> = {},
): AbortiveDrawRoundEnd {
    return {
        reason: "four_winds",
        resultType: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
        robbedKan: null,
        ronSeats: [],
        scoreChanges: { "0": 0, "1": 0, "2": 0, "3": 0 },
        scores: { "0": 25_000, "1": 25_000, "2": 25_000, "3": 25_000 },
        seat: null,
        type: "round_end",
        waitId: null,
        ...overrides,
    };
}

export function makeNagashiManganRoundEnd(
    overrides: Partial<NagashiManganRoundEnd> = {},
): NagashiManganRoundEnd {
    return {
        notenSeats: [1, 2, 3],
        qualifyingSeats: [0],
        resultType: ROUND_RESULT_TYPE.NAGASHI_MANGAN,
        scoreChanges: { "0": 12_000, "1": -4000, "2": -4000, "3": -4000 },
        scores: { "0": 25_000, "1": 25_000, "2": 25_000, "3": 25_000 },
        tenpaiHands: [{ closedTiles: [0, 1, 2], melds: [], seat: 0 }],
        tenpaiSeats: [0],
        type: "round_end",
        waitId: null,
        ...overrides,
    };
}

export function makeGameEndEvent(overrides: Partial<GameEndEvent> = {}): GameEndEvent {
    return {
        leftoverRiichiBonus: 0,
        numRounds: 8,
        standings: [
            { finalScore: 25, score: 35_000, seat: 0 },
            { finalScore: 2, score: 22_000, seat: 1 },
            { finalScore: -8, score: 22_000, seat: 2 },
            { finalScore: -19, score: 21_000, seat: 3 },
        ],
        type: "game_end",
        winnerSeat: 0,
        ...overrides,
    };
}

export function makeAiReplacementLine(
    overrides: Partial<AiReplacementLine> = {},
): AiReplacementLine {
    return {
        reason: SEAT_CONTROL_REASON.LEFT,
        seat: 1,
        type: "ai_replacement",
        ...overrides,
    };
}
