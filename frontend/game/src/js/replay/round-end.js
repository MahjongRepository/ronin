import wire from "../ronin/wire.js";

/** How a round ended, for the round list. */
export const OUTCOME = Object.freeze({
    TSUMO: "tsumo",
    RON: "ron",
    DOUBLE_RON: "double_ron",
    EXHAUSTIVE: "exhaustive",
    NAGASHI: "nagashi",
    ABORT: "abort",
});

function winnerOutcome(winner) {
    return { seat: winner.ws, points: winner.hr.pt * wire.SCORE_DIV };
}

const OUTCOME_OF_TYPE = {
    [wire.RT.TSUMO]: (roundEnd) => ({
        kind: OUTCOME.TSUMO,
        winners: [winnerOutcome(roundEnd)],
        loser: null,
    }),
    [wire.RT.RON]: (roundEnd) => ({
        kind: OUTCOME.RON,
        winners: [winnerOutcome(roundEnd)],
        loser: roundEnd.ls,
    }),
    [wire.RT.DOUBLE_RON]: (roundEnd) => ({
        kind: OUTCOME.DOUBLE_RON,
        winners: roundEnd.wn.map(winnerOutcome),
        loser: roundEnd.ls,
    }),
    [wire.RT.EXHAUSTIVE]: (roundEnd, name) => ({
        kind: OUTCOME.EXHAUSTIVE,
        name,
        tenpai: roundEnd.ts,
    }),
    [wire.RT.NAGASHI]: (roundEnd, name) => ({
        kind: OUTCOME.NAGASHI,
        name,
        players: roundEnd.qs,
        tenpai: roundEnd.ts,
    }),
    [wire.RT.ABORTIVE]: (_roundEnd, name) => ({ kind: OUTCOME.ABORT, name }),
};

const SEATS = [0, 1, 2, 3];

/** Every seat's score change; a round end always records all four, so one missing is a damaged file. */
function scoreChanges({ sch }) {
    if (!SEATS.every((seat) => Number.isInteger(sch?.[seat]))) {
        throw new Error(
            `round end has no score change (sch) for every seat: ${JSON.stringify(sch)}`,
        );
    }
    return SEATS.map((seat) => sch[seat] * wire.SCORE_DIV);
}

/**
 * What the round list says of a round end whose result messages are results: who won from whom and for how much, or
 * the draw's name and seats, and every seat's score change (by seat), which splits a tsumo by payer.
 */
export function roundOutcome(roundEnd, results) {
    const outcome = OUTCOME_OF_TYPE[roundEnd.rt](roundEnd, results[0].pingju?.name);
    return { ...outcome, scoreChanges: scoreChanges(roundEnd) };
}
