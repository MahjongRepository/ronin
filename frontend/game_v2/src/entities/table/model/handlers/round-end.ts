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
    type NagashiManganRoundEnd,
    type PaoLiability,
    ROUND_RESULT_TYPE,
    type RoundEndEvent,
} from "@/shared/protocol";

import { applyKanDeclared, robbedKanDeclared } from "./kan-declared";

function settleScores(players: readonly PlayerState[], event: RoundEndEvent): PlayerState[] {
    return players.map((p) => ({
        ...p,
        score: seatEntry(event.scores, p.seat) + seatEntry(event.scoreChanges, p.seat),
    }));
}

/**
 * What a round end's result reads beyond the event: the game's riichi stick value, which the event's collected sticks
 * are paid at. Everything else of the result, the round's dealer and dora included, is the event's.
 */
export interface RoundEndContext {
    readonly riichiStickValue: number | null;
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
        nagashiRivers: [],
        nagashiSeats: NO_SEATS,
        notenSeats: NO_SEATS,
        ronSeats: NO_SEATS,
        tenpaiHands: [],
        tenpaiSeats: NO_SEATS,
    };
}

function tenpaiDraw(
    kind: DrawKind,
    event: ExhaustiveDrawRoundEnd | NagashiManganRoundEnd,
): DrawResult {
    return {
        ...emptyDraw(kind),
        notenSeats: event.notenSeats,
        tenpaiHands: event.tenpaiHands,
        tenpaiSeats: event.tenpaiSeats,
    };
}

function resultWinners(event: RoundEndEvent, context: RoundEndContext): readonly WinnerResult[] {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.TSUMO:
        case ROUND_RESULT_TYPE.RON: {
            return [extractWinner(event, event.winningTile, context)];
        }
        case ROUND_RESULT_TYPE.DOUBLE_RON: {
            return event.winners.map((winner) => extractWinner(winner, event.winningTile, context));
        }
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW:
        case ROUND_RESULT_TYPE.NAGASHI_MANGAN:
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
        case ROUND_RESULT_TYPE.RON:
        case ROUND_RESULT_TYPE.DOUBLE_RON: {
            return null;
        }
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW: {
            return tenpaiDraw("exhaustive", event);
        }
        case ROUND_RESULT_TYPE.NAGASHI_MANGAN: {
            return {
                ...tenpaiDraw("nagashi_mangan", event),
                nagashiRivers: event.qualifyingRivers.map((river) => ({
                    discards: river.discards.map((discard) => ({
                        isRiichi: discard.isRiichiDiscard,
                        isTsumogiri: discard.isTsumogiri,
                        tileId: discard.tileId,
                    })),
                    seat: river.seat,
                })),
                nagashiSeats: event.qualifyingSeats,
            };
        }
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW: {
            return {
                ...emptyDraw(event.reason),
                declarerSeat: event.seat,
                ronSeats: event.ronSeats,
            };
        }
        default: {
            return assertNever(event);
        }
    }
}

interface RonDetail {
    readonly loserSeat: number | null;
    readonly headBumpedSeats: readonly number[];
    readonly kanRobbed: boolean;
}

function ronDetail(event: RoundEndEvent): RonDetail {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.RON:
        case ROUND_RESULT_TYPE.DOUBLE_RON: {
            return {
                headBumpedSeats: event.headBumpedSeats,
                kanRobbed: event.robbedKan !== null,
                loserSeat: event.loserSeat,
            };
        }
        case ROUND_RESULT_TYPE.TSUMO:
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW:
        case ROUND_RESULT_TYPE.NAGASHI_MANGAN:
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
        ...ronDetail(event),
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

/** The closed hands a result shows: its winners', and the tenpai hands of a draw that judges tenpai. */
function revealedHands(event: RoundEndEvent): RevealedHand[] {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.TSUMO: {
            const tiles = [...event.closedTiles, event.winningTile];
            return [{ drawnTileId: event.winningTile, seat: event.winnerSeat, tiles }];
        }
        case ROUND_RESULT_TYPE.RON: {
            return [{ drawnTileId: null, seat: event.winnerSeat, tiles: event.closedTiles }];
        }
        case ROUND_RESULT_TYPE.DOUBLE_RON: {
            return event.winners.map((winner) => ({
                drawnTileId: null,
                seat: winner.winnerSeat,
                tiles: winner.closedTiles,
            }));
        }
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW:
        case ROUND_RESULT_TYPE.NAGASHI_MANGAN: {
            return event.tenpaiHands.map((hand) => ({
                drawnTileId: null,
                seat: hand.seat,
                tiles: hand.closedTiles,
            }));
        }
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW: {
            return [];
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
    const hands = revealedHands(event);
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

/** The table with the kan the round end's win robbed shown as declared, unless a chankan prompt showed it already. */
export function showRobbedKan(state: TableState, event: RoundEndEvent): TableState {
    const declared = robbedKanDeclared(event);
    return declared === null ? state : applyKanDeclared(state, declared);
}

/**
 * End the round: the kan a win robbed shows as declared first, then the scores pay out, the table keeps the riichi
 * sticks the server says the result left, and the hands the result reveals show.
 */
export function applyRoundEnd(state: TableState, event: RoundEndEvent): TableState {
    const declared = showRobbedKan(state, event);
    const result = extractRoundEndResult(event, state);
    return revealHands(
        {
            ...declared,
            phase: "round_ended",
            players: settleScores(declared.players, event),
            riichiSticks: event.riichiSticks,
            roundEndResult: result,
        },
        event,
    );
}
