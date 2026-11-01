import { z } from "zod/mini";

import {
    ABORTIVE_DRAW_TYPE,
    ROUND_RESULT_TYPE,
    SESSION_MESSAGE_TYPE,
    WIRE_SCORE_DIVISOR,
} from "@/shared/protocol/constants";

import {
    calledBy,
    compactMeldSchema,
    coversEverySeat,
    discardInfoSchema,
    gamePlayerInfoSchema,
    roundInWindSchema,
    seatSchema,
    secondsSchema,
    tileIdSchema,
    tilesRemainingSchema,
    timerSettingsSchema,
    waitIdSchema,
    wireScoreMapSchema,
    wireSettingAmountSchema,
} from "./common";
import { parseRoundResult } from "./round-results";

// --- Player reconnect state (inside `pst` array) ---

const DEALT_HAND_SIZE = 13;

/** The tiles a meld takes from the closed hand's count: a kan's fourth comes back as its replacement draw. */
const TILES_PER_MELD = 3;

/** Whether a closed hand's count is one a turn leaves beside its melds: the dealt 13 less a meld's 3, a draw's 1 more. */
function isHandCount(tileCount: number, meldCount: number): boolean {
    const dealt = tileCount + meldCount * TILES_PER_MELD;
    return dealt === DEALT_HAND_SIZE || dealt === DEALT_HAND_SIZE + 1;
}

const playerReconnectStateSchema = z.pipe(
    z
        .object({
            dsc: z.array(discardInfoSchema),
            ml: z.array(compactMeldSchema),
            ri: z.boolean(),
            s: seatSchema,
            sc: z.number(),
            tc: z.int().check(z.gte(0)),
        })
        .check(
            z.refine((raw) => calledBy(raw.ml, raw.s), {
                message: "a seat's state lists a meld another seat called",
            }),
            z.refine((raw) => isHandCount(raw.tc, raw.ml.length), {
                message: "a seat's state holds a closed hand no turn leaves beside its melds",
            }),
        ),
    z.transform((raw) => ({
        discards: raw.dsc,
        isRiichi: raw.ri,
        melds: raw.ml,
        score: raw.sc * WIRE_SCORE_DIVISOR,
        seat: raw.s,
        tileCount: raw.tc,
    })),
);

const roundHistoryEntrySchema = z.pipe(
    z.object({
        dl: seatSchema,
        h: z.int(),
        ls: z.optional(seatSchema),
        ps: z.array(seatSchema),
        rn: z.optional(z.enum(ABORTIVE_DRAW_TYPE)),
        rs: z.array(seatSchema),
        rt: z.enum(ROUND_RESULT_TYPE),
        sch: wireScoreMapSchema,
        ts: z.optional(z.array(seatSchema)),
        w: z.int(),
        ws: z.array(seatSchema),
    }),
    z.transform((raw) => ({
        abortiveReason: raw.rn ?? null,
        dealerSeat: raw.dl,
        honbaSticks: raw.h,
        loserSeat: raw.ls ?? null,
        paoSeats: raw.ps,
        resultType: raw.rt,
        riichiSeats: raw.rs,
        scoreChanges: raw.sch,
        tenpaiSeats: raw.ts ?? null,
        wind: raw.w,
        winnerSeats: raw.ws,
    })),
);

// --- Game reconnected ---

interface SnapshotWhole {
    readonly mt: readonly number[];
    readonly n: number;
    readonly p: readonly { readonly seat: number }[];
    readonly pst: readonly { readonly seat: number; readonly tileCount: number }[];
    readonly re?: unknown;
    readonly rh: readonly unknown[];
    readonly s: number;
}

/** Whether the viewer's own tiles are its whole closed hand: as many as its seat's count, each tile once. */
function holdsOwnHand(raw: SnapshotWhole): boolean {
    return raw.mt.length === raw.pst[raw.s].tileCount && new Set(raw.mt).size === raw.mt.length;
}

/**
 * A snapshot whole enough to rebuild the table from it alone: every seat's player and state, the viewer's whole hand,
 * and the round history's every finished round, one per deal before the one it shows (`n` counts the deals) and that
 * one too once it ended. A snapshot lacking any of them is refused rather than made whole with a guess.
 */
function isComplete(raw: SnapshotWhole): boolean {
    const finished = raw.n + (raw.re === undefined ? 0 : 1);
    return (
        coversEverySeat(raw.p) &&
        coversEverySeat(raw.pst) &&
        holdsOwnHand(raw) &&
        raw.rh.length === finished
    );
}

/**
 * The round advance timer of a snapshot that owes the confirm while the seat's timer runs: how long it has run (`el`)
 * and its whole timeout (`at`), which the server names together, or neither.
 */
function advanceTimerOf(raw: {
    readonly at?: number;
    readonly el?: number;
}): { readonly elapsedSeconds: number; readonly seconds: number } | null {
    return raw.at === undefined || raw.el === undefined
        ? null
        : { elapsedSeconds: raw.el, seconds: raw.at };
}

export const gameReconnectedSchema = z.pipe(
    z
        .object({
            at: z.optional(secondsSchema),
            cp: seatSchema,
            dd: z.tuple([z.tuple([z.number(), z.number()]), z.tuple([z.number(), z.number()])]),
            di: z.array(tileIdSchema),
            dl: seatSchema,
            el: z.optional(secondsSchema),
            f: z.boolean(),
            fd: seatSchema,
            gid: z.string(),
            h: z.int(),
            ld: z.optional(seatSchema),
            mt: z.array(tileIdSchema),
            n: z.int(),
            oc: z.optional(z.boolean()),
            p: z.array(gamePlayerInfoSchema),
            pst: z.array(playerReconnectStateSchema),
            r: z.int(),
            re: z.optional(z.record(z.string(), z.unknown())),
            rh: z.array(roundHistoryEntrySchema),
            rsv: wireSettingAmountSchema,
            rw: roundInWindSchema,
            s: seatSchema,
            tm: timerSettingsSchema,
            tr: tilesRemainingSchema,
            type: z.literal(SESSION_MESSAGE_TYPE.GAME_RECONNECTED),
            w: z.int(),
            wi: waitIdSchema,
        })
        .check(
            z.refine(isComplete, {
                message:
                    "the snapshot lacks a seat's player or state, or a finished round of its history",
            }),
            z.refine((raw) => (raw.at === undefined) === (raw.el === undefined), {
                message:
                    "the snapshot names its round advance's elapsed time without its timeout, or its timeout without it",
            }),
        ),
    z.transform((raw) => ({
        advanceTimer: advanceTimerOf(raw),
        confirmationOwed: raw.oc ?? false,
        currentPlayerSeat: raw.cp,
        dealerDice: raw.dd,
        dealerSeat: raw.dl,
        doraIndicators: raw.di,
        firstDealerSeat: raw.fd,
        gameId: raw.gid,
        honbaSticks: raw.h,
        isFuriten: raw.f,
        latestDiscardSeat: raw.ld ?? null,
        myTiles: raw.mt,
        playerStates: raw.pst,
        players: raw.p,
        riichiStickValue: raw.rsv,
        riichiSticks: raw.r,
        roundHistory: raw.rh,
        roundInWind: raw.rw,
        roundNumber: raw.n,
        roundResult: raw.re ? parseRoundResult(raw.re) : null,
        seat: raw.s,
        tilesRemaining: raw.tr,
        timer: raw.tm,
        type: "game_reconnected" as const,
        waitId: raw.wi,
        wind: raw.w,
    })),
);

export type GameReconnectedEvent = z.output<typeof gameReconnectedSchema>;
