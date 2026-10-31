import { z } from "zod/mini";

import {
    ABORTIVE_DRAW_TYPE,
    EVENT_TYPE,
    KAN_TYPE,
    ROUND_RESULT_TYPE,
} from "@/shared/protocol/constants";

import {
    calledBy,
    compactMeldSchema,
    namesDistinctSeats,
    seatSchema,
    secondsSchema,
    tileIdSchema,
    waitIdSchema,
    wireScoreMapSchema,
} from "./common";
import { handResultSchema } from "./events";

/** A double ron names two winners, or more where the game allows more than two rons on one discard. */
const MIN_DOUBLE_RON_WINNERS = 2;

/**
 * The round advance a live round end opens: its wait id (`wi`) and the advance's whole timeout (`at`, seconds), which
 * the server names together; the game's last round end and a replay's name neither.
 */
const roundAdvanceShape = {
    at: z.optional(secondsSchema),
    wi: z.optional(waitIdSchema),
};

const roundAdvanceWaitSchema = z.object(roundAdvanceShape).check(
    z.refine((raw) => (raw.at === undefined) === (raw.wi === undefined), {
        message:
            "a round end names its round advance's wait without its timeout, or its timeout without its wait",
    }),
);

interface RoundAdvance {
    /** How long the server's round advance timer waits from the round end, over every result it shows. */
    readonly seconds: number;
    readonly waitId: number;
}

function roundAdvanceOf(raw: { at?: number; wi?: number }): RoundAdvance | null {
    return raw.at === undefined || raw.wi === undefined
        ? null
        : { seconds: raw.at, waitId: raw.wi };
}

// --- Tenpai hand (inside exhaustive_draw and nagashi_mangan `th` array) ---

const tenpaiHandSchema = z.pipe(
    z
        .object({
            ct: z.array(tileIdSchema),
            ml: z.array(compactMeldSchema),
            s: seatSchema,
        })
        .check(
            z.refine((raw) => calledBy(raw.ml, raw.s), {
                message: "a tenpai hand lists a meld another seat called",
            }),
        ),
    z.transform((raw) => ({
        closedTiles: raw.ct,
        melds: raw.ml,
        seat: raw.s,
    })),
);

const robbedKanSchema = z.pipe(
    z.object({
        kty: z.union([z.literal(KAN_TYPE.ADDED), z.literal(KAN_TYPE.CLOSED)]),
        s: seatSchema,
        ti: tileIdSchema,
    }),
    z.transform((raw) => ({
        kanType: raw.kty,
        seat: raw.s,
        tileId: raw.ti,
    })),
);

// --- Double ron winner (inside double_ron `wn` array) ---

const doubleRonWinnerSchema = z.pipe(
    z
        .object({
            ct: z.array(tileIdSchema),
            hr: handResultSchema,
            ml: z.array(compactMeldSchema),
            ps: z.optional(seatSchema),
            rc: z.int(),
            sch: wireScoreMapSchema,
            ud: z.optional(z.array(tileIdSchema)),
            ws: seatSchema,
        })
        .check(
            z.refine((raw) => calledBy(raw.ml, raw.ws), {
                message: "a winner's hand lists a meld another seat called",
            }),
        ),
    z.transform((raw) => ({
        closedTiles: raw.ct,
        handResult: raw.hr,
        melds: raw.ml,
        paoSeat: raw.ps ?? null,
        riichiSticksCollected: raw.rc,
        scoreChanges: raw.sch,
        uraDoraIndicators: raw.ud ?? null,
        winnerSeat: raw.ws,
    })),
);

// --- Tsumo (rt=0) ---

const tsumoSchema = z.pipe(
    z
        .object({
            ct: z.array(tileIdSchema),
            hr: handResultSchema,
            ml: z.array(compactMeldSchema),
            ps: z.optional(seatSchema),
            rc: z.int(),
            rt: z.literal(ROUND_RESULT_TYPE.TSUMO),
            sch: wireScoreMapSchema,
            scs: wireScoreMapSchema,
            t: z.literal(EVENT_TYPE.ROUND_END),
            ud: z.optional(z.array(tileIdSchema)),
            ...roundAdvanceShape,
            ws: seatSchema,
            wt: tileIdSchema,
        })
        .check(
            z.refine((raw) => calledBy(raw.ml, raw.ws), {
                message: "a winner's hand lists a meld another seat called",
            }),
        ),
    z.transform((raw) => ({
        closedTiles: raw.ct,
        handResult: raw.hr,
        melds: raw.ml,
        paoSeat: raw.ps ?? null,
        resultType: ROUND_RESULT_TYPE.TSUMO as typeof ROUND_RESULT_TYPE.TSUMO,
        riichiSticksCollected: raw.rc,
        roundAdvance: roundAdvanceOf(raw),
        scoreChanges: raw.sch,
        scores: raw.scs,
        type: "round_end" as const,
        uraDoraIndicators: raw.ud ?? null,
        winnerSeat: raw.ws,
        winningTile: raw.wt,
    })),
);

// --- Ron (rt=1) ---

const ronSchema = z.pipe(
    z
        .object({
            ct: z.array(tileIdSchema),
            hbs: z.optional(z.array(seatSchema)),
            hr: handResultSchema,
            ls: seatSchema,
            ml: z.array(compactMeldSchema),
            ps: z.optional(seatSchema),
            rc: z.int(),
            rk: z.optional(robbedKanSchema),
            rt: z.literal(ROUND_RESULT_TYPE.RON),
            sch: wireScoreMapSchema,
            scs: wireScoreMapSchema,
            t: z.literal(EVENT_TYPE.ROUND_END),
            ud: z.optional(z.array(tileIdSchema)),
            ...roundAdvanceShape,
            ws: seatSchema,
            wt: tileIdSchema,
        })
        .check(
            z.refine((raw) => calledBy(raw.ml, raw.ws), {
                message: "a winner's hand lists a meld another seat called",
            }),
        ),
    z.transform((raw) => ({
        closedTiles: raw.ct,
        handResult: raw.hr,
        headBumpedSeats: raw.hbs ?? [],
        loserSeat: raw.ls,
        melds: raw.ml,
        paoSeat: raw.ps ?? null,
        resultType: ROUND_RESULT_TYPE.RON as typeof ROUND_RESULT_TYPE.RON,
        riichiSticksCollected: raw.rc,
        robbedKan: raw.rk ?? null,
        roundAdvance: roundAdvanceOf(raw),
        scoreChanges: raw.sch,
        scores: raw.scs,
        type: "round_end" as const,
        uraDoraIndicators: raw.ud ?? null,
        winnerSeat: raw.ws,
        winningTile: raw.wt,
    })),
);

// --- Double Ron (rt=2) ---

const doubleRonSchema = z.pipe(
    z
        .object({
            hbs: z.optional(z.array(seatSchema)),
            ls: seatSchema,
            rk: z.optional(robbedKanSchema),
            rt: z.literal(ROUND_RESULT_TYPE.DOUBLE_RON),
            sch: wireScoreMapSchema,
            scs: wireScoreMapSchema,
            t: z.literal(EVENT_TYPE.ROUND_END),
            ...roundAdvanceShape,
            wn: z.array(doubleRonWinnerSchema),
            wt: tileIdSchema,
        })
        .check(
            z.refine(
                (raw) =>
                    raw.wn.length >= MIN_DOUBLE_RON_WINNERS &&
                    namesDistinctSeats(raw.wn.map((winner) => winner.winnerSeat)),
                { message: "the double ron does not name at least two distinct winners" },
            ),
        ),
    z.transform((raw) => ({
        headBumpedSeats: raw.hbs ?? [],
        loserSeat: raw.ls,
        resultType: ROUND_RESULT_TYPE.DOUBLE_RON as typeof ROUND_RESULT_TYPE.DOUBLE_RON,
        robbedKan: raw.rk ?? null,
        roundAdvance: roundAdvanceOf(raw),
        scoreChanges: raw.sch,
        scores: raw.scs,
        type: "round_end" as const,
        winners: raw.wn,
        winningTile: raw.wt,
    })),
);

// --- Exhaustive Draw (rt=3) ---

const exhaustiveDrawSchema = z.pipe(
    z.object({
        ns: z.array(seatSchema),
        rt: z.literal(ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW),
        sch: wireScoreMapSchema,
        scs: wireScoreMapSchema,
        t: z.literal(EVENT_TYPE.ROUND_END),
        th: z.array(tenpaiHandSchema),
        ts: z.array(seatSchema),
        ...roundAdvanceShape,
    }),
    z.transform((raw) => ({
        notenSeats: raw.ns,
        resultType: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW as typeof ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
        roundAdvance: roundAdvanceOf(raw),
        scoreChanges: raw.sch,
        scores: raw.scs,
        tenpaiHands: raw.th,
        tenpaiSeats: raw.ts,
        type: "round_end" as const,
    })),
);

// --- Abortive Draw (rt=4) ---

const abortiveDrawSchema = z.pipe(
    z.object({
        rcl: z.optional(z.array(seatSchema)),
        rk: z.optional(robbedKanSchema),
        rn: z.enum(ABORTIVE_DRAW_TYPE),
        rt: z.literal(ROUND_RESULT_TYPE.ABORTIVE_DRAW),
        s: z.optional(seatSchema),
        sch: wireScoreMapSchema,
        scs: wireScoreMapSchema,
        t: z.literal(EVENT_TYPE.ROUND_END),
        ...roundAdvanceShape,
    }),
    z.transform((raw) => ({
        reason: raw.rn,
        resultType: ROUND_RESULT_TYPE.ABORTIVE_DRAW as typeof ROUND_RESULT_TYPE.ABORTIVE_DRAW,
        robbedKan: raw.rk ?? null,
        ronSeats: raw.rcl ?? [],
        roundAdvance: roundAdvanceOf(raw),
        scoreChanges: raw.sch,
        scores: raw.scs,
        seat: raw.s ?? null,
        type: "round_end" as const,
    })),
);

// --- Nagashi Mangan (rt=5) ---

const nagashiManganSchema = z.pipe(
    z.object({
        ns: z.array(seatSchema),
        qs: z.array(seatSchema),
        rt: z.literal(ROUND_RESULT_TYPE.NAGASHI_MANGAN),
        sch: wireScoreMapSchema,
        scs: wireScoreMapSchema,
        t: z.literal(EVENT_TYPE.ROUND_END),
        th: z.array(tenpaiHandSchema),
        ts: z.array(seatSchema),
        ...roundAdvanceShape,
    }),
    z.transform((raw) => ({
        notenSeats: raw.ns,
        qualifyingSeats: raw.qs,
        resultType: ROUND_RESULT_TYPE.NAGASHI_MANGAN as typeof ROUND_RESULT_TYPE.NAGASHI_MANGAN,
        roundAdvance: roundAdvanceOf(raw),
        scoreChanges: raw.sch,
        scores: raw.scs,
        tenpaiHands: raw.th,
        tenpaiSeats: raw.ts,
        type: "round_end" as const,
    })),
);

// --- Dispatch ---

export type TsumoRoundEnd = z.output<typeof tsumoSchema>;
export type RonRoundEnd = z.output<typeof ronSchema>;
export type DoubleRonRoundEnd = z.output<typeof doubleRonSchema>;
export type ExhaustiveDrawRoundEnd = z.output<typeof exhaustiveDrawSchema>;
export type AbortiveDrawRoundEnd = z.output<typeof abortiveDrawSchema>;
export type NagashiManganRoundEnd = z.output<typeof nagashiManganSchema>;

export type RoundEndEvent =
    | TsumoRoundEnd
    | RonRoundEnd
    | DoubleRonRoundEnd
    | ExhaustiveDrawRoundEnd
    | AbortiveDrawRoundEnd
    | NagashiManganRoundEnd;

/** Dispatch on `rt` by hand: Zod's discriminatedUnion does not work with `.transform()`. */
export function parseRoundEnd(raw: Record<string, unknown>): RoundEndEvent {
    roundAdvanceWaitSchema.parse(raw);
    const { rt } = raw;
    switch (rt) {
        case ROUND_RESULT_TYPE.TSUMO: {
            return tsumoSchema.parse(raw);
        }
        case ROUND_RESULT_TYPE.RON: {
            return ronSchema.parse(raw);
        }
        case ROUND_RESULT_TYPE.DOUBLE_RON: {
            return doubleRonSchema.parse(raw);
        }
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW: {
            return exhaustiveDrawSchema.parse(raw);
        }
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW: {
            return abortiveDrawSchema.parse(raw);
        }
        case ROUND_RESULT_TYPE.NAGASHI_MANGAN: {
            return nagashiManganSchema.parse(raw);
        }
        default: {
            throw new Error(`Unknown round result type: rt=${String(rt)}`);
        }
    }
}

/** Parse a round result carried without its event type, as the reconnect snapshot's `re`. */
export function parseRoundResult(raw: Record<string, unknown>): RoundEndEvent {
    return parseRoundEnd({ ...raw, t: EVENT_TYPE.ROUND_END });
}
