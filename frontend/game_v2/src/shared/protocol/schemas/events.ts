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
import { WIRE_KEY } from "@/shared/protocol/wire-keys";

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

/**
 * One offered action, by the codes the server offers on a turn: a riichi with the tile ids it may discard, a kan or an
 * added kan with the tile types it may declare, each list nonempty. Any other code or shape fails the message, so an
 * offer the client cannot read is a loss of step, never a turn offering less than the server's.
 */
const availableActionSchema = z.union([
    z.pipe(
        z.object({
            [WIRE_KEY.ACTION]: z.literal(PLAYER_ACTION.RIICHI),
            [WIRE_KEY.TILES]: z.array(tileIdSchema).check(z.minLength(1)),
        }),
        z.transform((raw) => ({ action: raw[WIRE_KEY.ACTION], tileIds: raw[WIRE_KEY.TILES] })),
    ),
    z.pipe(
        z.object({
            [WIRE_KEY.ACTION]: z.union([
                z.literal(PLAYER_ACTION.KAN),
                z.literal(PLAYER_ACTION.ADDED_KAN),
            ]),
            [WIRE_KEY.TILES]: z.array(tileTypeSchema).check(z.minLength(1)),
        }),
        z.transform((raw) => ({ action: raw[WIRE_KEY.ACTION], tileTypes: raw[WIRE_KEY.TILES] })),
    ),
    z.pipe(
        z.object({
            [WIRE_KEY.ACTION]: z.union([
                z.literal(PLAYER_ACTION.TSUMO),
                z.literal(PLAYER_ACTION.KYUUSHU),
            ]),
        }),
        z.transform((raw) => ({ action: raw[WIRE_KEY.ACTION] })),
    ),
]);

const playerViewSchema = z.pipe(
    z.object({
        [WIRE_KEY.SEAT]: seatSchema,
        [WIRE_KEY.SCORE]: z.number(),
        [WIRE_KEY.TILES]: z.optional(z.array(tileIdSchema)),
    }),
    z.transform((raw) => ({
        score: raw[WIRE_KEY.SCORE] * WIRE_SCORE_DIVISOR,
        seat: raw[WIRE_KEY.SEAT],
        tiles: raw[WIRE_KEY.TILES] ?? null,
    })),
);

// --- Yaku info (inside hand result) ---

/** A yaku's yakuman count (`WIRE_KEY.YAKU_YAKUMAN_COUNT`): 0 for an ordinary yaku, else how many yakuman the server scored it as. */
const yakuInfoSchema = z.pipe(
    z.object({
        [WIRE_KEY.HAN]: z.int(),
        [WIRE_KEY.YAKU_ID]: z.int(),
        [WIRE_KEY.YAKU_YAKUMAN_COUNT]: z.int().check(z.gte(0)),
    }),
    z.transform((raw) => ({
        han: raw[WIRE_KEY.HAN],
        yakuId: raw[WIRE_KEY.YAKU_ID],
        yakumanCount: raw[WIRE_KEY.YAKU_YAKUMAN_COUNT],
    })),
);

// --- Hand result info ---

const YAKUMAN_LIMITS: ReadonlySet<HandLimit> = new Set([
    HAND_LIMIT.YAKUMAN,
    HAND_LIMIT.KAZOE_YAKUMAN,
]);

/**
 * A win's hand value: its limit (`WIRE_KEY.HAND_LIMIT`) as the server paid it, and how many yakuman (`WIRE_KEY.YAKUMAN_COUNT`) a yakuman or kazoe yakuman
 * limit counts, named for those limits alone.
 */
export const handResultSchema = z.pipe(
    z
        .object({
            [WIRE_KEY.FU]: z.int(),
            [WIRE_KEY.HAN]: z.int(),
            [WIRE_KEY.HAND_LIMIT]: z.enum(HAND_LIMIT),
            [WIRE_KEY.POINTS]: wireScoreSchema,
            [WIRE_KEY.YAKUMAN_COUNT]: z.optional(z.int().check(z.gte(1))),
            [WIRE_KEY.YAKU]: z.array(yakuInfoSchema),
        })
        .check(
            z.refine(
                (raw) =>
                    YAKUMAN_LIMITS.has(raw[WIRE_KEY.HAND_LIMIT]) ===
                    (raw[WIRE_KEY.YAKUMAN_COUNT] !== undefined),
                {
                    message:
                        "a hand result names its yakuman count without a yakuman limit, or a yakuman limit without it",
                },
            ),
        ),
    z.transform((raw) => ({
        fu: raw[WIRE_KEY.FU],
        han: raw[WIRE_KEY.HAN],
        limit: raw[WIRE_KEY.HAND_LIMIT],
        points: raw[WIRE_KEY.POINTS],
        yaku: raw[WIRE_KEY.YAKU],
        yakumanCount: raw[WIRE_KEY.YAKUMAN_COUNT] ?? null,
    })),
);

const playerStandingSchema = z.pipe(
    z.object({
        [WIRE_KEY.FINAL_SCORE]: z.number(),
        [WIRE_KEY.SEAT]: seatSchema,
        [WIRE_KEY.SCORE]: z.number(),
    }),
    z.transform((raw) => ({
        finalScore: raw[WIRE_KEY.FINAL_SCORE],
        score: raw[WIRE_KEY.SCORE] * WIRE_SCORE_DIVISOR,
        seat: raw[WIRE_KEY.SEAT],
    })),
);

export const gameStartedSchema = z.pipe(
    z
        .object({
            [WIRE_KEY.DEALER_DICE]: z.tuple([
                z.tuple([z.number(), z.number()]),
                z.tuple([z.number(), z.number()]),
            ]),
            [WIRE_KEY.DEALER]: seatSchema,
            [WIRE_KEY.GAME_ID]: z.string(),
            [WIRE_KEY.GAME_TYPE]: z.union([
                z.literal(GAME_TYPE.HANCHAN),
                z.literal(GAME_TYPE.TONPUSEN),
            ]),
            [WIRE_KEY.PLAYERS]: z.array(gamePlayerInfoSchema),
            [WIRE_KEY.RIICHI_STICK_VALUE]: wireSettingAmountSchema,
            [WIRE_KEY.SEAT]: z.optional(seatSchema),
            [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.GAME_STARTED),
            [WIRE_KEY.TIMER_SETTINGS]: z.optional(timerSettingsSchema),
        })
        .check(
            z.refine((raw) => coversEverySeat(raw[WIRE_KEY.PLAYERS]), {
                message: "the game start does not seat each of the four seats once, in seat order",
            }),
        ),
    z.transform((raw) => ({
        dealerDice: raw[WIRE_KEY.DEALER_DICE],
        dealerSeat: raw[WIRE_KEY.DEALER],
        gameId: raw[WIRE_KEY.GAME_ID],
        gameType: raw[WIRE_KEY.GAME_TYPE],
        hasAkadora: true,
        players: raw[WIRE_KEY.PLAYERS],
        riichiStickValue: raw[WIRE_KEY.RIICHI_STICK_VALUE],
        seat: raw[WIRE_KEY.SEAT] ?? null,
        timer: raw[WIRE_KEY.TIMER_SETTINGS] ?? null,
        type: "game_started" as const,
    })),
);

export const roundStartedSchema = z.pipe(
    z
        .object({
            [WIRE_KEY.CURRENT_PLAYER]: seatSchema,
            [WIRE_KEY.DORA_INDICATORS]: z.array(tileIdSchema),
            [WIRE_KEY.DEALER]: seatSchema,
            [WIRE_KEY.HONBA]: z.int(),
            [WIRE_KEY.MY_TILES]: z.optional(z.array(tileIdSchema)),
            [WIRE_KEY.ROUND_NUMBER]: z.int(),
            [WIRE_KEY.PLAYERS]: z.array(playerViewSchema),
            [WIRE_KEY.RIICHI_STICKS]: z.int(),
            [WIRE_KEY.ROUND_IN_WIND]: roundInWindSchema,
            [WIRE_KEY.SEAT]: z.optional(seatSchema),
            [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.ROUND_STARTED),
            [WIRE_KEY.TILES_REMAINING]: tilesRemainingSchema,
            [WIRE_KEY.WIND]: z.int(),
        })
        .check(
            z.refine((raw) => coversEverySeat(raw[WIRE_KEY.PLAYERS]), {
                message: "the deal does not list each of the four seats once, in seat order",
            }),
        ),
    z.transform((raw) => ({
        currentPlayerSeat: raw[WIRE_KEY.CURRENT_PLAYER],
        dealerSeat: raw[WIRE_KEY.DEALER],
        doraIndicators: raw[WIRE_KEY.DORA_INDICATORS],
        honbaSticks: raw[WIRE_KEY.HONBA],
        myTiles: raw[WIRE_KEY.MY_TILES] ?? null,
        players: raw[WIRE_KEY.PLAYERS],
        riichiSticks: raw[WIRE_KEY.RIICHI_STICKS],
        roundInWind: raw[WIRE_KEY.ROUND_IN_WIND],
        roundNumber: raw[WIRE_KEY.ROUND_NUMBER],
        seat: raw[WIRE_KEY.SEAT] ?? null,
        tilesRemaining: raw[WIRE_KEY.TILES_REMAINING],
        type: "round_started" as const,
        wind: raw[WIRE_KEY.WIND],
    })),
);

export const drawSchema = z.pipe(
    z.object({
        [WIRE_KEY.AVAILABLE_ACTIONS]: z.optional(z.array(availableActionSchema)),
        [WIRE_KEY.BANK_SECONDS]: z.optional(secondsSchema),
        [WIRE_KEY.PACKED_MOVE]: z.int(),
        [WIRE_KEY.WAIT_ELAPSED]: z.optional(secondsSchema),
        [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.DRAW),
        [WIRE_KEY.TILES_REMAINING]: tilesRemainingSchema,
        [WIRE_KEY.WAIT_ID]: z.optional(waitIdSchema),
    }),
    z.transform((raw) => ({
        ...decodeDraw(raw[WIRE_KEY.PACKED_MOVE]),
        availableActions: raw[WIRE_KEY.AVAILABLE_ACTIONS] ?? [],
        bankSeconds: raw[WIRE_KEY.BANK_SECONDS] ?? null,
        elapsedSeconds: raw[WIRE_KEY.WAIT_ELAPSED] ?? null,
        tilesRemaining: raw[WIRE_KEY.TILES_REMAINING],
        type: "draw" as const,
        waitId: raw[WIRE_KEY.WAIT_ID] ?? null,
    })),
);

/**
 * Another seat's draw, told to every seat but the drawer's: its seat and the live wall left after it, the tile private
 * to the drawer.
 */
export const drawNoticeSchema = z.pipe(
    z.object({
        [WIRE_KEY.SEAT]: seatSchema,
        [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.DRAW_NOTICE),
        [WIRE_KEY.TILES_REMAINING]: tilesRemainingSchema,
    }),
    z.transform((raw) => ({
        seat: raw[WIRE_KEY.SEAT],
        tilesRemaining: raw[WIRE_KEY.TILES_REMAINING],
        type: "draw_notice" as const,
    })),
);

export const turnSchema = z.pipe(
    z.object({
        [WIRE_KEY.BANK_SECONDS]: z.optional(secondsSchema),
        [WIRE_KEY.WAIT_ELAPSED]: z.optional(secondsSchema),
        [WIRE_KEY.KUIKAE_TILES]: z.array(tileTypeSchema),
        [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.TURN),
        [WIRE_KEY.WAIT_ID]: z.optional(waitIdSchema),
    }),
    z.transform((raw) => ({
        bankSeconds: raw[WIRE_KEY.BANK_SECONDS] ?? null,
        elapsedSeconds: raw[WIRE_KEY.WAIT_ELAPSED] ?? null,
        kuikaeTileTypes: raw[WIRE_KEY.KUIKAE_TILES],
        type: "turn" as const,
        waitId: raw[WIRE_KEY.WAIT_ID] ?? null,
    })),
);

export const discardSchema = z.pipe(
    z.object({
        [WIRE_KEY.PACKED_MOVE]: z.int(),
        [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.DISCARD),
    }),
    z.transform((raw) => ({
        ...decodeDiscard(raw[WIRE_KEY.PACKED_MOVE]),
        type: "discard" as const,
    })),
);

export const meldSchema = z.pipe(
    z.object({
        [WIRE_KEY.PACKED_MELD]: compactMeldSchema,
        [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.MELD),
    }),
    z.transform((raw) => ({
        ...raw[WIRE_KEY.PACKED_MELD],
        type: "meld" as const,
    })),
);

/** An accepted riichi: the declarer's score after its deposit and the riichi sticks on the table with it. */
export const riichiDeclaredSchema = z.pipe(
    z.object({
        [WIRE_KEY.RIICHI_STICKS]: z.int().check(z.gte(1)),
        [WIRE_KEY.SEAT]: seatSchema,
        [WIRE_KEY.SCORE]: z.number(),
        [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.RIICHI_DECLARED),
    }),
    z.transform((raw) => ({
        riichiSticks: raw[WIRE_KEY.RIICHI_STICKS],
        score: raw[WIRE_KEY.SCORE] * WIRE_SCORE_DIVISOR,
        seat: raw[WIRE_KEY.SEAT],
        type: "riichi_declared" as const,
    })),
);

export const doraRevealedSchema = z.pipe(
    z.object({
        [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.DORA_REVEALED),
        [WIRE_KEY.TILE_ID]: tileIdSchema,
    }),
    z.transform((raw) => ({
        tileId: raw[WIRE_KEY.TILE_ID],
        type: "dora_revealed" as const,
    })),
);

/** A game error refusing the seat's action, named by the wait id that action echoed. */
export const errorEventSchema = z.pipe(
    z.object({
        [WIRE_KEY.GAME_ERROR_CODE]: z.string(),
        [WIRE_KEY.GAME_ERROR_MESSAGE]: z.string(),
        [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.ERROR),
        [WIRE_KEY.WAIT_ID]: z.optional(waitIdSchema),
    }),
    z.transform((raw) => ({
        code: raw[WIRE_KEY.GAME_ERROR_CODE],
        message: raw[WIRE_KEY.GAME_ERROR_MESSAGE],
        type: "error" as const,
        waitId: raw[WIRE_KEY.WAIT_ID] ?? null,
    })),
);

export const furitenSchema = z.pipe(
    z.object({
        [WIRE_KEY.FURITEN]: z.boolean(),
        [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.FURITEN),
    }),
    z.transform((raw) => ({
        isFuriten: raw[WIRE_KEY.FURITEN],
        type: "furiten" as const,
    })),
);

export const gameEndSchema = z.pipe(
    z
        .object({
            [WIRE_KEY.END_CAUSE]: z.enum(GAME_END_CAUSE),
            [WIRE_KEY.LEFTOVER_BONUS]: wireScoreSchema,
            [WIRE_KEY.LEFTOVER_RIICHI]: z.int().check(z.gte(0)),
            [WIRE_KEY.ROUND_COUNT]: z.int(),
            [WIRE_KEY.STANDINGS]: z.array(playerStandingSchema),
            [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.GAME_END),
            [WIRE_KEY.WINNER_SEAT]: seatSchema,
        })
        .check(
            z.refine(
                (raw) =>
                    raw[WIRE_KEY.STANDINGS].length === NUM_PLAYERS &&
                    namesDistinctSeats(raw[WIRE_KEY.STANDINGS].map((standing) => standing.seat)),
                { message: "the standings do not rank each of the four seats once" },
            ),
        ),
    z.transform((raw) => ({
        endCause: raw[WIRE_KEY.END_CAUSE],
        leftoverRiichiBonus: raw[WIRE_KEY.LEFTOVER_BONUS],
        leftoverRiichiSticks: raw[WIRE_KEY.LEFTOVER_RIICHI],
        numRounds: raw[WIRE_KEY.ROUND_COUNT],
        standings: raw[WIRE_KEY.STANDINGS],
        type: "game_end" as const,
        winnerSeat: raw[WIRE_KEY.WINNER_SEAT],
    })),
);
