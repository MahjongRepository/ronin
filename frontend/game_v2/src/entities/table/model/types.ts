import {
    type AbortiveDrawType,
    type DiscardEvent,
    type DoraRevealedEvent,
    type DrawEvent,
    type DrawNoticeEvent,
    type GameEndCause,
    type GameEndEvent,
    type GameReconnectedEvent,
    type GameStartedEvent,
    type GameType,
    type KanType,
    type MeldEvent,
    type MeldType,
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
 * which another seat's draw notice raises as the draw happens. A replay shows every hand, so its counts stay 0.
 */
export interface PlayerState {
    readonly seat: number;
    readonly name: string;
    readonly isAiPlayer: boolean;
    /**
     * Why an AI player holds the seat for its human, as the seat control lines, the live seat control messages and the
     * reconnect snapshot say; null while its own player does. Such a seat is never `isAiPlayer`.
     */
    readonly aiStandIn: SeatControlReason | null;
    readonly score: number;
    readonly tiles: readonly number[];
    readonly concealedCount: number;
    readonly drawnTileId: number | null;
    /** One of the face-down tiles is the seat's draw a notice announced, apart from the rest until its discard or call. */
    readonly drawnConcealed: boolean;
    readonly discards: readonly DiscardRecord[];
    readonly melds: readonly MeldRecord[];
    readonly isRiichi: boolean;
}

/** A yaku of a winning hand: its id, its han, and whether the server scored it as a yakuman. */
export interface YakuResult {
    readonly yakuId: number;
    readonly han: number;
    readonly isYakuman: boolean;
}

/** A winning hand's value as the server scored it. */
export interface HandValue {
    readonly han: number;
    readonly fu: number;
    /** The hand's value without honba or riichi sticks, which pao does not change: the ron payment, or every tsumo payment together. */
    readonly points: number;
    /** Every yaku with its han, the dora, red-five and ura dora entries among them, in the server's order. */
    readonly yaku: readonly YakuResult[];
}

/** One winner's page of a round's result: its hand, its value and its own payments. */
export interface WinnerResult {
    readonly seat: number;
    readonly isDealer: boolean;
    readonly closedTiles: readonly number[];
    readonly melds: readonly number[];
    readonly winningTile: number;
    readonly handResult: HandValue;
    /** The han of each kind of dora, out of `handResult.yaku`. */
    readonly doraHan: { readonly dora: number; readonly aka: number; readonly ura: number };
    /** This winner's ura dora indicators: none unless it won in riichi. */
    readonly uraDoraIndicators: readonly number[];
    /**
     * This winner's own payments, a part of the result's aggregate `scoreChanges` for a double ron. They describe the
     * payment only: the table settles from the aggregate, once.
     */
    readonly scoreChanges: Readonly<Record<string, number>>;
    /** The honba bonus this winner collected, in points: its own gain beyond its hand value and riichi sticks. */
    readonly honbaBonus: number;
    readonly riichiSticksCollected: number;
    /** What the riichi sticks this winner collected paid it, in points, at the game's stick value. */
    readonly riichiBonus: number;
    /** The seat liable for this winner's pao yakuman, or null. */
    readonly paoSeat: number | null;
}

export type DrawKind = "exhaustive" | "nagashi_mangan" | AbortiveDrawType;

export interface TenpaiHandResult {
    readonly seat: number;
    readonly closedTiles: readonly number[];
    readonly melds: readonly number[];
}

/** A drawn round's result: its kind and the seats it names. Seat lists are empty where the kind names none. */
export interface DrawResult {
    readonly kind: DrawKind;
    readonly tenpaiSeats: readonly number[];
    readonly notenSeats: readonly number[];
    readonly tenpaiHands: readonly TenpaiHandResult[];
    /** The seats whose discards made a nagashi mangan. */
    readonly nagashiSeats: readonly number[];
    /** The seat that declared kyuushu kyuuhai, or null. */
    readonly declarerSeat: number | null;
    /** The seats that declared the triple ron, in caller order. */
    readonly ronSeats: readonly number[];
}

export interface RoundEndResult {
    readonly resultType: RoundEndEvent["resultType"];
    /** One per winner, in the server's order; empty for a draw. */
    readonly winners: readonly WinnerResult[];
    /** The discarder (or robbed kan's declarer) of a ron, or null. */
    readonly loserSeat: number | null;
    /** The seats that also declared ron on the tile and lost it to head bump, in caller order. */
    readonly headBumpedSeats: readonly number[];
    /** Whether the ron robbed the loser's kan (chankan) rather than taking a discard. */
    readonly kanRobbed: boolean;
    /** The aggregate payments, which the table settles once. */
    readonly scoreChanges: Readonly<Record<string, number>>;
    /** The wire's `scores`: after riichi deposits, before this round's payments. */
    readonly scoresBeforePayment: Readonly<Record<string, number>>;
    readonly doraIndicators: readonly number[];
    readonly draw: DrawResult | null;
    /**
     * Whether the table the result was read against was in step with the server: false for the game's last round end
     * a live client took out of step, whose dora indicators and dealer came from a table that may be stale.
     */
    readonly inStep: boolean;
}

/** One page of a round's result: a winner's, or the draw's. A double ron has a page per winner. */
export type RoundEndPage =
    | { readonly kind: "win"; readonly winner: WinnerResult }
    | { readonly kind: "draw"; readonly draw: DrawResult };

export interface GameEndResult {
    readonly winnerSeat: number;
    /** The rule that ended the game, as the server's engine decided it. */
    readonly endCause: GameEndCause;
    /** The riichi sticks left on the table at the end, paid to the winner: its standing's score holds them. */
    readonly leftoverRiichiBonus: number;
    /**
     * How many riichi sticks the server held as the game ended, awarded or not (the game end's `lr`, never the
     * table's own count, which may be out of step): a game whose rules award them to nobody pays no bonus for them.
     */
    readonly leftoverSticks: number;
    readonly standings: readonly {
        readonly seat: number;
        readonly score: number;
        readonly finalScore: number;
    }[];
}

export type GamePhase = "pre_game" | "in_round" | "round_ended" | "game_ended";

export interface TableState {
    readonly gameId: string;
    /** The game's length (east-only or hanchan) from its start; null when the table began at a reconnect's snapshot. */
    readonly gameType: GameType | null;
    readonly players: readonly PlayerState[];
    /** The game's first dealer (East 1's), from which a round's number within its wind counts. */
    readonly firstDealerSeat: number;
    readonly dealerSeat: number;
    readonly roundWind: number;
    /** The server's deal number: every deal of the game counted from 0, a hand's pending result keeping its hand's. */
    readonly roundNumber: number;
    readonly honbaSticks: number;
    readonly riichiSticks: number;
    /**
     * What a riichi takes from its declarer onto the table, the game's `riichi_cost` from its start or a reconnect's
     * snapshot; null before either.
     */
    readonly riichiCost: number | null;
    /**
     * What each riichi stick a winner collects pays it, the game's `riichi_stick_value` from its start or a reconnect's
     * snapshot; null before either. It is not the riichi cost: the game's settings may set them apart.
     */
    readonly riichiStickValue: number | null;
    readonly doraIndicators: readonly number[];
    readonly currentPlayerSeat: number;
    readonly tilesRemaining: number;
    /**
     * The seat whose discard is the table's latest while it still lies in its river: set by a discard, cleared by a
     * call that claims it (chi, pon, open kan) and by a new deal, kept through a draw and a kan from the hand; a
     * reconnect takes it from the snapshot's `ld`, which the server leaves out when there is none or a call claimed it.
     */
    readonly lastDiscardSeat: number | null;
    readonly phase: GamePhase;
    /** The ended round's result, kept through the game end that follows the last round's, until a new deal. */
    readonly roundEndResult: RoundEndResult | null;
    /**
     * The seats whose closed hands the ended round's result showed (its winners', a draw's tenpai hands), which every
     * perspective shows face up until a new deal.
     */
    readonly revealedSeats: readonly number[];
    readonly gameEndResult: GameEndResult | null;
    /**
     * Whether the table follows the server: false from a live client's loss of step (`LostStepEvent`) until a snapshot
     * rebuilds it.
     */
    readonly inStep: boolean;
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
 * A live client lost step with the server: it drops the messages that follow until a snapshot, so the table it holds
 * may miss what they carried, and the result it kept is no longer known to be the round's latest, so it goes. No
 * message carries it as such.
 */
export interface LostStepEvent {
    readonly type: "lost_step";
}

/**
 * Everything that changes the table: the events a replay stores, the seat control lines (a replay's, or the live
 * session's messages, parsed alike), the reconnect snapshot that rebuilds the table, a live seat's notice of another
 * seat's draw, a kan declared open to chankan, and a live client's loss of step.
 */
export type TableEvent =
    | ReplayEvent
    | DrawNoticeEvent
    | KanDeclaredEvent
    | LostStepEvent
    | SeatControlLine
    | GameReconnectedEvent;
