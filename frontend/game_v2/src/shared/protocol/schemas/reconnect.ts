import { z } from "zod/mini";

import {
    ABORTIVE_DRAW_TYPE,
    ROUND_RESULT_TYPE,
    SESSION_MESSAGE_TYPE,
    WIRE_SCORE_DIVISOR,
} from "@/shared/protocol/constants";

import {
    gamePlayerInfoSchema,
    seatSchema,
    secondsSchema,
    tileIdSchema,
    timerSettingsSchema,
    waitIdSchema,
    wireScoreMapSchema,
} from "./common";
import { parseRoundResult } from "./round-results";

// --- Discard info (inside player state `dsc` array) ---

const discardInfoSchema = z.pipe(
    z.object({
        rd: z.optional(z.boolean()),
        tg: z.optional(z.boolean()),
        ti: tileIdSchema,
    }),
    z.transform((raw) => ({
        isRiichiDiscard: raw.rd ?? false,
        isTsumogiri: raw.tg ?? false,
        tileId: raw.ti,
    })),
);

// --- Player reconnect state (inside `pst` array) ---

const playerReconnectStateSchema = z.pipe(
    z.object({
        dsc: z.array(discardInfoSchema),
        ml: z.array(z.int()),
        ri: z.boolean(),
        s: seatSchema,
        sc: z.number(),
        tc: z.int().check(z.gte(0)),
    }),
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

export const gameReconnectedSchema = z.pipe(
    z.object({
        cp: seatSchema,
        dc: z.tuple([z.number(), z.number()]),
        dd: z.tuple([z.tuple([z.number(), z.number()]), z.tuple([z.number(), z.number()])]),
        di: z.array(tileIdSchema),
        dl: seatSchema,
        el: z.optional(secondsSchema),
        f: z.boolean(),
        gid: z.string(),
        h: z.int(),
        mt: z.array(tileIdSchema),
        n: z.int(),
        oc: z.optional(z.boolean()),
        p: z.array(gamePlayerInfoSchema),
        pst: z.array(playerReconnectStateSchema),
        r: z.int(),
        re: z.optional(z.record(z.string(), z.unknown())),
        rh: z.array(roundHistoryEntrySchema),
        s: seatSchema,
        tm: timerSettingsSchema,
        tr: z.int(),
        type: z.literal(SESSION_MESSAGE_TYPE.GAME_RECONNECTED),
        w: z.int(),
        wi: waitIdSchema,
    }),
    z.transform((raw) => ({
        confirmationOwed: raw.oc ?? false,
        currentPlayerSeat: raw.cp,
        dealerDice: raw.dd,
        dealerSeat: raw.dl,
        dice: raw.dc,
        doraIndicators: raw.di,
        elapsedSeconds: raw.el ?? null,
        gameId: raw.gid,
        honbaSticks: raw.h,
        isFuriten: raw.f,
        myTiles: raw.mt,
        playerStates: raw.pst,
        players: raw.p,
        riichiSticks: raw.r,
        roundHistory: raw.rh,
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
