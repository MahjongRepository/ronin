import { drewUnseen, updatePlayer } from "@/entities/table/model/helpers";
import {
    type DrawKind,
    type DrawResult,
    type HandValue,
    type PlayerState,
    type RoundEndPage,
    type RoundEndResult,
    type TableState,
    type WinnerResult,
} from "@/entities/table/model/types";
import { assertNever } from "@/shared/lib";
import {
    type ExhaustiveDrawRoundEnd,
    type NagashiManganRoundEnd,
    ROUND_RESULT_TYPE,
    type RoundEndEvent,
} from "@/shared/protocol";

import { applyKanDeclared, robbedKanDeclared } from "./kan-declared";
import { roundRecordOfResult } from "./round-record";

function settleScores(players: readonly PlayerState[], event: RoundEndEvent): PlayerState[] {
    return players.map((p) => {
        const seat = String(p.seat);
        const scoreBeforePayment = event.scores[seat];
        if (scoreBeforePayment === undefined) {
            return p;
        }
        return { ...p, score: scoreBeforePayment + (event.scoreChanges[seat] ?? 0) };
    });
}

/**
 * What a riichi stick a winner collects is worth: the server's `riichi_stick_value`, which no live message carries, at
 * its default, the one every game is played with.
 */
export const RIICHI_STICK_VALUE = 1000;

const DORA_YAKU_ID = { aka: 121, dora: 120, ura: 122 } as const;

/** The table at a round end that its result reads beyond the event: the round's dealer and dora indicators. */
export interface RoundEndContext {
    readonly dealerSeat: number;
    readonly doraIndicators: readonly number[];
}

interface WinnerSource {
    readonly winnerSeat: number;
    readonly closedTiles: readonly number[];
    readonly melds: readonly number[];
    readonly handResult: HandValue;
    readonly scoreChanges: Readonly<Record<string, number>>;
    readonly riichiSticksCollected: number;
    readonly paoSeat: number | null;
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
    const gain = scoreChanges[String(winnerSeat)] ?? 0;
    return {
        closedTiles: source.closedTiles,
        doraHan: {
            aka: yakuHan(handResult, DORA_YAKU_ID.aka),
            dora: yakuHan(handResult, DORA_YAKU_ID.dora),
            ura: yakuHan(handResult, DORA_YAKU_ID.ura),
        },
        handResult,
        honbaBonus: gain - handResult.points - sticks * RIICHI_STICK_VALUE,
        isDealer: winnerSeat === context.dealerSeat,
        melds: source.melds,
        paoSeat: source.paoSeat,
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
            return { ...tenpaiDraw("nagashi_mangan", event), nagashiSeats: event.qualifyingSeats };
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

/** The round end's result as the table keeps it for the result panel, read with the table it ended on. */
export function extractRoundEndResult(
    event: RoundEndEvent,
    context: RoundEndContext,
): RoundEndResult {
    return {
        ...ronDetail(event),
        doraIndicators: context.doraIndicators,
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

/**
 * The seats whose own draw the round ended on, before any discard or kan: the tsumo winner and the kyuushu declarer.
 * A robbed kan's declarer took its draw at the declaration.
 */
function seatsEndingOnOwnDraw(event: RoundEndEvent): number[] {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.TSUMO: {
            return [event.winnerSeat];
        }
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW: {
            return event.seat === null ? [] : [event.seat];
        }
        case ROUND_RESULT_TYPE.RON:
        case ROUND_RESULT_TYPE.DOUBLE_RON:
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW:
        case ROUND_RESULT_TYPE.NAGASHI_MANGAN: {
            return [];
        }
        default: {
            return assertNever(event);
        }
    }
}

/**
 * Take into the table the draws a hidden hand made unseen before the round ended on it: no discard or kan follows
 * them to show them. A hand that already holds its draw (a reconnect snapshot's 3n+2) took it already.
 */
function settleUnseenDraw(table: TableState, seat: number): TableState {
    const player = table.players.find((p) => p.seat === seat);
    if (player === undefined || !drewUnseen(player)) {
        return table;
    }
    return {
        ...table,
        currentPlayerSeat: seat,
        players: updatePlayer(table.players, seat, { concealedCount: player.concealedCount + 1 }),
        tilesRemaining: table.tilesRemaining - 1,
    };
}

function settleUnseenDraws(state: TableState, event: RoundEndEvent): TableState {
    let table = state;
    for (const seat of seatsEndingOnOwnDraw(event)) {
        table = settleUnseenDraw(table, seat);
    }
    return table;
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
                drawnTileId: hand.drawnTileId,
                tiles: hand.tiles,
            }),
        [...state.players],
    );
    return { ...state, players, revealedSeats: hands.map((hand) => hand.seat) };
}

/** The riichi sticks the round's winners take off the table; a draw leaves them for the next deal. */
function riichiSticksCollected(event: RoundEndEvent): number {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.TSUMO:
        case ROUND_RESULT_TYPE.RON: {
            return event.riichiSticksCollected;
        }
        case ROUND_RESULT_TYPE.DOUBLE_RON: {
            return event.winners.reduce((sum, winner) => sum + winner.riichiSticksCollected, 0);
        }
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW:
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW:
        case ROUND_RESULT_TYPE.NAGASHI_MANGAN: {
            return 0;
        }
        default: {
            return assertNever(event);
        }
    }
}

/** The table with the kan the round end's win robbed shown as declared, unless a chankan prompt showed it already. */
export function showRobbedKan(state: TableState, event: RoundEndEvent): TableState {
    const declared = robbedKanDeclared(event);
    return declared === null ? state : applyKanDeclared(state, declared);
}

/**
 * End the round: the kan a win robbed shows as declared first, then the unseen draws settle, the scores pay out and
 * the hands the result reveals show.
 */
export function applyRoundEnd(state: TableState, event: RoundEndEvent): TableState {
    const drawn = settleUnseenDraws(showRobbedKan(state, event), event);
    const result = extractRoundEndResult(event, state);
    return revealHands(
        {
            ...drawn,
            phase: "round_ended",
            players: settleScores(drawn.players, event),
            riichiSticks: state.riichiSticks - riichiSticksCollected(event),
            roundEndResult: result,
            roundHistory: [...state.roundHistory, roundRecordOfResult(state, result)],
        },
        event,
    );
}
