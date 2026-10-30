import { type PlayerState, type TableState } from "./types";

export function createInitialTableState(): TableState {
    return {
        currentPlayerSeat: 0,
        dealerSeat: 0,
        doraIndicators: [],
        firstDealerSeat: 0,
        gameEndResult: null,
        gameId: "",
        gameType: null,
        honbaSticks: 0,
        lastDiscardSeat: null,
        phase: "pre_game",
        players: [],
        revealedSeats: [],
        riichiSticks: 0,
        roundEndResult: null,
        roundHistory: [],
        roundNumber: 0,
        roundWind: 0,
        tilesRemaining: 0,
    };
}

interface InitialPlayerParams {
    readonly isAiPlayer: boolean;
    readonly name: string;
    readonly score: number;
    readonly seat: number;
}

export function createInitialPlayerState(params: InitialPlayerParams): PlayerState {
    return {
        aiStandIn: null,
        concealedCount: 0,
        discards: [],
        drawnTileId: null,
        isAiPlayer: params.isAiPlayer,
        isRiichi: false,
        melds: [],
        name: params.name,
        score: params.score,
        seat: params.seat,
        tiles: [],
    };
}
