import wire from "../ronin/wire.js";
import { SEATS } from "./seats.js";

/** How a round ended, for the round list and the strip's result line. */
export const OUTCOME = Object.freeze({
    TSUMO: "tsumo",
    RON: "ron",
    DOUBLE_RON: "double_ron",
    EXHAUSTIVE: "exhaustive",
    NAGASHI: "nagashi",
    ABORT: "abort",
});

/**
 * A winner's seat, the hand's points, the seat liable for it (pao) if any, and what each seat paid for this win (by
 * seat, the honba included), from the win's own score changes: a double ron's wins each carry theirs.
 */
function winnerOutcome(winner) {
    return {
        seat: winner.ws,
        points: winner.hr.pt * wire.SCORE_DIV,
        liable: winner.ps ?? null,
        paid: scoreChanges(winner).map((change, seat) =>
            seat === winner.ws ? 0 : Math.max(0, -change),
        ),
    };
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
    [wire.RT.ABORTIVE]: (roundEnd, name) => ({
        kind: OUTCOME.ABORT,
        name,
        declarer: roundEnd.s ?? null,
    }),
};

const SEAT_NUMBERS = Array.from({ length: SEATS }, (_, seat) => seat);

/** Every seat's score change; a round end always records all four, so one missing is a damaged file. */
function scoreChanges({ sch }) {
    if (!SEAT_NUMBERS.every((seat) => Number.isInteger(sch?.[seat]))) {
        throw new Error(
            `round end has no score change (sch) for every seat: ${JSON.stringify(sch)}`,
        );
    }
    return SEAT_NUMBERS.map((seat) => sch[seat] * wire.SCORE_DIV);
}

/**
 * What the round list says of a round end whose result messages are results: who won from whom, for how much and who
 * paid it (and who was liable), or the draw's name and seats (a nine-terminals declarer's among them), and every seat's
 * score change (by seat).
 */
export function roundOutcome(roundEnd, results) {
    const outcome = OUTCOME_OF_TYPE[roundEnd.rt](roundEnd, results[0].pingju?.name);
    return { ...outcome, scoreChanges: scoreChanges(roundEnd) };
}
