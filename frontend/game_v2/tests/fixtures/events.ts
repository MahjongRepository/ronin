import {
    CALL_TYPE,
    type ChankanPromptEvent,
    type ClaimedMeldEvent,
    type DiscardEvent,
    type DoraRevealedEvent,
    type DrawNoticeEvent,
    type ExhaustiveDrawRoundEnd,
    GAME_END_CAUSE,
    GAME_TYPE,
    type GameEndEvent,
    type GameStartedEvent,
    HAND_LIMIT,
    type LiveDrawEvent,
    MELD_TYPE,
    type MeldEvent,
    type NagashiManganRoundEnd,
    ROUND_RESULT_TYPE,
    type RecordedDrawEvent,
    type RiichiDeclaredEvent,
    type RoundStartedEvent,
    SEAT_CONTROL_REASON,
} from "@/shared/protocol";
import { type AiReplacementLine } from "@/shared/protocol/schemas/replay";
import {
    type AbortiveDrawRoundEnd,
    type DoubleRonRoundEnd,
    type RonRoundEnd,
    type TsumoRoundEnd,
} from "@/shared/protocol/types";

type HandResult = TsumoRoundEnd["handResult"];

export function makeHandResult(overrides: Partial<HandResult> = {}): HandResult {
    return {
        fu: 30,
        han: 4,
        limit: HAND_LIMIT.NONE,
        points: 7700,
        yaku: [{ han: 1, yakuId: 0, yakumanCount: 0 }],
        yakumanCount: null,
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
        hasAkadora: true,
        players: [
            { aiStandIn: null, isAiPlayer: false, name: "Alice", seat: 0 },
            { aiStandIn: null, isAiPlayer: true, name: "Bot-1", seat: 1 },
            { aiStandIn: null, isAiPlayer: true, name: "Bot-2", seat: 2 },
            { aiStandIn: null, isAiPlayer: false, name: "Bob", seat: 3 },
        ],
        riichiStickValue: 1000,
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
        roundInWind: 1,
        roundNumber: 1,
        seat: null,
        tilesRemaining: 70,
        type: "round_started",
        wind: 0,
        ...overrides,
    };
}

export function makeDrawEvent(overrides: Partial<RecordedDrawEvent> = {}): RecordedDrawEvent {
    return {
        availableActions: [],
        bankSeconds: null,
        elapsedSeconds: null,
        seat: 0,
        source: "replay",
        tileId: 52,
        tilesRemaining: 69,
        type: "draw",
        waitId: null,
        ...overrides,
    };
}

export function makeLiveDrawEvent(overrides: Partial<LiveDrawEvent> = {}): LiveDrawEvent {
    const { tilesRemaining: _tilesRemaining, ...draw } = makeDrawEvent();
    return { ...draw, source: "live", ...overrides };
}

export function makeDrawNoticeEvent(seat: number): DrawNoticeEvent {
    return { seat, type: "draw_notice" };
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

type CalledMeldEvent = Exclude<ClaimedMeldEvent, { meldType: "added_kan" }>;
type AddedKanEvent = Extract<MeldEvent, { meldType: "added_kan" }>;

export function makeMeldEvent(overrides: Partial<CalledMeldEvent> = {}): CalledMeldEvent {
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

export function makeAddedKanEvent(
    overrides: Partial<Omit<AddedKanEvent, "meldType" | "type">> = {},
): AddedKanEvent {
    return {
        addedTileId: 3,
        calledTileId: 0,
        callerSeat: 1,
        fromSeat: 0,
        meldType: MELD_TYPE.ADDED_KAN,
        tileIds: [0, 1, 2, 3],
        type: "meld",
        ...overrides,
    };
}

export function makeClosedKanEvent(
    overrides: Partial<Pick<MeldEvent, "callerSeat" | "tileIds">> = {},
): MeldEvent {
    return {
        calledTileId: null,
        callerSeat: 1,
        fromSeat: null,
        meldType: MELD_TYPE.CLOSED_KAN,
        tileIds: [0, 1, 2, 3],
        type: "meld",
        ...overrides,
    };
}

export function makeChankanPromptEvent(
    overrides: Partial<ChankanPromptEvent> = {},
): ChankanPromptEvent {
    return {
        bankSeconds: null,
        callType: CALL_TYPE.CHANKAN,
        callerSeat: 1,
        elapsedSeconds: null,
        fromSeat: 0,
        kanType: "added",
        tileId: 39,
        type: "call_prompt",
        waitId: null,
        ...overrides,
    };
}

export function makeRiichiDeclaredEvent(
    overrides: Partial<RiichiDeclaredEvent> = {},
): RiichiDeclaredEvent {
    return {
        riichiSticks: 1,
        score: 24_000,
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
        dealerSeat: 0,
        doraIndicators: [40],
        handResult: makeHandResult(),
        honbaBonus: 0,
        melds: [],
        pao: null,
        resultType: ROUND_RESULT_TYPE.TSUMO,
        riichiSticks: 0,
        riichiSticksCollected: 0,
        roundAdvance: null,
        scoreChanges: { "0": 10_000, "1": -3000, "2": -3000, "3": -4000 },
        scores: { "0": 25_000, "1": 25_000, "2": 25_000, "3": 25_000 },
        type: "round_end",
        uraDoraIndicators: null,
        winnerSeat: 0,
        winningTile: 52,
        ...overrides,
    };
}

export function makeRonRoundEnd(overrides: Partial<RonRoundEnd> = {}): RonRoundEnd {
    return {
        closedTiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        dealerSeat: 0,
        doraIndicators: [40],
        handResult: makeHandResult({ han: 3, points: 3900 }),
        headBumpedSeats: [],
        honbaBonus: 0,
        loserSeat: 1,
        melds: [],
        pao: null,
        resultType: ROUND_RESULT_TYPE.RON,
        riichiSticks: 0,
        riichiSticksCollected: 0,
        robbedKan: null,
        roundAdvance: null,
        scoreChanges: { "0": 8000, "1": -8000, "2": 0, "3": 0 },
        scores: { "0": 25_000, "1": 25_000, "2": 25_000, "3": 25_000 },
        type: "round_end",
        uraDoraIndicators: null,
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
        honbaBonus: 0,
        melds: [],
        pao: null,
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
        dealerSeat: 0,
        doraIndicators: [40],
        headBumpedSeats: [],
        loserSeat: 1,
        resultType: ROUND_RESULT_TYPE.DOUBLE_RON,
        riichiSticks: 0,
        robbedKan: null,
        roundAdvance: null,
        scoreChanges: { "0": 8000, "1": -16_000, "2": 8000, "3": 0 },
        scores: { "0": 25_000, "1": 25_000, "2": 25_000, "3": 25_000 },
        type: "round_end",
        winners: [
            makeDoubleRonWinner({
                scoreChanges: { "0": 8000, "1": -8000, "2": 0, "3": 0 },
                winnerSeat: 0,
            }),
            makeDoubleRonWinner({
                closedTiles: [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38],
                scoreChanges: { "0": 0, "1": -8000, "2": 8000, "3": 0 },
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
        dealerSeat: 0,
        doraIndicators: [40],
        notenSeats: [1, 3],
        resultType: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
        riichiSticks: 0,
        roundAdvance: null,
        scoreChanges: { "0": 1500, "1": -1500, "2": 1500, "3": -1500 },
        scores: { "0": 25_000, "1": 25_000, "2": 25_000, "3": 25_000 },
        tenpaiHands: [
            { closedTiles: [0, 1, 2], melds: [], seat: 0 },
            { closedTiles: [26, 27, 28], melds: [], seat: 2 },
        ],
        tenpaiSeats: [0, 2],
        type: "round_end",
        ...overrides,
    };
}

export function makeAbortiveDrawRoundEnd(
    overrides: Partial<AbortiveDrawRoundEnd> = {},
): AbortiveDrawRoundEnd {
    return {
        dealerSeat: 0,
        doraIndicators: [40],
        reason: "four_winds",
        resultType: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
        riichiSticks: 0,
        robbedKan: null,
        ronSeats: [],
        roundAdvance: null,
        scoreChanges: { "0": 0, "1": 0, "2": 0, "3": 0 },
        scores: { "0": 25_000, "1": 25_000, "2": 25_000, "3": 25_000 },
        seat: null,
        type: "round_end",
        ...overrides,
    };
}

export function makeNagashiManganRoundEnd(
    overrides: Partial<NagashiManganRoundEnd> = {},
): NagashiManganRoundEnd {
    return {
        dealerSeat: 0,
        doraIndicators: [40],
        notenSeats: [1, 2, 3],
        qualifyingRivers: [
            {
                discards: [
                    { isRiichiDiscard: false, isTsumogiri: false, tileId: 0 },
                    { isRiichiDiscard: false, isTsumogiri: true, tileId: 132 },
                ],
                seat: 0,
            },
        ],
        qualifyingSeats: [0],
        resultType: ROUND_RESULT_TYPE.NAGASHI_MANGAN,
        riichiSticks: 0,
        roundAdvance: null,
        scoreChanges: { "0": 12_000, "1": -4000, "2": -4000, "3": -4000 },
        scores: { "0": 25_000, "1": 25_000, "2": 25_000, "3": 25_000 },
        tenpaiHands: [{ closedTiles: [0, 1, 2], melds: [], seat: 0 }],
        tenpaiSeats: [0],
        type: "round_end",
        ...overrides,
    };
}

export function makeGameEndEvent(overrides: Partial<GameEndEvent> = {}): GameEndEvent {
    return {
        endCause: GAME_END_CAUSE.LENGTH,
        leftoverRiichiBonus: 0,
        leftoverRiichiSticks: 0,
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
