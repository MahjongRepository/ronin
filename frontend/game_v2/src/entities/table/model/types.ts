import {
    type AbortiveDrawType,
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

export interface YakuResult {
    readonly yakuId: number;
    readonly han: number;
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
}

/** One page of a round's result: a winner's, or the draw's. A double ron has a page per winner. */
export type RoundEndPage =
    | { readonly kind: "win"; readonly winner: WinnerResult }
    | { readonly kind: "draw"; readonly draw: DrawResult };

/** What ended a finished round: a tsumo, a ron (a double ron's too), or a draw of its kind. */
export type RoundOutcome = "tsumo" | "ron" | DrawKind;

/**
 * A finished round as the final standings' ledger reads it, the same whether the table saw the round end or a
 * reconnect's snapshot listed it: its wind, dealer and honba, its outcome, the seats it names and its payments.
 * `riichiSeats` are the seats whose riichi stood, so each paid its deposit in the round; `tenpaiSeats` is set only on
 * a draw that judges tenpai (exhaustive or nagashi mangan).
 */
export interface RoundRecord {
    readonly wind: number;
    readonly dealerSeat: number;
    readonly honba: number;
    readonly outcome: RoundOutcome;
    readonly winnerSeats: readonly number[];
    readonly loserSeat: number | null;
    readonly riichiSeats: readonly number[];
    readonly tenpaiSeats: readonly number[] | null;
    /** The round's payments, collected riichi sticks and honba included, riichi deposits not. */
    readonly scoreChanges: Readonly<Record<string, number>>;
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
    /**
     * The seat whose discard is the table's latest while it still lies in its river: set by a discard, cleared by any
     * meld or kan declaration and by a new deal; a reconnect's snapshot sets it when the seat in turn has just
     * discarded, else clears it.
     */
    readonly lastDiscardSeat: number | null;
    readonly phase: GamePhase;
    /** The ended round's result, kept through the game end that follows the last round's, until a new deal. */
    readonly roundEndResult: RoundEndResult | null;
    readonly gameEndResult: GameEndResult | null;
    /** Every finished round of the game in play order, for the final standings' ledger. */
    readonly roundHistory: readonly RoundRecord[];
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
