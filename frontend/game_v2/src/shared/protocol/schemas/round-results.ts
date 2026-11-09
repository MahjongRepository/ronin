import { z } from "zod/mini";

import {
    ABORTIVE_DRAW_TYPE,
    EVENT_TYPE,
    KAN_TYPE,
    PAO_SHARE,
    ROUND_RESULT_TYPE,
} from "@/shared/protocol/constants";
import { WIRE_KEY } from "@/shared/protocol/wire-keys";

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
 * The round advance a live round end opens: its wait id (`WIRE_KEY.WAIT_ID`) and the advance's whole timeout (`WIRE_KEY.ROUND_ADVANCE_SECONDS`, seconds), which
 * the server names together; the game's last round end and a replay's name neither.
 */
const roundAdvanceShape = {
    [WIRE_KEY.ROUND_ADVANCE_SECONDS]: z.optional(secondsSchema),
    [WIRE_KEY.WAIT_ID]: z.optional(waitIdSchema),
};

/**
 * Every round end names the riichi sticks its result leaves on the table (`WIRE_KEY.RIICHI_STICKS`) and its round's dealer (`WIRE_KEY.DEALER`) and
 * revealed dora indicators (`WIRE_KEY.DORA_INDICATORS`), beside its round advance, so the result never reads them from the client's table.
 */
const roundEndShape = {
    ...roundAdvanceShape,
    [WIRE_KEY.DORA_INDICATORS]: z.array(tileIdSchema),
    [WIRE_KEY.DEALER]: seatSchema,
    [WIRE_KEY.RIICHI_STICKS]: z.int().check(z.gte(0)),
};

const roundAdvanceWaitSchema = z.object(roundAdvanceShape).check(
    z.refine(
        (raw) =>
            (raw[WIRE_KEY.ROUND_ADVANCE_SECONDS] === undefined) ===
            (raw[WIRE_KEY.WAIT_ID] === undefined),
        {
            message:
                "a round end names its round advance's wait without its timeout, or its timeout without its wait",
        },
    ),
);

interface RoundAdvance {
    /** How long the server's round advance timer waits from the round end, over every result it shows. */
    readonly seconds: number;
    readonly waitId: number;
}

function roundAdvanceOf(raw: {
    [WIRE_KEY.ROUND_ADVANCE_SECONDS]?: number;
    [WIRE_KEY.WAIT_ID]?: number;
}): RoundAdvance | null {
    const seconds = raw[WIRE_KEY.ROUND_ADVANCE_SECONDS];
    const waitId = raw[WIRE_KEY.WAIT_ID];
    return seconds === undefined || waitId === undefined ? null : { seconds, waitId };
}

const tenpaiHandSchema = z.pipe(
    z
        .object({
            [WIRE_KEY.CLOSED_TILES]: z.array(tileIdSchema),
            [WIRE_KEY.MELDS]: z.array(compactMeldSchema),
            [WIRE_KEY.SEAT]: seatSchema,
        })
        .check(
            z.refine((raw) => calledBy(raw[WIRE_KEY.MELDS], raw[WIRE_KEY.SEAT]), {
                message: "a tenpai hand lists a meld another seat called",
            }),
        ),
    z.transform((raw) => ({
        closedTiles: raw[WIRE_KEY.CLOSED_TILES],
        melds: raw[WIRE_KEY.MELDS],
        seat: raw[WIRE_KEY.SEAT],
    })),
);

const robbedKanSchema = z.pipe(
    z.object({
        [WIRE_KEY.KAN_TYPE]: z.union([z.literal(KAN_TYPE.ADDED), z.literal(KAN_TYPE.CLOSED)]),
        [WIRE_KEY.SEAT]: seatSchema,
        [WIRE_KEY.TILE_ID]: tileIdSchema,
    }),
    z.transform((raw) => ({
        kanType: raw[WIRE_KEY.KAN_TYPE],
        seat: raw[WIRE_KEY.SEAT],
        tileId: raw[WIRE_KEY.TILE_ID],
    })),
);

const paoLiabilitySchema = z.object({
    [WIRE_KEY.PAYS_HONBA]: z.boolean(),
    [WIRE_KEY.PAO_SHARE]: z.enum(PAO_SHARE),
    [WIRE_KEY.YAKU]: z.array(z.int()).check(z.minLength(1)),
});

/**
 * A winner's honba bonus (`WIRE_KEY.HONBA_BONUS`) and, with a liable seat (`WIRE_KEY.PAO_SEAT`), what that seat pays (`WIRE_KEY.PAO_LIABILITY`): the pao yakuman that made it liable,
 * all or half of the whole hand, and whether it pays the honba too. The server names the seat and its liability together.
 */
const winnerPaymentShape = {
    [WIRE_KEY.HONBA_BONUS]: wireScoreSchema,
    [WIRE_KEY.PAO_LIABILITY]: z.optional(paoLiabilitySchema),
    [WIRE_KEY.PAO_SEAT]: z.optional(seatSchema),
};

function namesPaoWhole(raw: {
    readonly [WIRE_KEY.PAO_LIABILITY]?: unknown;
    readonly [WIRE_KEY.PAO_SEAT]?: unknown;
}): boolean {
    return (raw[WIRE_KEY.PAO_LIABILITY] === undefined) === (raw[WIRE_KEY.PAO_SEAT] === undefined);
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
    readonly [WIRE_KEY.PAO_LIABILITY]?: z.output<typeof paoLiabilitySchema>;
    readonly [WIRE_KEY.PAO_SEAT]?: number;
}): PaoLiability | null {
    const seat = raw[WIRE_KEY.PAO_SEAT];
    const liability = raw[WIRE_KEY.PAO_LIABILITY];
    return seat === undefined || liability === undefined
        ? null
        : {
              paysHonba: liability[WIRE_KEY.PAYS_HONBA],
              seat,
              share: liability[WIRE_KEY.PAO_SHARE],
              yakuIds: liability[WIRE_KEY.YAKU],
          };
}

const doubleRonWinnerSchema = z.pipe(
    z
        .object({
            [WIRE_KEY.CLOSED_TILES]: z.array(tileIdSchema),
            [WIRE_KEY.HAND_RESULT]: handResultSchema,
            [WIRE_KEY.MELDS]: z.array(compactMeldSchema),
            [WIRE_KEY.RIICHI_COLLECTED]: z.int(),
            [WIRE_KEY.SCORE_CHANGES]: wireScoreMapSchema,
            [WIRE_KEY.URA_DORA]: z.optional(z.array(tileIdSchema)),
            ...winnerPaymentShape,
            [WIRE_KEY.WINNER_SEAT]: seatSchema,
        })
        .check(
            z.refine((raw) => calledBy(raw[WIRE_KEY.MELDS], raw[WIRE_KEY.WINNER_SEAT]), {
                message: "a winner's hand lists a meld another seat called",
            }),
            z.refine(namesPaoWhole, PAO_NAMED_PARTLY),
        ),
    z.transform((raw) => ({
        closedTiles: raw[WIRE_KEY.CLOSED_TILES],
        handResult: raw[WIRE_KEY.HAND_RESULT],
        honbaBonus: raw[WIRE_KEY.HONBA_BONUS],
        melds: raw[WIRE_KEY.MELDS],
        pao: paoOf(raw),
        riichiSticksCollected: raw[WIRE_KEY.RIICHI_COLLECTED],
        scoreChanges: raw[WIRE_KEY.SCORE_CHANGES],
        uraDoraIndicators: raw[WIRE_KEY.URA_DORA] ?? null,
        winnerSeat: raw[WIRE_KEY.WINNER_SEAT],
    })),
);

const tsumoSchema = z.pipe(
    z
        .object({
            [WIRE_KEY.CLOSED_TILES]: z.array(tileIdSchema),
            [WIRE_KEY.HAND_RESULT]: handResultSchema,
            [WIRE_KEY.MELDS]: z.array(compactMeldSchema),
            [WIRE_KEY.RIICHI_COLLECTED]: z.int(),
            [WIRE_KEY.RESULT_TYPE]: z.literal(ROUND_RESULT_TYPE.TSUMO),
            [WIRE_KEY.SCORE_CHANGES]: wireScoreMapSchema,
            [WIRE_KEY.SCORES]: wireScoreMapSchema,
            [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.ROUND_END),
            [WIRE_KEY.URA_DORA]: z.optional(z.array(tileIdSchema)),
            ...roundEndShape,
            ...winnerPaymentShape,
            [WIRE_KEY.WINNER_SEAT]: seatSchema,
            [WIRE_KEY.WINNING_TILE]: tileIdSchema,
        })
        .check(
            z.refine((raw) => calledBy(raw[WIRE_KEY.MELDS], raw[WIRE_KEY.WINNER_SEAT]), {
                message: "a winner's hand lists a meld another seat called",
            }),
            z.refine(namesPaoWhole, PAO_NAMED_PARTLY),
        ),
    z.transform((raw) => ({
        closedTiles: raw[WIRE_KEY.CLOSED_TILES],
        dealerSeat: raw[WIRE_KEY.DEALER],
        doraIndicators: raw[WIRE_KEY.DORA_INDICATORS],
        handResult: raw[WIRE_KEY.HAND_RESULT],
        honbaBonus: raw[WIRE_KEY.HONBA_BONUS],
        melds: raw[WIRE_KEY.MELDS],
        pao: paoOf(raw),
        resultType: ROUND_RESULT_TYPE.TSUMO as typeof ROUND_RESULT_TYPE.TSUMO,
        riichiSticks: raw[WIRE_KEY.RIICHI_STICKS],
        riichiSticksCollected: raw[WIRE_KEY.RIICHI_COLLECTED],
        roundAdvance: roundAdvanceOf(raw),
        scoreChanges: raw[WIRE_KEY.SCORE_CHANGES],
        scores: raw[WIRE_KEY.SCORES],
        type: "round_end" as const,
        uraDoraIndicators: raw[WIRE_KEY.URA_DORA] ?? null,
        winnerSeat: raw[WIRE_KEY.WINNER_SEAT],
        winningTile: raw[WIRE_KEY.WINNING_TILE],
    })),
);

const ronSchema = z.pipe(
    z
        .object({
            [WIRE_KEY.CLOSED_TILES]: z.array(tileIdSchema),
            [WIRE_KEY.HEAD_BUMPED_SEATS]: z.optional(z.array(seatSchema)),
            [WIRE_KEY.HAND_RESULT]: handResultSchema,
            [WIRE_KEY.LOSER_SEAT]: seatSchema,
            [WIRE_KEY.MELDS]: z.array(compactMeldSchema),
            [WIRE_KEY.RIICHI_COLLECTED]: z.int(),
            [WIRE_KEY.ROBBED_KAN]: z.optional(robbedKanSchema),
            [WIRE_KEY.RESULT_TYPE]: z.literal(ROUND_RESULT_TYPE.RON),
            [WIRE_KEY.SCORE_CHANGES]: wireScoreMapSchema,
            [WIRE_KEY.SCORES]: wireScoreMapSchema,
            [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.ROUND_END),
            [WIRE_KEY.URA_DORA]: z.optional(z.array(tileIdSchema)),
            ...roundEndShape,
            ...winnerPaymentShape,
            [WIRE_KEY.WINNER_SEAT]: seatSchema,
            [WIRE_KEY.WINNING_TILE]: tileIdSchema,
        })
        .check(
            z.refine((raw) => calledBy(raw[WIRE_KEY.MELDS], raw[WIRE_KEY.WINNER_SEAT]), {
                message: "a winner's hand lists a meld another seat called",
            }),
            z.refine(namesPaoWhole, PAO_NAMED_PARTLY),
        ),
    z.transform((raw) => ({
        closedTiles: raw[WIRE_KEY.CLOSED_TILES],
        dealerSeat: raw[WIRE_KEY.DEALER],
        doraIndicators: raw[WIRE_KEY.DORA_INDICATORS],
        handResult: raw[WIRE_KEY.HAND_RESULT],
        headBumpedSeats: raw[WIRE_KEY.HEAD_BUMPED_SEATS] ?? [],
        honbaBonus: raw[WIRE_KEY.HONBA_BONUS],
        loserSeat: raw[WIRE_KEY.LOSER_SEAT],
        melds: raw[WIRE_KEY.MELDS],
        pao: paoOf(raw),
        resultType: ROUND_RESULT_TYPE.RON as typeof ROUND_RESULT_TYPE.RON,
        riichiSticks: raw[WIRE_KEY.RIICHI_STICKS],
        riichiSticksCollected: raw[WIRE_KEY.RIICHI_COLLECTED],
        robbedKan: raw[WIRE_KEY.ROBBED_KAN] ?? null,
        roundAdvance: roundAdvanceOf(raw),
        scoreChanges: raw[WIRE_KEY.SCORE_CHANGES],
        scores: raw[WIRE_KEY.SCORES],
        type: "round_end" as const,
        uraDoraIndicators: raw[WIRE_KEY.URA_DORA] ?? null,
        winnerSeat: raw[WIRE_KEY.WINNER_SEAT],
        winningTile: raw[WIRE_KEY.WINNING_TILE],
    })),
);

const doubleRonSchema = z.pipe(
    z
        .object({
            [WIRE_KEY.HEAD_BUMPED_SEATS]: z.optional(z.array(seatSchema)),
            [WIRE_KEY.LOSER_SEAT]: seatSchema,
            [WIRE_KEY.ROBBED_KAN]: z.optional(robbedKanSchema),
            [WIRE_KEY.RESULT_TYPE]: z.literal(ROUND_RESULT_TYPE.DOUBLE_RON),
            [WIRE_KEY.SCORE_CHANGES]: wireScoreMapSchema,
            [WIRE_KEY.SCORES]: wireScoreMapSchema,
            [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.ROUND_END),
            ...roundEndShape,
            [WIRE_KEY.WINNERS]: z.array(doubleRonWinnerSchema),
            [WIRE_KEY.WINNING_TILE]: tileIdSchema,
        })
        .check(
            z.refine(
                (raw) =>
                    raw[WIRE_KEY.WINNERS].length >= MIN_DOUBLE_RON_WINNERS &&
                    namesDistinctSeats(raw[WIRE_KEY.WINNERS].map((winner) => winner.winnerSeat)),
                { message: "the double ron does not name at least two distinct winners" },
            ),
        ),
    z.transform((raw) => ({
        dealerSeat: raw[WIRE_KEY.DEALER],
        doraIndicators: raw[WIRE_KEY.DORA_INDICATORS],
        headBumpedSeats: raw[WIRE_KEY.HEAD_BUMPED_SEATS] ?? [],
        loserSeat: raw[WIRE_KEY.LOSER_SEAT],
        resultType: ROUND_RESULT_TYPE.DOUBLE_RON as typeof ROUND_RESULT_TYPE.DOUBLE_RON,
        riichiSticks: raw[WIRE_KEY.RIICHI_STICKS],
        robbedKan: raw[WIRE_KEY.ROBBED_KAN] ?? null,
        roundAdvance: roundAdvanceOf(raw),
        scoreChanges: raw[WIRE_KEY.SCORE_CHANGES],
        scores: raw[WIRE_KEY.SCORES],
        type: "round_end" as const,
        winners: raw[WIRE_KEY.WINNERS],
        winningTile: raw[WIRE_KEY.WINNING_TILE],
    })),
);

const exhaustiveDrawSchema = z.pipe(
    z.object({
        [WIRE_KEY.NOTEN_SEATS]: z.array(seatSchema),
        [WIRE_KEY.RESULT_TYPE]: z.literal(ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW),
        [WIRE_KEY.SCORE_CHANGES]: wireScoreMapSchema,
        [WIRE_KEY.SCORES]: wireScoreMapSchema,
        [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.ROUND_END),
        [WIRE_KEY.TENPAI_HANDS]: z.array(tenpaiHandSchema),
        [WIRE_KEY.TENPAI_SEATS]: z.array(seatSchema),
        ...roundEndShape,
    }),
    z.transform((raw) => ({
        dealerSeat: raw[WIRE_KEY.DEALER],
        doraIndicators: raw[WIRE_KEY.DORA_INDICATORS],
        notenSeats: raw[WIRE_KEY.NOTEN_SEATS],
        resultType: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW as typeof ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
        riichiSticks: raw[WIRE_KEY.RIICHI_STICKS],
        roundAdvance: roundAdvanceOf(raw),
        scoreChanges: raw[WIRE_KEY.SCORE_CHANGES],
        scores: raw[WIRE_KEY.SCORES],
        tenpaiHands: raw[WIRE_KEY.TENPAI_HANDS],
        tenpaiSeats: raw[WIRE_KEY.TENPAI_SEATS],
        type: "round_end" as const,
    })),
);

const abortiveDrawSchema = z.pipe(
    z.object({
        [WIRE_KEY.RON_CALLERS]: z.optional(z.array(seatSchema)),
        [WIRE_KEY.ROBBED_KAN]: z.optional(robbedKanSchema),
        [WIRE_KEY.ABORTIVE_REASON]: z.enum(ABORTIVE_DRAW_TYPE),
        [WIRE_KEY.RESULT_TYPE]: z.literal(ROUND_RESULT_TYPE.ABORTIVE_DRAW),
        [WIRE_KEY.SEAT]: z.optional(seatSchema),
        [WIRE_KEY.SCORE_CHANGES]: wireScoreMapSchema,
        [WIRE_KEY.SCORES]: wireScoreMapSchema,
        [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.ROUND_END),
        ...roundEndShape,
    }),
    z.transform((raw) => ({
        dealerSeat: raw[WIRE_KEY.DEALER],
        doraIndicators: raw[WIRE_KEY.DORA_INDICATORS],
        reason: raw[WIRE_KEY.ABORTIVE_REASON],
        resultType: ROUND_RESULT_TYPE.ABORTIVE_DRAW as typeof ROUND_RESULT_TYPE.ABORTIVE_DRAW,
        riichiSticks: raw[WIRE_KEY.RIICHI_STICKS],
        robbedKan: raw[WIRE_KEY.ROBBED_KAN] ?? null,
        ronSeats: raw[WIRE_KEY.RON_CALLERS] ?? [],
        roundAdvance: roundAdvanceOf(raw),
        scoreChanges: raw[WIRE_KEY.SCORE_CHANGES],
        scores: raw[WIRE_KEY.SCORES],
        seat: raw[WIRE_KEY.SEAT] ?? null,
        type: "round_end" as const,
    })),
);

const nagashiRiverSchema = z.pipe(
    z.object({
        [WIRE_KEY.DISCARDS]: z.array(discardInfoSchema).check(z.minLength(1)),
        [WIRE_KEY.SEAT]: seatSchema,
    }),
    z.transform((raw) => ({ discards: raw[WIRE_KEY.DISCARDS], seat: raw[WIRE_KEY.SEAT] })),
);

/** A nagashi mangan names each qualifying seat's river (`WIRE_KEY.QUALIFYING_RIVERS`), its proof, in the order of the seats (`WIRE_KEY.QUALIFYING_SEATS`). */
const nagashiManganSchema = z.pipe(
    z
        .object({
            [WIRE_KEY.NOTEN_SEATS]: z.array(seatSchema),
            [WIRE_KEY.QUALIFYING_RIVERS]: z.array(nagashiRiverSchema),
            [WIRE_KEY.QUALIFYING_SEATS]: z.array(seatSchema).check(z.minLength(1)),
            [WIRE_KEY.RESULT_TYPE]: z.literal(ROUND_RESULT_TYPE.NAGASHI_MANGAN),
            [WIRE_KEY.SCORE_CHANGES]: wireScoreMapSchema,
            [WIRE_KEY.SCORES]: wireScoreMapSchema,
            [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.ROUND_END),
            [WIRE_KEY.TENPAI_HANDS]: z.array(tenpaiHandSchema),
            [WIRE_KEY.TENPAI_SEATS]: z.array(seatSchema),
            ...roundEndShape,
        })
        .check(
            z.refine(
                (raw) =>
                    raw[WIRE_KEY.QUALIFYING_RIVERS].length ===
                        raw[WIRE_KEY.QUALIFYING_SEATS].length &&
                    raw[WIRE_KEY.QUALIFYING_RIVERS].every(
                        (river, index) => river.seat === raw[WIRE_KEY.QUALIFYING_SEATS][index],
                    ),
                {
                    message:
                        "a nagashi mangan does not name the river of each qualifying seat, in order",
                },
            ),
        ),
    z.transform((raw) => ({
        dealerSeat: raw[WIRE_KEY.DEALER],
        doraIndicators: raw[WIRE_KEY.DORA_INDICATORS],
        notenSeats: raw[WIRE_KEY.NOTEN_SEATS],
        qualifyingRivers: raw[WIRE_KEY.QUALIFYING_RIVERS],
        qualifyingSeats: raw[WIRE_KEY.QUALIFYING_SEATS],
        resultType: ROUND_RESULT_TYPE.NAGASHI_MANGAN as typeof ROUND_RESULT_TYPE.NAGASHI_MANGAN,
        riichiSticks: raw[WIRE_KEY.RIICHI_STICKS],
        roundAdvance: roundAdvanceOf(raw),
        scoreChanges: raw[WIRE_KEY.SCORE_CHANGES],
        scores: raw[WIRE_KEY.SCORES],
        tenpaiHands: raw[WIRE_KEY.TENPAI_HANDS],
        tenpaiSeats: raw[WIRE_KEY.TENPAI_SEATS],
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

/** Dispatch on `WIRE_KEY.RESULT_TYPE` by hand: Zod's discriminatedUnion does not work with `.transform()`. */
export function parseRoundEnd(raw: Record<string, unknown>): RoundEndEvent {
    roundAdvanceWaitSchema.parse(raw);
    const { [WIRE_KEY.RESULT_TYPE]: rt } = raw;
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
            throw new Error(`Unknown round result type: RESULT_TYPE=${String(rt)}`);
        }
    }
}

/** Parse a round result carried without its event type, as the reconnect snapshot's `WIRE_KEY.ROUND_RESULT`. */
export function parseRoundResult(raw: Record<string, unknown>): RoundEndEvent {
    return parseRoundEnd({ ...raw, [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END });
}
