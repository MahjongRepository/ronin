// Zod schema for the game_reconnected message.
// Matches ReconnectionSnapshot from backend/game/logic/types.py:333-350.
// Uses aliased keys (by_alias=True) plus an injected "type" field.

import { z } from "zod";

import { SESSION_MESSAGE_TYPE, WIRE_SCORE_DIVISOR } from "../constants";
import { gamePlayerInfoSchema, seatSchema, tileIdSchema } from "./common";

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
    })
    .transform((raw) => ({
        discards: raw.dsc,
        isRiichi: raw.ri,
        melds: raw.ml,
        score: raw.sc * WIRE_SCORE_DIVISOR,
        seat: raw.s,
    }));

// --- Game reconnected ---

export const gameReconnectedSchema = z
    .object({
        cp: seatSchema,
        dc: z.tuple([z.number(), z.number()]),
        dd: z.tuple([z.tuple([z.number(), z.number()]), z.tuple([z.number(), z.number()])]),
        di: z.array(tileIdSchema),
        dl: seatSchema,
        gid: z.string(),
        h: z.number().int(),
        mt: z.array(tileIdSchema),
        n: z.number().int(),
        p: z.array(gamePlayerInfoSchema),
        pst: z.array(playerReconnectStateSchema),
        r: z.number().int(),
        s: seatSchema,
        tr: z.number().int(),
        type: z.literal(SESSION_MESSAGE_TYPE.GAME_RECONNECTED),
        w: z.number().int(),
    })
    .transform((raw) => ({
        currentPlayerSeat: raw.cp,
        dealerDice: raw.dd,
        dealerSeat: raw.dl,
        dice: raw.dc,
        doraIndicators: raw.di,
        gameId: raw.gid,
        honbaSticks: raw.h,
        myTiles: raw.mt,
        playerStates: raw.pst,
        players: raw.p,
        riichiSticks: raw.r,
        roundNumber: raw.n,
        seat: raw.s,
        tilesRemaining: raw.tr,
        type: "game_reconnected" as const,
        wind: raw.w,
    }));

export type GameReconnectedEvent = z.output<typeof gameReconnectedSchema>;
