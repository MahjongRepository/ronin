import wire from "../ronin/wire.js";
import { SEATS, isSeat } from "./seats.js";

/** How a round ended, for the round list and the strip's result line. */
export const OUTCOME = Object.freeze({
    TSUMO: "tsumo",
    RON: "ron",
    DOUBLE_RON: "double_ron",
    EXHAUSTIVE: "exhaustive",
    NAGASHI: "nagashi",
    ABORT: "abort",
});

/** The round end's `field`, which must be a seat: a round end without it is a damaged file. */
function seatField(record, field) {
    const value = record[field];
    if (!isSeat(value)) {
        throw new Error(`round end has no seat ${field}: ${JSON.stringify(value)}`);
    }
    return value;
}

/** The round end's `field`, a seat if present. */
function optionalSeatField(record, field) {
    return record[field] == null ? null : seatField(record, field);
}

/** The round end's `field`, which must be a list of seats. */
function seatsField(record, field) {
    const value = record[field];
    if (!Array.isArray(value) || !value.every(isSeat)) {
        throw new Error(`round end has no seat list ${field}: ${JSON.stringify(value)}`);
    }
    return value;
}

function handPoints({ hr }) {
    if (!Number.isInteger(hr?.pt)) {
        throw new Error(`round end has no hand points (hr.pt): ${JSON.stringify(hr)}`);
    }
    return hr.pt * wire.SCORE_DIV;
}

/**
 * A winner's seat, the hand's points, the seat liable for it (pao) if any, and what each seat paid for this win (by
 * seat, the honba included), from the win's own score changes: a double ron's wins each carry theirs. A liable seat that
 * dealt the ron in pays it whole as any discarder does, so no one is named liable then, as the result dialog names no
 * one (`results.js`).
 */
function winnerOutcome(winner, loser) {
    const seat = seatField(winner, "ws");
    const liable = optionalSeatField(winner, "ps");
    return {
        seat,
        points: handPoints(winner),
        liable: liable === loser ? null : liable,
        paid: scoreChanges(winner).map((change, payer) =>
            payer === seat ? 0 : Math.max(0, -change),
        ),
    };
}

function doubleRonWinners(roundEnd, loser) {
    if (!Array.isArray(roundEnd.wn) || roundEnd.wn.length === 0) {
        throw new Error(`double ron has no winners (wn): ${JSON.stringify(roundEnd.wn)}`);
    }
    return roundEnd.wn.map((winner) => winnerOutcome(winner, loser));
}

const OUTCOME_OF_TYPE = {
    [wire.RT.TSUMO]: (roundEnd) => ({
        kind: OUTCOME.TSUMO,
        winners: [winnerOutcome(roundEnd, null)],
        loser: null,
    }),
    [wire.RT.RON]: (roundEnd) => {
        const loser = seatField(roundEnd, "ls");
        return { kind: OUTCOME.RON, winners: [winnerOutcome(roundEnd, loser)], loser };
    },
    [wire.RT.DOUBLE_RON]: (roundEnd) => {
        const loser = seatField(roundEnd, "ls");
        return { kind: OUTCOME.DOUBLE_RON, winners: doubleRonWinners(roundEnd, loser), loser };
    },
    [wire.RT.EXHAUSTIVE]: (roundEnd, name) => ({
        kind: OUTCOME.EXHAUSTIVE,
        name,
        tenpai: seatsField(roundEnd, "ts"),
    }),
    [wire.RT.NAGASHI]: (roundEnd, name) => ({
        kind: OUTCOME.NAGASHI,
        name,
        players: seatsField(roundEnd, "qs"),
    }),
    [wire.RT.ABORTIVE]: (roundEnd, name) => ({
        kind: OUTCOME.ABORT,
        name,
        declarer: optionalSeatField(roundEnd, "s"),
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
 * paid it (and who was liable), or the draw's name and seats (a nine-terminals declarer's among them). Every field read
 * is checked here, so a damaged one fails the conversion at its line rather than the page drawing it. Every round end
 * records every seat's score change, which a draw's outcome does not read but its result dialog shows.
 */
export function roundOutcome(roundEnd, results) {
    if (!Object.hasOwn(OUTCOME_OF_TYPE, roundEnd.rt)) {
        throw new Error(`unknown round end type ${roundEnd.rt}`);
    }
    scoreChanges(roundEnd);
    return OUTCOME_OF_TYPE[roundEnd.rt](roundEnd, results[0].pingju?.name);
}
