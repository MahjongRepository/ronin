import { z } from "zod";

import { SESSION_MESSAGE_TYPE, WIRE_SCORE_DIVISOR } from "@/shared/protocol/constants";

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

const discardInfoSchema = z
    .object({
        rd: z.boolean().optional(),
        tg: z.boolean().optional(),
        ti: tileIdSchema,
    })
    .transform((raw) => ({
        isRiichiDiscard: raw.rd ?? false,
        isTsumogiri: raw.tg ?? false,
        tileId: raw.ti,
    }));

// --- Player reconnect state (inside `pst` array) ---

const playerReconnectStateSchema = z
    .object({
        dsc: z.array(discardInfoSchema),
        ml: z.array(z.number().int()),
        ri: z.boolean(),
        s: seatSchema,
        sc: z.number(),
        tc: z.number().int().min(0),
    })
    .transform((raw) => ({
        discards: raw.dsc,
        isRiichi: raw.ri,
        melds: raw.ml,
        score: raw.sc * WIRE_SCORE_DIVISOR,
        seat: raw.s,
        tileCount: raw.tc,
    }));

const roundHistoryEntrySchema = z
    .object({
        dl: seatSchema,
        h: z.number().int(),
        ls: seatSchema.optional(),
        rs: z.array(seatSchema),
        sch: wireScoreMapSchema,
        ts: z.array(seatSchema).optional(),
        w: z.number().int(),
        ws: z.array(seatSchema),
    })
    .transform((raw) => ({
        dealerSeat: raw.dl,
        honbaSticks: raw.h,
        loserSeat: raw.ls ?? null,
        riichiSeats: raw.rs,
        scoreChanges: raw.sch,
        tenpaiSeats: raw.ts ?? null,
        wind: raw.w,
        winnerSeats: raw.ws,
    }));

// --- Game reconnected ---

export const gameReconnectedSchema = z
    .object({
        cp: seatSchema,
        dc: z.tuple([z.number(), z.number()]),
        dd: z.tuple([z.tuple([z.number(), z.number()]), z.tuple([z.number(), z.number()])]),
        di: z.array(tileIdSchema),
        dl: seatSchema,
        el: secondsSchema.optional(),
        f: z.boolean(),
        gid: z.string(),
        h: z.number().int(),
        mt: z.array(tileIdSchema),
        n: z.number().int(),
        oc: z.boolean().optional(),
        p: z.array(gamePlayerInfoSchema),
        pst: z.array(playerReconnectStateSchema),
        r: z.number().int(),
        re: z.record(z.string(), z.unknown()).optional(),
        rh: z.array(roundHistoryEntrySchema),
        s: seatSchema,
        tm: timerSettingsSchema,
        tr: z.number().int(),
        type: z.literal(SESSION_MESSAGE_TYPE.GAME_RECONNECTED),
        w: z.number().int(),
        wi: waitIdSchema,
    })
    .transform((raw) => ({
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
    }));

export type GameReconnectedEvent = z.output<typeof gameReconnectedSchema>;
