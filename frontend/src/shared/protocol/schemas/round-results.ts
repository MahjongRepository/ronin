// Zod schemas for the six round end result variants (t=4).
// Six variants based on `rt` field: tsumo (0), ron (1), double_ron (2),
// exhaustive_draw (3), abortive_draw (4), nagashi_mangan (5).
// Manual dispatch via parseRoundEnd() since Zod discriminatedUnion
// doesn't work with .transform().

import { z } from "zod";

import { EVENT_TYPE, ROUND_RESULT_TYPE } from "../constants";
import { seatSchema, tileIdSchema, wireScoreMapSchema } from "./common";
import { handResultSchema } from "./events";

// --- Tenpai hand (inside exhaustive_draw and nagashi_mangan `th` array) ---

const tenpaiHandSchema = z
    .object({
        ct: z.array(tileIdSchema),
        ml: z.array(z.number().int()),
        s: seatSchema,
    })
    .transform((raw) => ({
        closedTiles: raw.ct,
        melds: raw.ml,
        seat: raw.s,
    }));

// --- Double ron winner (inside double_ron `wn` array) ---

const doubleRonWinnerSchema = z
    .object({
        ct: z.array(tileIdSchema),
        hr: handResultSchema,
        ml: z.array(z.number().int()),
        ps: seatSchema.optional(),
        rc: z.number().int(),
        ud: z.array(tileIdSchema).optional(),
        ws: seatSchema,
    })
    .transform((raw) => ({
        closedTiles: raw.ct,
        handResult: raw.hr,
        melds: raw.ml,
        paoSeat: raw.ps ?? null,
        riichiSticksCollected: raw.rc,
        uraDoraIndicators: raw.ud ?? null,
        winnerSeat: raw.ws,
    }));

// --- Tsumo (rt=0) ---

const tsumoSchema = z
    .object({
        ct: z.array(tileIdSchema),
        hr: handResultSchema,
        ml: z.array(z.number().int()),
        ps: seatSchema.optional(),
        rc: z.number().int(),
        rt: z.literal(ROUND_RESULT_TYPE.TSUMO),
        sch: wireScoreMapSchema,
        scs: wireScoreMapSchema,
        t: z.literal(EVENT_TYPE.ROUND_END),
        ud: z.array(tileIdSchema).optional(),
        ws: seatSchema,
        wt: tileIdSchema,
    })
    .transform((raw) => ({
        closedTiles: raw.ct,
        handResult: raw.hr,
        melds: raw.ml,
        paoSeat: raw.ps ?? null,
        resultType: ROUND_RESULT_TYPE.TSUMO as typeof ROUND_RESULT_TYPE.TSUMO,
        riichiSticksCollected: raw.rc,
        scoreChanges: raw.sch,
        scores: raw.scs,
        type: "round_end" as const,
        uraDoraIndicators: raw.ud ?? null,
        winnerSeat: raw.ws,
        winningTile: raw.wt,
    }));

// --- Ron (rt=1) ---

const ronSchema = z
    .object({
        ct: z.array(tileIdSchema),
        hr: handResultSchema,
        ls: seatSchema,
        ml: z.array(z.number().int()),
        ps: seatSchema.optional(),
        rc: z.number().int(),
        rt: z.literal(ROUND_RESULT_TYPE.RON),
        sch: wireScoreMapSchema,
        scs: wireScoreMapSchema,
        t: z.literal(EVENT_TYPE.ROUND_END),
        ud: z.array(tileIdSchema).optional(),
        ws: seatSchema,
        wt: tileIdSchema,
    })
    .transform((raw) => ({
        closedTiles: raw.ct,
        handResult: raw.hr,
        loserSeat: raw.ls,
        melds: raw.ml,
        paoSeat: raw.ps ?? null,
        resultType: ROUND_RESULT_TYPE.RON as typeof ROUND_RESULT_TYPE.RON,
        riichiSticksCollected: raw.rc,
        scoreChanges: raw.sch,
        scores: raw.scs,
        type: "round_end" as const,
        uraDoraIndicators: raw.ud ?? null,
        winnerSeat: raw.ws,
        winningTile: raw.wt,
    }));

// --- Double Ron (rt=2) ---

const doubleRonSchema = z
    .object({
        ls: seatSchema,
        rt: z.literal(ROUND_RESULT_TYPE.DOUBLE_RON),
        sch: wireScoreMapSchema,
        scs: wireScoreMapSchema,
        t: z.literal(EVENT_TYPE.ROUND_END),
        wn: z.array(doubleRonWinnerSchema),
        wt: tileIdSchema,
    })
    .transform((raw) => ({
        loserSeat: raw.ls,
        resultType: ROUND_RESULT_TYPE.DOUBLE_RON as typeof ROUND_RESULT_TYPE.DOUBLE_RON,
        scoreChanges: raw.sch,
        scores: raw.scs,
        type: "round_end" as const,
        winners: raw.wn,
        winningTile: raw.wt,
    }));

// --- Exhaustive Draw (rt=3) ---

const exhaustiveDrawSchema = z
    .object({
        ns: z.array(seatSchema),
        rt: z.literal(ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW),
        sch: wireScoreMapSchema,
        scs: wireScoreMapSchema,
        t: z.literal(EVENT_TYPE.ROUND_END),
        th: z.array(tenpaiHandSchema),
        ts: z.array(seatSchema),
    })
    .transform((raw) => ({
        notenSeats: raw.ns,
        resultType: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW as typeof ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
        scoreChanges: raw.sch,
        scores: raw.scs,
        tenpaiHands: raw.th,
        tenpaiSeats: raw.ts,
        type: "round_end" as const,
    }));

// --- Abortive Draw (rt=4) ---

const abortiveDrawSchema = z
    .object({
        rn: z.string(),
        rt: z.literal(ROUND_RESULT_TYPE.ABORTIVE_DRAW),
        s: seatSchema.optional(),
        sch: wireScoreMapSchema,
        scs: wireScoreMapSchema,
        t: z.literal(EVENT_TYPE.ROUND_END),
    })
    .transform((raw) => ({
        reason: raw.rn,
        resultType: ROUND_RESULT_TYPE.ABORTIVE_DRAW as typeof ROUND_RESULT_TYPE.ABORTIVE_DRAW,
        scoreChanges: raw.sch,
        scores: raw.scs,
        seat: raw.s ?? null,
        type: "round_end" as const,
    }));

// --- Nagashi Mangan (rt=5) ---

const nagashiManganSchema = z
    .object({
        ns: z.array(seatSchema),
        qs: z.array(seatSchema),
        rt: z.literal(ROUND_RESULT_TYPE.NAGASHI_MANGAN),
        sch: wireScoreMapSchema,
        scs: wireScoreMapSchema,
        t: z.literal(EVENT_TYPE.ROUND_END),
        th: z.array(tenpaiHandSchema),
        ts: z.array(seatSchema),
    })
    .transform((raw) => ({
        notenSeats: raw.ns,
        qualifyingSeats: raw.qs,
        resultType: ROUND_RESULT_TYPE.NAGASHI_MANGAN as typeof ROUND_RESULT_TYPE.NAGASHI_MANGAN,
        scoreChanges: raw.sch,
        scores: raw.scs,
        tenpaiHands: raw.th,
        tenpaiSeats: raw.ts,
        type: "round_end" as const,
    }));

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

export function parseRoundEnd(raw: Record<string, unknown>): RoundEndEvent {
    const { rt } = raw;
    switch (rt) {
        case ROUND_RESULT_TYPE.TSUMO:
            return tsumoSchema.parse(raw);
        case ROUND_RESULT_TYPE.RON:
            return ronSchema.parse(raw);
        case ROUND_RESULT_TYPE.DOUBLE_RON:
            return doubleRonSchema.parse(raw);
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW:
            return exhaustiveDrawSchema.parse(raw);
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW:
            return abortiveDrawSchema.parse(raw);
        case ROUND_RESULT_TYPE.NAGASHI_MANGAN:
            return nagashiManganSchema.parse(raw);
        default:
            throw new Error(`Unknown round result type: rt=${String(rt)}`);
    }
}
