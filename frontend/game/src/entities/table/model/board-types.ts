import { type DiscardTile, type HandTile, type MeldInput, type TileFace } from "@/entities/tile";

type SeatPosition = "bottom" | "right" | "top" | "left";

const SEAT_POSITIONS: SeatPosition[] = ["bottom", "right", "top", "left"];

interface BoardCenterInfo {
    roundDisplay: string;
    honbaSticks: number;
    riichiSticks: number;
    tilesRemaining: number;
    doraIndicators: TileFace[];
    scores: [BoardPlayerScore, BoardPlayerScore, BoardPlayerScore, BoardPlayerScore];
}

interface BoardPlayerScore {
    wind: string;
    score: string;
    isDealer: boolean;
    isCurrent: boolean;
    isRiichi: boolean;
}

interface BoardPlayerDisplay {
    hand: HandTile[];
    drawnTile?: HandTile;
    melds: MeldInput[];
    discards: DiscardTile[];
}

interface BoardDisplayState {
    players: [BoardPlayerDisplay, BoardPlayerDisplay, BoardPlayerDisplay, BoardPlayerDisplay];
    center: BoardCenterInfo;
}

export { SEAT_POSITIONS };
export type {
    BoardCenterInfo,
    BoardDisplayState,
    BoardPlayerDisplay,
    BoardPlayerScore,
    SeatPosition,
};
