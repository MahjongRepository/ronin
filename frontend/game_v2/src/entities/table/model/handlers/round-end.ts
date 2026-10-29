import { drewUnseen, updatePlayer } from "@/entities/table/model/helpers";
import {
    type PlayerState,
    type RoundEndResult,
    type TableState,
    type WinnerResult,
} from "@/entities/table/model/types";
import { assertNever } from "@/shared/lib";
import {
    type DoubleRonRoundEnd,
    type NagashiManganRoundEnd,
    ROUND_RESULT_TYPE,
    type RonRoundEnd,
    type RoundEndEvent,
    type TsumoRoundEnd,
} from "@/shared/protocol";

import { applyKanDeclared, robbedKanDeclared } from "./kan-declared";

function playerName(state: TableState, seat: number): string {
    return state.players.find((p) => p.seat === seat)?.name ?? `Seat ${seat}`;
}

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

function tsumoDescription(state: TableState, event: TsumoRoundEnd): string {
    return `Tsumo by ${playerName(state, event.winnerSeat)}`;
}

function ronDescription(state: TableState, event: RonRoundEnd): string {
    return `Ron by ${playerName(state, event.winnerSeat)} from ${playerName(state, event.loserSeat)}`;
}

function doubleRonDescription(state: TableState, event: DoubleRonRoundEnd): string {
    const names = event.winners.map((w) => playerName(state, w.winnerSeat));
    return `Double ron by ${names.join(" and ")}`;
}

function nagashiDescription(state: TableState, event: NagashiManganRoundEnd): string {
    const names = event.qualifyingSeats.map((seat) => playerName(state, seat));
    return `Nagashi mangan by ${names.join(" and ")}`;
}

function roundEndDescription(state: TableState, event: RoundEndEvent): string {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.TSUMO: {
            return tsumoDescription(state, event);
        }
        case ROUND_RESULT_TYPE.RON: {
            return ronDescription(state, event);
        }
        case ROUND_RESULT_TYPE.DOUBLE_RON: {
            return doubleRonDescription(state, event);
        }
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW: {
            return "Exhaustive draw";
        }
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW: {
            return `Abortive draw: ${event.reason}`;
        }
        case ROUND_RESULT_TYPE.NAGASHI_MANGAN: {
            return nagashiDescription(state, event);
        }
        default: {
            return assertNever(event);
        }
    }
}

function extractWinnerFromSingle(event: TsumoRoundEnd | RonRoundEnd): WinnerResult {
    return {
        closedTiles: event.closedTiles,
        handResult: event.handResult,
        melds: event.melds,
        seat: event.winnerSeat,
        winningTile: event.winningTile,
    };
}

function collectUraDoraIndicators(event: RoundEndEvent): number[] {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.TSUMO:
        case ROUND_RESULT_TYPE.RON: {
            return event.uraDoraIndicators ?? [];
        }
        case ROUND_RESULT_TYPE.DOUBLE_RON: {
            const ids = new Set<number>();
            for (const w of event.winners) {
                for (const id of w.uraDoraIndicators ?? []) {
                    ids.add(id);
                }
            }
            return [...ids];
        }
        default: {
            return [];
        }
    }
}

/** The round end's result as the table keeps it for the overlay, beside the dora indicators the round showed. */
export function extractRoundEndResult(
    event: RoundEndEvent,
    doraIndicators: readonly number[],
): RoundEndResult {
    const uraDoraIndicators = collectUraDoraIndicators(event);

    switch (event.resultType) {
        case ROUND_RESULT_TYPE.TSUMO: {
            return {
                doraIndicators,
                resultType: event.resultType,
                scoreChanges: event.scoreChanges,
                scoresBeforePayment: event.scores,
                uraDoraIndicators,
                winners: [extractWinnerFromSingle(event)],
            };
        }
        case ROUND_RESULT_TYPE.RON: {
            return {
                doraIndicators,
                loserSeat: event.loserSeat,
                resultType: event.resultType,
                scoreChanges: event.scoreChanges,
                scoresBeforePayment: event.scores,
                uraDoraIndicators,
                winners: [extractWinnerFromSingle(event)],
            };
        }
        case ROUND_RESULT_TYPE.DOUBLE_RON: {
            return {
                doraIndicators,
                loserSeat: event.loserSeat,
                resultType: event.resultType,
                scoreChanges: event.scoreChanges,
                scoresBeforePayment: event.scores,
                uraDoraIndicators,
                winners: event.winners.map((w) => ({
                    closedTiles: w.closedTiles,
                    handResult: w.handResult,
                    melds: w.melds,
                    seat: w.winnerSeat,
                    winningTile: event.winningTile,
                })),
            };
        }
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW:
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW:
        case ROUND_RESULT_TYPE.NAGASHI_MANGAN: {
            return {
                doraIndicators,
                resultType: event.resultType,
                scoreChanges: event.scoreChanges,
                scoresBeforePayment: event.scores,
                uraDoraIndicators,
                winners: [],
            };
        }
        default: {
            return assertNever(event);
        }
    }
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

/** Show the hands the result reveals: their tiles become known and nothing of them stays concealed. */
function revealHands(players: readonly PlayerState[], event: RoundEndEvent): PlayerState[] {
    return revealedHands(event).reduce(
        (revealed, hand) =>
            updatePlayer(revealed, hand.seat, {
                concealedCount: 0,
                drawnTileId: hand.drawnTileId,
                tiles: hand.tiles,
            }),
        [...players],
    );
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
    return {
        ...drawn,
        lastEventDescription: roundEndDescription(state, event),
        phase: "round_ended",
        players: revealHands(settleScores(drawn.players, event), event),
        riichiSticks: state.riichiSticks - riichiSticksCollected(event),
        roundEndResult: extractRoundEndResult(event, state.doraIndicators),
    };
}
