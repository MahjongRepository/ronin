// Zod schemas for the 10 game event types (excludes call_prompt and round_end).
// Each schema parses raw wire-format dicts with single-char aliases
// into well-typed camelCase objects.

import { z } from "zod";

import { EVENT_TYPE, WIRE_SCORE_DIVISOR } from "@/shared/protocol/constants";
import { decodeDiscard } from "@/shared/protocol/decoders/discard";
import { decodeDraw } from "@/shared/protocol/decoders/draw";
import { decodeMeldCompact } from "@/shared/protocol/decoders/meld";

import { gamePlayerInfoSchema, seatSchema, tileIdSchema } from "./common";

// --- Available action item (inside draw event `aa` array) ---

const availableActionSchema = z
    .object({
        a: z.number().int(),
        tl: z.array(tileIdSchema).nullable().optional(),
    })
    .transform((raw) => ({
        action: raw.a,
        tiles: raw.tl ?? null,
    }));

// --- Player view (inside round_started `p` array) ---

const playerViewSchema = z
    .object({
        s: seatSchema,
        sc: z.number(),
        tl: z.array(tileIdSchema).optional(),
    })
    .transform((raw) => ({
        score: raw.sc * WIRE_SCORE_DIVISOR,
        seat: raw.s,
        tiles: raw.tl ?? null,
    }));

// --- Yaku info (inside hand result) ---

const yakuInfoSchema = z
    .object({
        han: z.number().int(),
        yi: z.number().int(),
    })
    .transform((raw) => ({
        han: raw.han,
        yakuId: raw.yi,
    }));

// --- Hand result info ---

export const handResultSchema = z
    .object({
        fu: z.number().int(),
        han: z.number().int(),
        yk: z.array(yakuInfoSchema),
    })
    .transform((raw) => ({
        fu: raw.fu,
        han: raw.han,
        yaku: raw.yk,
    }));

// --- Standing (inside game_end `st` array) ---

const playerStandingSchema = z
    .object({
        fs: z.number(),
        s: seatSchema,
        sc: z.number(),
    })
    .transform((raw) => ({
        finalScore: raw.fs,
        score: raw.sc * WIRE_SCORE_DIVISOR,
        seat: raw.s,
    }));

// --- Game Started (t=8) ---

export const gameStartedSchema = z
    .object({
        dd: z.tuple([z.tuple([z.number(), z.number()]), z.tuple([z.number(), z.number()])]),
        dl: seatSchema,
        gid: z.string(),
        p: z.array(gamePlayerInfoSchema),
        t: z.literal(EVENT_TYPE.GAME_STARTED),
    })
    .transform((raw) => ({
        dealerDice: raw.dd,
        dealerSeat: raw.dl,
        gameId: raw.gid,
        players: raw.p,
        type: "game_started" as const,
    }));

// --- Round Started (t=9) ---
// Accepts both live format (has `s` and `mt`) and replay format (no `s`/`mt`, but `p[].tl`).

export const roundStartedSchema = z
    .object({
        cp: seatSchema,
        dc: z.tuple([z.number(), z.number()]).optional(),
        di: z.array(tileIdSchema),
        dl: seatSchema,
        h: z.number().int(),
        mt: z.array(tileIdSchema).optional(),
        n: z.number().int(),
        p: z.array(playerViewSchema),
        r: z.number().int(),
        s: seatSchema.optional(),
        t: z.literal(EVENT_TYPE.ROUND_STARTED),
        w: z.number().int(),
    })
    .transform((raw) => ({
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
    }));

// --- Draw (t=1) ---

export const drawSchema = z
    .object({
        aa: z.array(availableActionSchema).optional(),
        d: z.number().int(),
        t: z.literal(EVENT_TYPE.DRAW),
    })
    .transform((raw) => ({
        ...decodeDraw(raw.d),
        availableActions: raw.aa ?? [],
        type: "draw" as const,
    }));

// --- Discard (t=2) ---

export const discardSchema = z
    .object({
        d: z.number().int(),
        t: z.literal(EVENT_TYPE.DISCARD),
    })
    .transform((raw) => ({
        ...decodeDiscard(raw.d),
        type: "discard" as const,
    }));

// --- Meld (t=0) ---

export const meldSchema = z
    .object({
        m: z.number().int(),
        t: z.literal(EVENT_TYPE.MELD),
    })
    .transform((raw) => ({
        ...decodeMeldCompact(raw.m),
        type: "meld" as const,
    }));

// --- Riichi Declared (t=5) ---

export const riichiDeclaredSchema = z
    .object({
        s: seatSchema,
        t: z.literal(EVENT_TYPE.RIICHI_DECLARED),
    })
    .transform((raw) => ({
        seat: raw.s,
        type: "riichi_declared" as const,
    }));

// --- Dora Revealed (t=6) ---

export const doraRevealedSchema = z
    .object({
        t: z.literal(EVENT_TYPE.DORA_REVEALED),
        ti: tileIdSchema,
    })
    .transform((raw) => ({
        tileId: raw.ti,
        type: "dora_revealed" as const,
    }));

// --- Error (t=7) ---

export const errorEventSchema = z
    .object({
        cd: z.string(),
        msg: z.string(),
        t: z.literal(EVENT_TYPE.ERROR),
    })
    .transform((raw) => ({
        code: raw.cd,
        message: raw.msg,
        type: "error" as const,
    }));

// --- Furiten (t=11) ---

export const furitenSchema = z
    .object({
        f: z.boolean(),
        t: z.literal(EVENT_TYPE.FURITEN),
    })
    .transform((raw) => ({
        isFuriten: raw.f,
        type: "furiten" as const,
    }));

// --- Game End (t=10) ---

export const gameEndSchema = z
    .object({
        nr: z.number().int().optional(),
        st: z.array(playerStandingSchema),
        t: z.literal(EVENT_TYPE.GAME_END),
        ws: seatSchema,
    })
    .transform((raw) => ({
        numRounds: raw.nr ?? 0,
        standings: raw.st,
        type: "game_end" as const,
        winnerSeat: raw.ws,
    }));
