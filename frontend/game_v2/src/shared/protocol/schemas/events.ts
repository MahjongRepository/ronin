import { z } from "zod/mini";

import {
    EVENT_TYPE,
    GAME_END_CAUSE,
    GAME_TYPE,
    HAND_LIMIT,
    type HandLimit,
    NUM_PLAYERS,
    PLAYER_ACTION,
    WIRE_SCORE_DIVISOR,
} from "@/shared/protocol/constants";
import { decodeDiscard } from "@/shared/protocol/decoders/discard";
import { decodeDraw } from "@/shared/protocol/decoders/draw";

import {
    compactMeldSchema,
    coversEverySeat,
    gamePlayerInfoSchema,
    namesDistinctSeats,
    roundInWindSchema,
    seatSchema,
    secondsSchema,
    tileIdSchema,
    tileTypeSchema,
    tilesRemainingSchema,
    timerSettingsSchema,
    waitIdSchema,
    wireScoreSchema,
    wireSettingAmountSchema,
} from "./common";

// --- Available action item (inside draw event `aa` array) ---

/**
 * One offered action, by the codes the server offers on a turn: a riichi with the tile ids it may discard, a kan or an
 * added kan with the tile types it may declare, each list nonempty. Any other code or shape fails the message, so an
 * offer the client cannot read is a loss of step, never a turn offering less than the server's.
 */
const availableActionSchema = z.union([
    z.pipe(
        z.object({
            a: z.literal(PLAYER_ACTION.RIICHI),
            tl: z.array(tileIdSchema).check(z.minLength(1)),
        }),
        z.transform((raw) => ({ action: raw.a, tileIds: raw.tl })),
    ),
    z.pipe(
        z.object({
            a: z.union([z.literal(PLAYER_ACTION.KAN), z.literal(PLAYER_ACTION.ADDED_KAN)]),
            tl: z.array(tileTypeSchema).check(z.minLength(1)),
        }),
        z.transform((raw) => ({ action: raw.a, tileTypes: raw.tl })),
    ),
    z.pipe(
        z.object({
            a: z.union([z.literal(PLAYER_ACTION.TSUMO), z.literal(PLAYER_ACTION.KYUUSHU)]),
        }),
        z.transform((raw) => ({ action: raw.a })),
    ),
]);

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

/** A yaku's yakuman count (`ym`): 0 for an ordinary yaku, else how many yakuman the server scored it as. */
const yakuInfoSchema = z.pipe(
    z.object({
        han: z.int(),
        yi: z.int(),
        ym: z.int().check(z.gte(0)),
    }),
    z.transform((raw) => ({
        han: raw.han,
        yakuId: raw.yi,
        yakumanCount: raw.ym,
    })),
);

// --- Hand result info ---

const YAKUMAN_LIMITS: ReadonlySet<HandLimit> = new Set([
    HAND_LIMIT.YAKUMAN,
    HAND_LIMIT.KAZOE_YAKUMAN,
]);

/**
 * A win's hand value: its limit (`lm`) as the server paid it, and how many yakuman (`yc`) a yakuman or kazoe yakuman
 * limit counts, named for those limits alone.
 */
export const handResultSchema = z.pipe(
    z
        .object({
            fu: z.int(),
            han: z.int(),
            lm: z.enum(HAND_LIMIT),
            pt: wireScoreSchema,
            yc: z.optional(z.int().check(z.gte(1))),
            yk: z.array(yakuInfoSchema),
        })
        .check(
            z.refine((raw) => YAKUMAN_LIMITS.has(raw.lm) === (raw.yc !== undefined), {
                message:
                    "a hand result names its yakuman count without a yakuman limit, or a yakuman limit without it",
            }),
        ),
    z.transform((raw) => ({
        fu: raw.fu,
        han: raw.han,
        limit: raw.lm,
        points: raw.pt,
        yaku: raw.yk,
        yakumanCount: raw.yc ?? null,
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
    z
        .object({
            dd: z.tuple([z.tuple([z.number(), z.number()]), z.tuple([z.number(), z.number()])]),
            dl: seatSchema,
            gid: z.string(),
            gt: z.union([z.literal(GAME_TYPE.HANCHAN), z.literal(GAME_TYPE.TONPUSEN)]),
            p: z.array(gamePlayerInfoSchema),
            rsv: wireSettingAmountSchema,
            s: z.optional(seatSchema),
            t: z.literal(EVENT_TYPE.GAME_STARTED),
            tm: z.optional(timerSettingsSchema),
        })
        .check(
            z.refine((raw) => coversEverySeat(raw.p), {
                message: "the game start does not seat each of the four seats once, in seat order",
            }),
        ),
    z.transform((raw) => ({
        dealerDice: raw.dd,
        dealerSeat: raw.dl,
        gameId: raw.gid,
        gameType: raw.gt,
        players: raw.p,
        riichiStickValue: raw.rsv,
        seat: raw.s ?? null,
        timer: raw.tm ?? null,
        type: "game_started" as const,
    })),
);

// --- Round Started (t=9) ---

export const roundStartedSchema = z.pipe(
    z
        .object({
            cp: seatSchema,
            di: z.array(tileIdSchema),
            dl: seatSchema,
            h: z.int(),
            mt: z.optional(z.array(tileIdSchema)),
            n: z.int(),
            p: z.array(playerViewSchema),
            r: z.int(),
            rw: roundInWindSchema,
            s: z.optional(seatSchema),
            t: z.literal(EVENT_TYPE.ROUND_STARTED),
            tr: tilesRemainingSchema,
            w: z.int(),
        })
        .check(
            z.refine((raw) => coversEverySeat(raw.p), {
                message: "the deal does not list each of the four seats once, in seat order",
            }),
        ),
    z.transform((raw) => ({
        currentPlayerSeat: raw.cp,
        dealerSeat: raw.dl,
        doraIndicators: raw.di,
        honbaSticks: raw.h,
        myTiles: raw.mt ?? null,
        players: raw.p,
        riichiSticks: raw.r,
        roundInWind: raw.rw,
        roundNumber: raw.n,
        seat: raw.s ?? null,
        tilesRemaining: raw.tr,
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
        tr: tilesRemainingSchema,
        wi: z.optional(waitIdSchema),
    }),
    z.transform((raw) => ({
        ...decodeDraw(raw.d),
        availableActions: raw.aa ?? [],
        bankSeconds: raw.bk ?? null,
        elapsedSeconds: raw.el ?? null,
        tilesRemaining: raw.tr,
        type: "draw" as const,
        waitId: raw.wi ?? null,
    })),
);

/**
 * Another seat's draw, told to every seat but the drawer's: its seat and the live wall left after it, the tile private
 * to the drawer.
 */
export const drawNoticeSchema = z.pipe(
    z.object({
        s: seatSchema,
        t: z.literal(EVENT_TYPE.DRAW_NOTICE),
        tr: tilesRemainingSchema,
    }),
    z.transform((raw) => ({
        seat: raw.s,
        tilesRemaining: raw.tr,
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
        m: compactMeldSchema,
        t: z.literal(EVENT_TYPE.MELD),
    }),
    z.transform((raw) => ({
        ...raw.m,
        type: "meld" as const,
    })),
);

// --- Riichi Declared (t=5) ---

/** An accepted riichi: the declarer's score after its deposit and the riichi sticks on the table with it. */
export const riichiDeclaredSchema = z.pipe(
    z.object({
        r: z.int().check(z.gte(1)),
        s: seatSchema,
        sc: z.number(),
        t: z.literal(EVENT_TYPE.RIICHI_DECLARED),
    }),
    z.transform((raw) => ({
        riichiSticks: raw.r,
        score: raw.sc * WIRE_SCORE_DIVISOR,
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
    z
        .object({
            ec: z.enum(GAME_END_CAUSE),
            lb: wireScoreSchema,
            lr: z.int().check(z.gte(0)),
            nr: z.int(),
            st: z.array(playerStandingSchema),
            t: z.literal(EVENT_TYPE.GAME_END),
            ws: seatSchema,
        })
        .check(
            z.refine(
                (raw) =>
                    raw.st.length === NUM_PLAYERS &&
                    namesDistinctSeats(raw.st.map((standing) => standing.seat)),
                { message: "the standings do not rank each of the four seats once" },
            ),
        ),
    z.transform((raw) => ({
        endCause: raw.ec,
        leftoverRiichiBonus: raw.lb,
        leftoverRiichiSticks: raw.lr,
        numRounds: raw.nr,
        standings: raw.st,
        type: "game_end" as const,
        winnerSeat: raw.ws,
    })),
);
