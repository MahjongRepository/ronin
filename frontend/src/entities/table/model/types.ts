import {
    type DecodedMeld,
    type DiscardEvent,
    type DoraRevealedEvent,
    type DrawEvent,
    type GameEndEvent,
    type GameStartedEvent,
    type MeldEvent,
    type RiichiDeclaredEvent,
    type RoundEndEvent,
    type RoundStartedEvent,
} from "@/shared/protocol";

export interface DiscardRecord {
    tileId: number;
    isTsumogiri: boolean;
    isRiichi: boolean;
    claimed?: boolean;
}

export interface MeldRecord extends DecodedMeld {
    /** For added_kan only: the tile added from hand to upgrade the pon. */
    addedTileId?: number;
}

export interface PlayerState {
    seat: number;
    name: string;
    isAiPlayer: boolean;
    score: number;
    tiles: number[];
    drawnTileId: number | null;
    discards: DiscardRecord[];
    melds: MeldRecord[];
    isRiichi: boolean;
}

export type GamePhase = "pre_game" | "in_round" | "round_ended" | "game_ended";

export interface TableState {
    gameId: string;
    players: PlayerState[];
    dealerSeat: number;
    roundWind: number;
    roundNumber: number;
    honbaSticks: number;
    riichiSticks: number;
    doraIndicators: number[];
    currentPlayerSeat: number;
    phase: GamePhase;
    lastEventDescription: string;
}

export type ReplayEvent =
    | GameStartedEvent
    | RoundStartedEvent
    | DrawEvent
    | DiscardEvent
    | MeldEvent
    | RiichiDeclaredEvent
    | DoraRevealedEvent
    | RoundEndEvent
    | GameEndEvent;
