import { type DiscardTile, type HandTile, type MeldTile, type TileFace } from "@/entities/tile";

type SeatPosition = "bottom" | "right" | "top" | "left";

const SEAT_POSITIONS: SeatPosition[] = ["bottom", "right", "top", "left"];

interface BoardCenterInfo {
    readonly roundDisplay: string;
    readonly honbaSticks: number;
    readonly riichiSticks: number;
    readonly tilesRemaining: number;
    readonly doraIndicators: readonly TileFace[];
}

/**
 * An AI player marked on a seat: the plate's short tag, `AI` for one playing the seat as far as the source says or
 * `Away` for one holding it while its human is out (left, or never came), and the words for why.
 */
interface NameplateAiMark {
    readonly kind: "ai" | "away";
    readonly tag: string;
    readonly words: string;
}

/**
 * A seat's nameplate: who plays it, its seat wind and score, and its marks. `scoreDiffs` gives, by board position, how
 * far this seat's score is from that seat's, signed (`+1000`, `-3000`, `0`): what the plate shows while that seat's
 * plate is hovered; its own position's is empty.
 */
interface BoardNameplate {
    readonly name: string;
    /** The seat wind's letter (`E`) and name (`East`). */
    readonly wind: string;
    readonly windName: string;
    readonly score: string;
    readonly scoreDiffs: Readonly<Record<SeatPosition, string>>;
    readonly isDealer: boolean;
    /** Whose turn it is, while a round plays. */
    readonly isCurrent: boolean;
    /** The seat declared riichi and its stick is down. */
    readonly isRiichi: boolean;
    /** The AI player marked on the seat; null when none is known to play it. */
    readonly aiMark: NameplateAiMark | null;
}

/** A call a seat makes aloud, which the board shows by its seat for a moment. */
type CalloutKind = "ron" | "tsumo" | "pon" | "chi" | "kan" | "riichi";

/** A call shown on the board: its kind, its word and the position of the seat that made it. */
interface BoardCallout {
    readonly kind: CalloutKind;
    readonly label: string;
    readonly position: SeatPosition;
}

/**
 * The calls a board shows at once, made by one move: the key that tells this showing from the next, so a new one plays
 * its animation afresh while a redraw of the same one does not, and whether the board reads the showing out (a
 * replay's jump shows its calls silently).
 */
interface BoardCallouts {
    readonly key: string;
    readonly items: readonly BoardCallout[];
    readonly announced: boolean;
}

interface BoardPlayerDisplay {
    readonly hand: readonly HandTile[];
    readonly drawnTile?: HandTile;
    /** Each meld laid out, oldest first. */
    readonly melds: readonly (readonly MeldTile[])[];
    readonly discards: readonly DiscardTile[];
    /** The meld an offer refers to (the kan a chankan offer may rob), by its index in `melds`; none for any other. */
    readonly sourceMeld?: number;
}

interface BoardDisplayState {
    readonly motionContext?: string;
    readonly motionRound?: number;
    readonly players: readonly [
        BoardPlayerDisplay,
        BoardPlayerDisplay,
        BoardPlayerDisplay,
        BoardPlayerDisplay,
    ];
    readonly center: BoardCenterInfo;
    /** Each seat's nameplate, by board position like `players`. */
    readonly nameplates: readonly [BoardNameplate, BoardNameplate, BoardNameplate, BoardNameplate];
}

interface BoardMotionCue {
    readonly sequence: number;
    readonly mode: "step" | "replay" | "reset";
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
    BoardCallout,
    BoardCallouts,
    BoardCenterInfo,
    CalloutKind,
    BoardPerspective,
    BoardDisplayState,
    BoardMotionCue,
    BoardNameplate,
    BoardPlayerDisplay,
    NameplateAiMark,
    SeatPosition,
};
