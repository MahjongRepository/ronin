import { type DiscardTile, type HandTile, type MeldInput, type TileFace } from "@/entities/tile";

type SeatPosition = "bottom" | "right" | "top" | "left";

const SEAT_POSITIONS: SeatPosition[] = ["bottom", "right", "top", "left"];

interface BoardCenterInfo {
    readonly roundDisplay: string;
    readonly honbaSticks: number;
    readonly riichiSticks: number;
    readonly tilesRemaining: number;
    readonly doraIndicators: readonly TileFace[];
    readonly scores: readonly [
        BoardPlayerScore,
        BoardPlayerScore,
        BoardPlayerScore,
        BoardPlayerScore,
    ];
}

interface BoardPlayerScore {
    readonly wind: string;
    readonly score: string;
    readonly isDealer: boolean;
    readonly isCurrent: boolean;
    readonly isRiichi: boolean;
}

interface BoardPlayerDisplay {
    readonly hand: readonly HandTile[];
    readonly drawnTile?: HandTile;
    readonly melds: readonly MeldInput[];
    readonly discards: readonly DiscardTile[];
}

interface BoardDisplayState {
    readonly players: readonly [
        BoardPlayerDisplay,
        BoardPlayerDisplay,
        BoardPlayerDisplay,
        BoardPlayerDisplay,
    ];
    readonly center: BoardCenterInfo;
}

/**
 * How a board is seen: which seat sits at the bottom, whoever deals, and whose known tiles show face up. A replay
 * may show every hand it knows (`all`); a seat sees only its own (`bottom`). Concealed tiles are backs either way.
 */
interface BoardPerspective {
    readonly bottomSeat: number;
    readonly reveal: "all" | "bottom";
}

export { SEAT_POSITIONS };
export type {
    BoardCenterInfo,
    BoardPerspective,
    BoardDisplayState,
    BoardPlayerDisplay,
    BoardPlayerScore,
    SeatPosition,
};
