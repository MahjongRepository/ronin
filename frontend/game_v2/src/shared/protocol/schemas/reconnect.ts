import { z } from "zod/mini";

import {
    ABORTIVE_DRAW_TYPE,
    ROUND_RESULT_TYPE,
    SESSION_MESSAGE_TYPE,
    WIRE_SCORE_DIVISOR,
} from "@/shared/protocol/constants";
import { WIRE_KEY } from "@/shared/protocol/wire-keys";

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
import { type RoundEndEvent, parseRoundResult } from "./round-results";

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
            [WIRE_KEY.DISCARDS]: z.array(discardInfoSchema),
            [WIRE_KEY.MELDS]: z.array(compactMeldSchema),
            [WIRE_KEY.IS_RIICHI]: z.boolean(),
            [WIRE_KEY.SEAT]: seatSchema,
            [WIRE_KEY.SCORE]: z.number(),
            [WIRE_KEY.TILE_COUNT]: z.int().check(z.gte(0)),
        })
        .check(
            z.refine((raw) => calledBy(raw[WIRE_KEY.MELDS], raw[WIRE_KEY.SEAT]), {
                message: "a seat's state lists a meld another seat called",
            }),
            z.refine((raw) => isHandCount(raw[WIRE_KEY.TILE_COUNT], raw[WIRE_KEY.MELDS].length), {
                message: "a seat's state holds a closed hand no turn leaves beside its melds",
            }),
        ),
    z.transform((raw) => ({
        discards: raw[WIRE_KEY.DISCARDS],
        isRiichi: raw[WIRE_KEY.IS_RIICHI],
        melds: raw[WIRE_KEY.MELDS],
        score: raw[WIRE_KEY.SCORE] * WIRE_SCORE_DIVISOR,
        seat: raw[WIRE_KEY.SEAT],
        tileCount: raw[WIRE_KEY.TILE_COUNT],
    })),
);

const roundHistoryEntrySchema = z.pipe(
    z.object({
        [WIRE_KEY.DEALER]: seatSchema,
        [WIRE_KEY.HONBA]: z.int(),
        [WIRE_KEY.LOSER_SEAT]: z.optional(seatSchema),
        [WIRE_KEY.PAO_SEAT]: z.array(seatSchema),
        [WIRE_KEY.ABORTIVE_REASON]: z.optional(z.enum(ABORTIVE_DRAW_TYPE)),
        [WIRE_KEY.RIICHI_SEATS]: z.array(seatSchema),
        [WIRE_KEY.RESULT_TYPE]: z.enum(ROUND_RESULT_TYPE),
        [WIRE_KEY.SCORE_CHANGES]: wireScoreMapSchema,
        [WIRE_KEY.TENPAI_SEATS]: z.optional(z.array(seatSchema)),
        [WIRE_KEY.WIND]: z.int(),
        [WIRE_KEY.WINNER_SEAT]: z.array(seatSchema),
    }),
    z.transform((raw) => ({
        abortiveReason: raw[WIRE_KEY.ABORTIVE_REASON] ?? null,
        dealerSeat: raw[WIRE_KEY.DEALER],
        honbaSticks: raw[WIRE_KEY.HONBA],
        loserSeat: raw[WIRE_KEY.LOSER_SEAT] ?? null,
        paoSeats: raw[WIRE_KEY.PAO_SEAT],
        resultType: raw[WIRE_KEY.RESULT_TYPE],
        riichiSeats: raw[WIRE_KEY.RIICHI_SEATS],
        scoreChanges: raw[WIRE_KEY.SCORE_CHANGES],
        tenpaiSeats: raw[WIRE_KEY.TENPAI_SEATS] ?? null,
        wind: raw[WIRE_KEY.WIND],
        winnerSeats: raw[WIRE_KEY.WINNER_SEAT],
    })),
);

// --- Game reconnected ---

interface SnapshotWhole {
    readonly [WIRE_KEY.MY_TILES]: readonly number[];
    readonly [WIRE_KEY.ROUND_NUMBER]: number;
    readonly [WIRE_KEY.PLAYERS]: readonly { readonly seat: number }[];
    readonly [WIRE_KEY.PLAYER_STATES]: readonly {
        readonly seat: number;
        readonly tileCount: number;
    }[];
    readonly [WIRE_KEY.ROUND_RESULT]?: unknown;
    readonly [WIRE_KEY.ROUND_HISTORY]: readonly unknown[];
    readonly [WIRE_KEY.SEAT]: number;
}

/** Whether the viewer's own tiles are its whole closed hand: as many as its seat's count, each tile once. */
function holdsOwnHand(raw: SnapshotWhole): boolean {
    return (
        raw[WIRE_KEY.MY_TILES].length ===
            raw[WIRE_KEY.PLAYER_STATES][raw[WIRE_KEY.SEAT]].tileCount &&
        new Set(raw[WIRE_KEY.MY_TILES]).size === raw[WIRE_KEY.MY_TILES].length
    );
}

/**
 * A snapshot whole enough to rebuild the table from it alone: every seat's player and state, the viewer's whole hand,
 * and the round history's every finished round, one per deal before the one it shows (`WIRE_KEY.ROUND_NUMBER` counts the deals) and that
 * one too once it ended. A snapshot lacking any of them is refused rather than made whole with a guess.
 */
function isComplete(raw: SnapshotWhole): boolean {
    const finished =
        raw[WIRE_KEY.ROUND_NUMBER] + (raw[WIRE_KEY.ROUND_RESULT] === undefined ? 0 : 1);
    return (
        coversEverySeat(raw[WIRE_KEY.PLAYERS]) &&
        coversEverySeat(raw[WIRE_KEY.PLAYER_STATES]) &&
        holdsOwnHand(raw) &&
        raw[WIRE_KEY.ROUND_HISTORY].length === finished
    );
}

/**
 * The round advance timer of a snapshot that owes the confirm while the seat's timer runs: how long it has run (`WIRE_KEY.WAIT_ELAPSED`)
 * and its whole timeout (`WIRE_KEY.ROUND_ADVANCE_SECONDS`), which the server names together, or neither.
 */
function advanceTimerOf(raw: {
    readonly [WIRE_KEY.ROUND_ADVANCE_SECONDS]?: number;
    readonly [WIRE_KEY.WAIT_ELAPSED]?: number;
}): { readonly elapsedSeconds: number; readonly seconds: number } | null {
    const seconds = raw[WIRE_KEY.ROUND_ADVANCE_SECONDS];
    const elapsedSeconds = raw[WIRE_KEY.WAIT_ELAPSED];
    return seconds === undefined || elapsedSeconds === undefined
        ? null
        : { elapsedSeconds, seconds };
}

export const gameReconnectedSchema = z.pipe(
    z
        .object({
            [WIRE_KEY.ROUND_ADVANCE_SECONDS]: z.optional(secondsSchema),
            [WIRE_KEY.CURRENT_PLAYER]: seatSchema,
            [WIRE_KEY.DEALER_DICE]: z.tuple([
                z.tuple([z.number(), z.number()]),
                z.tuple([z.number(), z.number()]),
            ]),
            [WIRE_KEY.DORA_INDICATORS]: z.array(tileIdSchema),
            [WIRE_KEY.DEALER]: seatSchema,
            [WIRE_KEY.WAIT_ELAPSED]: z.optional(secondsSchema),
            [WIRE_KEY.FURITEN]: z.boolean(),
            [WIRE_KEY.FIRST_DEALER]: seatSchema,
            [WIRE_KEY.GAME_ID]: z.string(),
            [WIRE_KEY.HONBA]: z.int(),
            [WIRE_KEY.LATEST_DISCARD_SEAT]: z.optional(seatSchema),
            [WIRE_KEY.MY_TILES]: z.array(tileIdSchema),
            [WIRE_KEY.ROUND_NUMBER]: z.int(),
            [WIRE_KEY.CONFIRMATION_OWED]: z.optional(z.boolean()),
            [WIRE_KEY.PLAYERS]: z.array(gamePlayerInfoSchema),
            [WIRE_KEY.PLAYER_STATES]: z.array(playerReconnectStateSchema),
            [WIRE_KEY.RIICHI_STICKS]: z.int(),
            [WIRE_KEY.ROUND_RESULT]: z.optional(z.record(z.string(), z.unknown())),
            [WIRE_KEY.ROUND_HISTORY]: z.array(roundHistoryEntrySchema),
            [WIRE_KEY.RIICHI_STICK_VALUE]: wireSettingAmountSchema,
            [WIRE_KEY.ROUND_IN_WIND]: roundInWindSchema,
            [WIRE_KEY.SEAT]: seatSchema,
            [WIRE_KEY.TIMER_SETTINGS]: timerSettingsSchema,
            [WIRE_KEY.TILES_REMAINING]: tilesRemainingSchema,
            [WIRE_KEY.SESSION_TYPE]: z.literal(SESSION_MESSAGE_TYPE.GAME_RECONNECTED),
            [WIRE_KEY.WIND]: z.int(),
            [WIRE_KEY.WAIT_ID]: waitIdSchema,
        })
        .check(
            z.refine(isComplete, {
                message:
                    "the snapshot lacks a seat's player or state, or a finished round of its history",
            }),
            z.refine(
                (raw) =>
                    (raw[WIRE_KEY.ROUND_ADVANCE_SECONDS] === undefined) ===
                    (raw[WIRE_KEY.WAIT_ELAPSED] === undefined),
                {
                    message:
                        "the snapshot names its round advance's elapsed time without its timeout, or its timeout without it",
                },
            ),
        ),
    z.transform((raw) => ({
        advanceTimer: advanceTimerOf(raw),
        confirmationOwed: raw[WIRE_KEY.CONFIRMATION_OWED] ?? false,
        currentPlayerSeat: raw[WIRE_KEY.CURRENT_PLAYER],
        dealerDice: raw[WIRE_KEY.DEALER_DICE],
        dealerSeat: raw[WIRE_KEY.DEALER],
        doraIndicators: raw[WIRE_KEY.DORA_INDICATORS],
        firstDealerSeat: raw[WIRE_KEY.FIRST_DEALER],
        gameId: raw[WIRE_KEY.GAME_ID],
        honbaSticks: raw[WIRE_KEY.HONBA],
        isFuriten: raw[WIRE_KEY.FURITEN],
        latestDiscardSeat: raw[WIRE_KEY.LATEST_DISCARD_SEAT] ?? null,
        myTiles: raw[WIRE_KEY.MY_TILES],
        playerStates: raw[WIRE_KEY.PLAYER_STATES],
        players: raw[WIRE_KEY.PLAYERS],
        riichiStickValue: raw[WIRE_KEY.RIICHI_STICK_VALUE],
        riichiSticks: raw[WIRE_KEY.RIICHI_STICKS],
        roundHistory: raw[WIRE_KEY.ROUND_HISTORY],
        roundInWind: raw[WIRE_KEY.ROUND_IN_WIND],
        roundNumber: raw[WIRE_KEY.ROUND_NUMBER],
        roundResult: parseSnapshotRoundResult(raw[WIRE_KEY.ROUND_RESULT]),
        seat: raw[WIRE_KEY.SEAT],
        tilesRemaining: raw[WIRE_KEY.TILES_REMAINING],
        timer: raw[WIRE_KEY.TIMER_SETTINGS],
        type: "game_reconnected" as const,
        waitId: raw[WIRE_KEY.WAIT_ID],
        wind: raw[WIRE_KEY.WIND],
    })),
);

export type GameReconnectedEvent = z.output<typeof gameReconnectedSchema>;

function parseSnapshotRoundResult(raw: Record<string, unknown> | undefined): RoundEndEvent | null {
    return raw === undefined ? null : parseRoundResult(raw);
}
