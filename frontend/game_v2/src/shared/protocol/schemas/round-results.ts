import { z } from "zod/mini";

import {
    ABORTIVE_DRAW_TYPE,
    EVENT_TYPE,
    KAN_TYPE,
    PAO_SHARE,
    ROUND_RESULT_TYPE,
} from "@/shared/protocol/constants";

import {
    calledBy,
    compactMeldSchema,
    discardInfoSchema,
    namesDistinctSeats,
    seatSchema,
    secondsSchema,
    tileIdSchema,
    waitIdSchema,
    wireScoreMapSchema,
    wireScoreSchema,
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

/**
 * Every round end names the riichi sticks its result leaves on the table (`r`) and its round's dealer (`dl`) and
 * revealed dora indicators (`di`), beside its round advance, so the result never reads them from the client's table.
 */
const roundEndShape = {
    ...roundAdvanceShape,
    di: z.array(tileIdSchema),
    dl: seatSchema,
    r: z.int().check(z.gte(0)),
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

const paoLiabilitySchema = z.object({
    hb: z.boolean(),
    sh: z.enum(PAO_SHARE),
    yk: z.array(z.int()).check(z.minLength(1)),
});

/**
 * A winner's honba bonus (`hb`) and, with a liable seat (`ps`), what that seat pays (`pl`): the pao yakuman it covers,
 * all or half of them, and whether it pays the honba too. The server names the seat and its liability together.
 */
const winnerPaymentShape = {
    hb: wireScoreSchema,
    pl: z.optional(paoLiabilitySchema),
    ps: z.optional(seatSchema),
};

function namesPaoWhole(raw: { readonly pl?: unknown; readonly ps?: unknown }): boolean {
    return (raw.pl === undefined) === (raw.ps === undefined);
}

const PAO_NAMED_PARTLY = {
    message:
        "a winner names its liable seat without its liability, or its liability without the seat",
};

/** What the seat liable for a win's yakuman pays, by the server's word. */
export interface PaoLiability {
    readonly seat: number;
    readonly yakuIds: readonly number[];
    readonly share: (typeof PAO_SHARE)[keyof typeof PAO_SHARE];
    readonly paysHonba: boolean;
}

function paoOf(raw: {
    readonly pl?: z.output<typeof paoLiabilitySchema>;
    readonly ps?: number;
}): PaoLiability | null {
    return raw.ps === undefined || raw.pl === undefined
        ? null
        : { paysHonba: raw.pl.hb, seat: raw.ps, share: raw.pl.sh, yakuIds: raw.pl.yk };
}

// --- Double ron winner (inside double_ron `wn` array) ---

const doubleRonWinnerSchema = z.pipe(
    z
        .object({
            ct: z.array(tileIdSchema),
            hr: handResultSchema,
            ml: z.array(compactMeldSchema),
            rc: z.int(),
            sch: wireScoreMapSchema,
            ud: z.optional(z.array(tileIdSchema)),
            ...winnerPaymentShape,
            ws: seatSchema,
        })
        .check(
            z.refine((raw) => calledBy(raw.ml, raw.ws), {
                message: "a winner's hand lists a meld another seat called",
            }),
            z.refine(namesPaoWhole, PAO_NAMED_PARTLY),
        ),
    z.transform((raw) => ({
        closedTiles: raw.ct,
        handResult: raw.hr,
        honbaBonus: raw.hb,
        melds: raw.ml,
        pao: paoOf(raw),
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
            rc: z.int(),
            rt: z.literal(ROUND_RESULT_TYPE.TSUMO),
            sch: wireScoreMapSchema,
            scs: wireScoreMapSchema,
            t: z.literal(EVENT_TYPE.ROUND_END),
            ud: z.optional(z.array(tileIdSchema)),
            ...roundEndShape,
            ...winnerPaymentShape,
            ws: seatSchema,
            wt: tileIdSchema,
        })
        .check(
            z.refine((raw) => calledBy(raw.ml, raw.ws), {
                message: "a winner's hand lists a meld another seat called",
            }),
            z.refine(namesPaoWhole, PAO_NAMED_PARTLY),
        ),
    z.transform((raw) => ({
        closedTiles: raw.ct,
        dealerSeat: raw.dl,
        doraIndicators: raw.di,
        handResult: raw.hr,
        honbaBonus: raw.hb,
        melds: raw.ml,
        pao: paoOf(raw),
        resultType: ROUND_RESULT_TYPE.TSUMO as typeof ROUND_RESULT_TYPE.TSUMO,
        riichiSticks: raw.r,
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
            rc: z.int(),
            rk: z.optional(robbedKanSchema),
            rt: z.literal(ROUND_RESULT_TYPE.RON),
            sch: wireScoreMapSchema,
            scs: wireScoreMapSchema,
            t: z.literal(EVENT_TYPE.ROUND_END),
            ud: z.optional(z.array(tileIdSchema)),
            ...roundEndShape,
            ...winnerPaymentShape,
            ws: seatSchema,
            wt: tileIdSchema,
        })
        .check(
            z.refine((raw) => calledBy(raw.ml, raw.ws), {
                message: "a winner's hand lists a meld another seat called",
            }),
            z.refine(namesPaoWhole, PAO_NAMED_PARTLY),
        ),
    z.transform((raw) => ({
        closedTiles: raw.ct,
        dealerSeat: raw.dl,
        doraIndicators: raw.di,
        handResult: raw.hr,
        headBumpedSeats: raw.hbs ?? [],
        honbaBonus: raw.hb,
        loserSeat: raw.ls,
        melds: raw.ml,
        pao: paoOf(raw),
        resultType: ROUND_RESULT_TYPE.RON as typeof ROUND_RESULT_TYPE.RON,
        riichiSticks: raw.r,
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
            ...roundEndShape,
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
        dealerSeat: raw.dl,
        doraIndicators: raw.di,
        headBumpedSeats: raw.hbs ?? [],
        loserSeat: raw.ls,
        resultType: ROUND_RESULT_TYPE.DOUBLE_RON as typeof ROUND_RESULT_TYPE.DOUBLE_RON,
        riichiSticks: raw.r,
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
        ...roundEndShape,
    }),
    z.transform((raw) => ({
        dealerSeat: raw.dl,
        doraIndicators: raw.di,
        notenSeats: raw.ns,
        resultType: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW as typeof ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
        riichiSticks: raw.r,
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
        ...roundEndShape,
    }),
    z.transform((raw) => ({
        dealerSeat: raw.dl,
        doraIndicators: raw.di,
        reason: raw.rn,
        resultType: ROUND_RESULT_TYPE.ABORTIVE_DRAW as typeof ROUND_RESULT_TYPE.ABORTIVE_DRAW,
        riichiSticks: raw.r,
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

const nagashiRiverSchema = z.pipe(
    z.object({
        dsc: z.array(discardInfoSchema).check(z.minLength(1)),
        s: seatSchema,
    }),
    z.transform((raw) => ({ discards: raw.dsc, seat: raw.s })),
);

/** A nagashi mangan names each qualifying seat's river (`qr`), its proof, in the order of the seats (`qs`). */
const nagashiManganSchema = z.pipe(
    z
        .object({
            ns: z.array(seatSchema),
            qr: z.array(nagashiRiverSchema),
            qs: z.array(seatSchema).check(z.minLength(1)),
            rt: z.literal(ROUND_RESULT_TYPE.NAGASHI_MANGAN),
            sch: wireScoreMapSchema,
            scs: wireScoreMapSchema,
            t: z.literal(EVENT_TYPE.ROUND_END),
            th: z.array(tenpaiHandSchema),
            ts: z.array(seatSchema),
            ...roundEndShape,
        })
        .check(
            z.refine(
                (raw) =>
                    raw.qr.length === raw.qs.length &&
                    raw.qr.every((river, index) => river.seat === raw.qs[index]),
                {
                    message:
                        "a nagashi mangan does not name the river of each qualifying seat, in order",
                },
            ),
        ),
    z.transform((raw) => ({
        dealerSeat: raw.dl,
        doraIndicators: raw.di,
        notenSeats: raw.ns,
        qualifyingRivers: raw.qr,
        qualifyingSeats: raw.qs,
        resultType: ROUND_RESULT_TYPE.NAGASHI_MANGAN as typeof ROUND_RESULT_TYPE.NAGASHI_MANGAN,
        riichiSticks: raw.r,
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
