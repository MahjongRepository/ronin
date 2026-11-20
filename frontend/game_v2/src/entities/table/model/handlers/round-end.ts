import { requireRiichiStickValue, seatEntry, updatePlayer } from "@/entities/table/model/helpers";
import {
    type DrawKind,
    type DrawResult,
    type HandValue,
    type MeldRecord,
    type PlayerState,
    type RoundEndPage,
    type RoundEndResult,
    type TableState,
    type WinnerResult,
} from "@/entities/table/model/types";
import { assertNever } from "@/shared/lib";
import {
    DORA_YAKU_ID,
    type ExhaustiveDrawRoundEnd,
    type PaoLiability,
    ROUND_RESULT_TYPE,
    type RonRoundEnd,
    type RoundEndEvent,
} from "@/shared/protocol";

function settleScores(players: readonly PlayerState[], event: RoundEndEvent): PlayerState[] {
    return players.map((p) => ({
        ...p,
        score: seatEntry(event.scores, p.seat) + seatEntry(event.scoreChanges, p.seat),
    }));
}

/**
 * What a round end's result reads beyond the event: the game's riichi stick value, which the event's collected sticks
 * are paid at, and each seat's melds as the round ended, which tell a ron that robbed a kan (the server announces a
 * kan before anyone may rob it). Everything else of the result, the round's dealer and dora included, is the event's.
 */
export interface RoundEndContext {
    readonly riichiStickValue: number | null;
    readonly players: readonly Pick<PlayerState, "seat" | "melds">[];
}

interface WinnerSource {
    readonly winnerSeat: number;
    readonly closedTiles: readonly number[];
    readonly melds: readonly MeldRecord[];
    readonly handResult: HandValue;
    readonly scoreChanges: Readonly<Record<string, number>>;
    readonly riichiSticksCollected: number;
    readonly honbaBonus: number;
    readonly pao: PaoLiability | null;
    readonly uraDoraIndicators: readonly number[] | null;
}

function yakuHan(hand: HandValue, yakuId: number): number {
    return hand.yaku.find((yaku) => yaku.yakuId === yakuId)?.han ?? 0;
}

function extractWinner(
    source: WinnerSource,
    winningTile: number,
    context: RoundEndContext,
): WinnerResult {
    const { handResult, scoreChanges, winnerSeat } = source;
    const sticks = source.riichiSticksCollected;
    const riichiBonus = sticks === 0 ? 0 : sticks * requireRiichiStickValue(context);
    return {
        closedTiles: source.closedTiles,
        doraHan: {
            aka: yakuHan(handResult, DORA_YAKU_ID.AKA),
            dora: yakuHan(handResult, DORA_YAKU_ID.DORA),
            ura: yakuHan(handResult, DORA_YAKU_ID.URA),
        },
        handResult,
        honbaBonus: source.honbaBonus,
        melds: source.melds,
        pao: source.pao,
        riichiBonus,
        riichiSticksCollected: sticks,
        scoreChanges,
        seat: winnerSeat,
        uraDoraIndicators: source.uraDoraIndicators ?? [],
        winningTile,
    };
}

const NO_SEATS: readonly number[] = [];

function emptyDraw(kind: DrawKind): DrawResult {
    return {
        declarerSeat: null,
        kind,
        nagashiSeats: NO_SEATS,
        notenSeats: NO_SEATS,
        ronSeats: NO_SEATS,
        shownHands: [],
        tenpaiSeats: NO_SEATS,
    };
}

function exhaustiveDraw(event: ExhaustiveDrawRoundEnd): DrawResult {
    return {
        ...emptyDraw(event.qualifyingSeats.length === 0 ? "exhaustive" : "nagashi_mangan"),
        nagashiSeats: event.qualifyingSeats,
        notenSeats: event.notenSeats,
        shownHands: event.tenpaiHands,
        tenpaiSeats: event.tenpaiSeats,
    };
}

function resultWinners(event: RoundEndEvent, context: RoundEndContext): readonly WinnerResult[] {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.TSUMO: {
            return [extractWinner(event, event.winningTile, context)];
        }
        case ROUND_RESULT_TYPE.RON: {
            return event.winners.map((winner) => extractWinner(winner, event.winningTile, context));
        }
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW:
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW: {
            return [];
        }
        default: {
            return assertNever(event);
        }
    }
}

function resultDraw(event: RoundEndEvent): DrawResult | null {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.TSUMO:
        case ROUND_RESULT_TYPE.RON: {
            return null;
        }
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW: {
            return exhaustiveDraw(event);
        }
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW: {
            return {
                ...emptyDraw(event.reason),
                declarerSeat: event.seat,
                ronSeats: event.ronSeats,
                shownHands: event.shownHands,
            };
        }
        default: {
            return assertNever(event);
        }
    }
}

/** Whether a ron robbed a kan: its won tile lies in a kan of the loser's, declared before the ron. */
function robsKan(event: RonRoundEnd, context: RoundEndContext): boolean {
    const loser = context.players.find((player) => player.seat === event.loserSeat);
    return (
        loser?.melds.some(
            (meld) =>
                (meld.meldType === "added_kan" || meld.meldType === "closed_kan") &&
                meld.tileIds.includes(event.winningTile),
        ) ?? false
    );
}

interface RonDetail {
    readonly loserSeat: number | null;
    readonly headBumpedSeats: readonly number[];
    readonly kanRobbed: boolean;
}

function ronDetail(event: RoundEndEvent, context: RoundEndContext): RonDetail {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.RON: {
            return {
                headBumpedSeats: event.headBumpedSeats,
                kanRobbed: robsKan(event, context),
                loserSeat: event.loserSeat,
            };
        }
        case ROUND_RESULT_TYPE.TSUMO:
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW:
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW: {
            return { headBumpedSeats: NO_SEATS, kanRobbed: false, loserSeat: null };
        }
        default: {
            return assertNever(event);
        }
    }
}

/** The round end's result as the table keeps it for the result panel, every fact of it the server's. */
export function extractRoundEndResult(
    event: RoundEndEvent,
    context: RoundEndContext,
): RoundEndResult {
    return {
        ...ronDetail(event, context),
        dealerSeat: event.dealerSeat,
        doraIndicators: event.doraIndicators,
        draw: resultDraw(event),
        resultType: event.resultType,
        scoreChanges: event.scoreChanges,
        scoresBeforePayment: event.scores,
        winners: resultWinners(event, context),
    };
}

/** The pages a result shows: a winner's each, in the server's order, or the draw's one. */
export function roundEndPages(result: RoundEndResult): readonly RoundEndPage[] {
    if (result.draw !== null) {
        return [{ draw: result.draw, kind: "draw" }];
    }
    return result.winners.map((winner) => ({ kind: "win", winner }));
}

interface RevealedHand {
    readonly seat: number;
    readonly tiles: readonly number[];
    readonly drawnTileId: number | null;
}

/** The drawn tile of a seat whose hand an abort shows, kept apart while the shown tiles still hold it. */
function shownDrawnTile(state: TableState, seat: number, tiles: readonly number[]): number | null {
    const drawn = state.players.find((player) => player.seat === seat)?.drawnTileId ?? null;
    return drawn !== null && tiles.includes(drawn) ? drawn : null;
}

/** The closed hands a result shows: its winners', the tenpai hands of an exhaustive draw, the hands an abort shows. */
function revealedHands(state: TableState, event: RoundEndEvent): RevealedHand[] {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.TSUMO: {
            const tiles = [...event.closedTiles, event.winningTile];
            return [{ drawnTileId: event.winningTile, seat: event.winnerSeat, tiles }];
        }
        case ROUND_RESULT_TYPE.RON: {
            return event.winners.map((winner) => ({
                drawnTileId: null,
                seat: winner.winnerSeat,
                tiles: winner.closedTiles,
            }));
        }
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW: {
            return event.tenpaiHands.map((hand) => ({
                drawnTileId: null,
                seat: hand.seat,
                tiles: hand.closedTiles,
            }));
        }
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW: {
            return event.shownHands.map((hand) => ({
                drawnTileId: shownDrawnTile(state, hand.seat, hand.closedTiles),
                seat: hand.seat,
                tiles: hand.closedTiles,
            }));
        }
        default: {
            return assertNever(event);
        }
    }
}

/**
 * Show the hands the result reveals: their tiles become known, nothing of them stays concealed, and their seats show
 * face up from every perspective.
 */
export function revealHands(state: TableState, event: RoundEndEvent): TableState {
    const hands = revealedHands(state, event);
    const players = hands.reduce(
        (revealed, hand) =>
            updatePlayer(revealed, hand.seat, {
                concealedCount: 0,
                drawnConcealed: false,
                drawnTileId: hand.drawnTileId,
                tiles: hand.tiles,
            }),
        [...state.players],
    );
    return { ...state, players, revealedSeats: hands.map((hand) => hand.seat) };
}

/**
 * End the round: the scores pay out, the table keeps the riichi sticks the server says the result left, and the hands
 * the result reveals show. Whatever ended it, the latest discard is unmarked and lies in the river as any other.
 */
export function applyRoundEnd(state: TableState, event: RoundEndEvent): TableState {
    const result = extractRoundEndResult(event, state);
    return revealHands(
        {
            ...state,
            lastDiscardSeat: null,
            phase: "round_ended",
            players: settleScores(state.players, event),
            riichiSticks: event.riichiSticks,
            roundEndResult: result,
        },
        event,
    );
}
