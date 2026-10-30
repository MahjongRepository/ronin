import { z } from "zod/mini";

import { EVENT_TYPE, GAME_TYPE, WIRE_SCORE_DIVISOR } from "@/shared/protocol/constants";
import { decodeDiscard } from "@/shared/protocol/decoders/discard";
import { decodeDraw } from "@/shared/protocol/decoders/draw";
import { decodeMeldCompact } from "@/shared/protocol/decoders/meld";

import {
    gamePlayerInfoSchema,
    seatSchema,
    secondsSchema,
    tileIdSchema,
    tileTypeSchema,
    timerSettingsSchema,
    waitIdSchema,
    wireScoreSchema,
} from "./common";

// --- Available action item (inside draw event `aa` array) ---

const availableActionSchema = z.pipe(
    z.object({
        a: z.int(),
        tl: z.optional(z.nullable(z.array(tileIdSchema))),
    }),
    z.transform((raw) => ({
        action: raw.a,
        tiles: raw.tl ?? null,
    })),
);

// --- Player view (inside round_started `p` array) ---

const playerViewSchema = z.pipe(
    z.object({
        s: seatSchema,
        sc: z.number(),
        tl: z.optional(z.array(tileIdSchema)),
    }),
    z.transform((raw) => ({
        score: raw.sc * WIRE_SCORE_DIVISOR,
        seat: raw.s,
        tiles: raw.tl ?? null,
    })),
);

// --- Yaku info (inside hand result) ---

const yakuInfoSchema = z.pipe(
    z.object({
        han: z.int(),
        yi: z.int(),
    }),
    z.transform((raw) => ({
        han: raw.han,
        yakuId: raw.yi,
    })),
);

// --- Hand result info ---

export const handResultSchema = z.pipe(
    z.object({
        fu: z.int(),
        han: z.int(),
        pt: wireScoreSchema,
        yk: z.array(yakuInfoSchema),
    }),
    z.transform((raw) => ({
        fu: raw.fu,
        han: raw.han,
        points: raw.pt,
        yaku: raw.yk,
    })),
);

// --- Standing (inside game_end `st` array) ---

const playerStandingSchema = z.pipe(
    z.object({
        fs: z.number(),
        s: seatSchema,
        sc: z.number(),
    }),
    z.transform((raw) => ({
        finalScore: raw.fs,
        score: raw.sc * WIRE_SCORE_DIVISOR,
        seat: raw.s,
    })),
);

// --- Game Started (t=8) ---

export const gameStartedSchema = z.pipe(
    z.object({
        dd: z.tuple([z.tuple([z.number(), z.number()]), z.tuple([z.number(), z.number()])]),
        dl: seatSchema,
        gid: z.string(),
        gt: z.union([z.literal(GAME_TYPE.HANCHAN), z.literal(GAME_TYPE.TONPUSEN)]),
        p: z.array(gamePlayerInfoSchema),
        rc: wireScoreSchema,
        s: z.optional(seatSchema),
        t: z.literal(EVENT_TYPE.GAME_STARTED),
        tm: z.optional(timerSettingsSchema),
    }),
    z.transform((raw) => ({
        dealerDice: raw.dd,
        dealerSeat: raw.dl,
        gameId: raw.gid,
        gameType: raw.gt,
        players: raw.p,
        riichiCost: raw.rc,
        seat: raw.s ?? null,
        timer: raw.tm ?? null,
        type: "game_started" as const,
    })),
);

// --- Round Started (t=9) ---
// Accepts both live format (has `s` and `mt`) and replay format (no `s`/`mt`, but `p[].tl`).

export const roundStartedSchema = z.pipe(
    z.object({
        cp: seatSchema,
        dc: z.optional(z.tuple([z.number(), z.number()])),
        di: z.array(tileIdSchema),
        dl: seatSchema,
        h: z.int(),
        mt: z.optional(z.array(tileIdSchema)),
        n: z.int(),
        p: z.array(playerViewSchema),
        r: z.int(),
        s: z.optional(seatSchema),
        t: z.literal(EVENT_TYPE.ROUND_STARTED),
        w: z.int(),
    }),
    z.transform((raw) => ({
        currentPlayerSeat: raw.cp,
        dealerSeat: raw.dl,
        dice: raw.dc ?? ([1, 1] as [number, number]),
        doraIndicators: raw.di,
        honbaSticks: raw.h,
        myTiles: raw.mt ?? null,
        players: raw.p,
        riichiSticks: raw.r,
        roundNumber: raw.n,
        seat: raw.s ?? null,
        type: "round_started" as const,
        wind: raw.w,
    })),
);

// --- Draw (t=1) ---

export const drawSchema = z.pipe(
    z.object({
        aa: z.optional(z.array(availableActionSchema)),
        bk: z.optional(secondsSchema),
        d: z.int(),
        el: z.optional(secondsSchema),
        t: z.literal(EVENT_TYPE.DRAW),
        wi: z.optional(waitIdSchema),
    }),
    z.transform((raw) => ({
        ...decodeDraw(raw.d),
        availableActions: raw.aa ?? [],
        bankSeconds: raw.bk ?? null,
        elapsedSeconds: raw.el ?? null,
        type: "draw" as const,
        waitId: raw.wi ?? null,
    })),
);

/** Another seat's draw, told to every seat but the drawer's: its seat alone, the tile private to the drawer. */
export const drawNoticeSchema = z.pipe(
    z.object({
        s: seatSchema,
        t: z.literal(EVENT_TYPE.DRAW_NOTICE),
    }),
    z.transform((raw) => ({
        seat: raw.s,
        type: "draw_notice" as const,
    })),
);

export const turnSchema = z.pipe(
    z.object({
        bk: z.optional(secondsSchema),
        el: z.optional(secondsSchema),
        kt: z.array(tileTypeSchema),
        t: z.literal(EVENT_TYPE.TURN),
        wi: z.optional(waitIdSchema),
    }),
    z.transform((raw) => ({
        bankSeconds: raw.bk ?? null,
        elapsedSeconds: raw.el ?? null,
        kuikaeTileTypes: raw.kt,
        type: "turn" as const,
        waitId: raw.wi ?? null,
    })),
);

// --- Discard (t=2) ---

export const discardSchema = z.pipe(
    z.object({
        d: z.int(),
        t: z.literal(EVENT_TYPE.DISCARD),
    }),
    z.transform((raw) => ({
        ...decodeDiscard(raw.d),
        type: "discard" as const,
    })),
);

// --- Meld (t=0) ---

export const meldSchema = z.pipe(
    z.object({
        m: z.int(),
        t: z.literal(EVENT_TYPE.MELD),
    }),
    z.transform((raw) => ({
        ...decodeMeldCompact(raw.m),
        type: "meld" as const,
    })),
);

// --- Riichi Declared (t=5) ---

export const riichiDeclaredSchema = z.pipe(
    z.object({
        s: seatSchema,
        t: z.literal(EVENT_TYPE.RIICHI_DECLARED),
    }),
    z.transform((raw) => ({
        seat: raw.s,
        type: "riichi_declared" as const,
    })),
);

// --- Dora Revealed (t=6) ---

export const doraRevealedSchema = z.pipe(
    z.object({
        t: z.literal(EVENT_TYPE.DORA_REVEALED),
        ti: tileIdSchema,
    }),
    z.transform((raw) => ({
        tileId: raw.ti,
        type: "dora_revealed" as const,
    })),
);

// --- Error (t=7) ---

/** A game error refusing the seat's action, named by the wait id that action echoed. */
export const errorEventSchema = z.pipe(
    z.object({
        cd: z.string(),
        msg: z.string(),
        t: z.literal(EVENT_TYPE.ERROR),
        wi: z.optional(waitIdSchema),
    }),
    z.transform((raw) => ({
        code: raw.cd,
        message: raw.msg,
        type: "error" as const,
        waitId: raw.wi ?? null,
    })),
);

// --- Furiten (t=11) ---

export const furitenSchema = z.pipe(
    z.object({
        f: z.boolean(),
        t: z.literal(EVENT_TYPE.FURITEN),
    }),
    z.transform((raw) => ({
        isFuriten: raw.f,
        type: "furiten" as const,
    })),
);

// --- Game End (t=10) ---

export const gameEndSchema = z.pipe(
    z.object({
        lb: wireScoreSchema,
        nr: z.int(),
        st: z.array(playerStandingSchema),
        t: z.literal(EVENT_TYPE.GAME_END),
        ws: seatSchema,
    }),
    z.transform((raw) => ({
        leftoverRiichiBonus: raw.lb,
        numRounds: raw.nr,
        standings: raw.st,
        type: "game_end" as const,
        winnerSeat: raw.ws,
    })),
);
