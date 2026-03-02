import { type PlayerState, type TableState } from "./types";

export function createInitialTableState(): TableState {
    return {
        currentPlayerSeat: 0,
        dealerSeat: 0,
        doraIndicators: [],
        gameId: "",
        honbaSticks: 0,
        lastEventDescription: "",
        phase: "pre_game",
        players: [],
        riichiSticks: 0,
        roundNumber: 0,
        roundWind: 0,
    };
}

interface InitialPlayerParams {
    isAiPlayer: boolean;
    name: string;
    score: number;
    seat: number;
}

export function createInitialPlayerState(params: InitialPlayerParams): PlayerState {
    return {
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
