import {
    type DiscardEvent,
    type DoraRevealedEvent,
    type DrawEvent,
    type GameEndEvent,
    type GameReconnectedEvent,
    type GameStartedEvent,
    type KanType,
    type MeldEvent,
    type MeldType,
    type PlayerLeftMessage,
    type PlayerReconnectedMessage,
    type RiichiDeclaredEvent,
    type RoundEndEvent,
    type RoundStartedEvent,
    type SeatControlLine,
    type SeatControlReason,
} from "@/shared/protocol";

export interface DiscardRecord {
    readonly tileId: number;
    readonly isTsumogiri: boolean;
    readonly isRiichi: boolean;
    readonly claimed?: boolean;
}

export interface MeldRecord {
    readonly calledTileId: number | null;
    readonly callerSeat: number;
    readonly fromSeat: number | null;
    readonly meldType: MeldType;
    readonly tileIds: readonly number[];
    /** For added_kan only: the tile added from hand to upgrade the pon. */
    readonly addedTileId?: number;
}

/**
 * A seat as this view knows it. Its closed hand is `tiles`, the tile ids the source showed it, plus
 * `concealedCount` tiles it holds face down: a live seat sees only its own tiles, so every other hand is a count,
 * and their draws reach it only as the discard or kan that follows them. A replay shows every hand, so its counts
 * stay 0.
 */
export interface PlayerState {
    readonly seat: number;
    readonly name: string;
    readonly isAiPlayer: boolean;
    /**
     * Why an AI player holds the seat for its human, as the seat control lines and session messages say; null
     * while its own player does.
     */
    readonly aiStandIn: SeatControlReason | null;
    readonly score: number;
    readonly tiles: readonly number[];
    readonly concealedCount: number;
    readonly drawnTileId: number | null;
    readonly discards: readonly DiscardRecord[];
    readonly melds: readonly MeldRecord[];
    readonly isRiichi: boolean;
}

export interface WinnerResult {
    readonly seat: number;
    readonly closedTiles: readonly number[];
    readonly melds: readonly number[];
    readonly winningTile: number;
    readonly handResult: {
        readonly han: number;
        readonly fu: number;
        readonly yaku: readonly { readonly yakuId: number; readonly han: number }[];
    };
}

export interface RoundEndResult {
    readonly resultType: RoundEndEvent["resultType"];
    readonly winners: readonly WinnerResult[];
    readonly scoreChanges: Readonly<Record<string, number>>;
    /** The wire's `scores`: after riichi deposits, before this round's payments. */
    readonly scoresBeforePayment: Readonly<Record<string, number>>;
    readonly doraIndicators: readonly number[];
    readonly uraDoraIndicators: readonly number[];
    readonly loserSeat?: number;
}

export interface GameEndResult {
    readonly winnerSeat: number;
    /** The riichi sticks left on the table at the end, paid to the winner: its standing's score holds them. */
    readonly leftoverRiichiBonus: number;
    readonly standings: readonly {
        readonly seat: number;
        readonly score: number;
        readonly finalScore: number;
    }[];
}

export type GamePhase = "pre_game" | "in_round" | "round_ended" | "game_ended";

export interface TableState {
    readonly gameId: string;
    readonly players: readonly PlayerState[];
    /** The game's first dealer (East 1's), from which a round's number within its wind counts. */
    readonly firstDealerSeat: number;
    readonly dealerSeat: number;
    readonly roundWind: number;
    readonly honbaSticks: number;
    readonly riichiSticks: number;
    readonly doraIndicators: readonly number[];
    readonly currentPlayerSeat: number;
    readonly tilesRemaining: number;
    readonly phase: GamePhase;
    readonly lastEventDescription: string;
    readonly roundEndResult: RoundEndResult | null;
    readonly gameEndResult: GameEndResult | null;
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

/**
 * A closed or added kan its declarer declared on its own turn and that a ron may rob (chankan), shown before the
 * chankan resolves. No message carries it as such: a chankan prompt names its tile and declarer, a robbed kan's round
 * end names it, its type too; a kan nobody robs completes as the server's meld event. `kanType` is null when the
 * source names none (a prompt): the kan is then added when the declarer holds a pon of the tile, else closed, as the
 * server decides.
 */
export interface KanDeclaredEvent {
    readonly type: "kan_declared";
    readonly seat: number;
    readonly tileId: number;
    readonly kanType: Extract<KanType, "added" | "closed"> | null;
}

/**
 * Everything that changes the table: the events a replay stores, the replay-only seat control lines, the reconnect
 * snapshot that rebuilds the table, the session messages that mark a seat's human leaving and returning, and a kan
 * declared open to chankan.
 */
export type TableEvent =
    | ReplayEvent
    | KanDeclaredEvent
    | SeatControlLine
    | GameReconnectedEvent
    | PlayerLeftMessage
    | PlayerReconnectedMessage;
