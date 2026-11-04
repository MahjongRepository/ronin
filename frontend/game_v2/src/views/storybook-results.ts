import {
    type PlayerState,
    type RoundEndResult,
    createInitialPlayerState,
    extractRoundEndResult,
    seatEntry,
} from "@/entities/table";
import { WIRE_KEY, parseRoundEnd } from "@/shared/protocol";

interface ResultSource {
    /** The generated replay fixture (`src/fixtures/replays/`) whose round end this is. */
    readonly fixture: string;
    readonly key: string;
    readonly label: string;
    readonly names: readonly string[];
    /** The riichi stick value its fixture's recorded settings (`gs`) name. */
    readonly riichiStickValue: number;
    /** The round end's wire line as the fixture records it. */
    readonly roundEnd: Readonly<Record<number, unknown>>;
}

/**
 * The round results the board storybook shows over its board: each the wire round end of a generated replay fixture,
 * with the names of its round and its game's riichi stick value, parsed and read as the table reads it. A copy, so the storybook's chunk carries one line of each fixture rather than the whole file; a test
 * fails when a copy no longer reads as its fixture's round end does.
 */
const RESULT_SOURCES = [
    {
        fixture: "riichi",
        key: "tsumo",
        label: "Tsumo",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 0,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [109],
            [WIRE_KEY.WINNER_SEAT]: 1,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.HAN]: 5,
                [WIRE_KEY.FU]: 20,
                [WIRE_KEY.YAKU]: [
                    { [WIRE_KEY.YAKU_ID]: 0, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 1, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 12, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    {
                        [WIRE_KEY.YAKU_ID]: 121,
                        [WIRE_KEY.HAN]: 1,
                        [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                    },
                    {
                        [WIRE_KEY.YAKU_ID]: 122,
                        [WIRE_KEY.HAN]: 1,
                        [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                    },
                ],
                [WIRE_KEY.POINTS]: 80,
                [WIRE_KEY.HAND_LIMIT]: "mangan",
            },
            [WIRE_KEY.SCORES]: { "0": 250, "1": 240, "2": 250, "3": 240 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": -40, "1": 100, "2": -20, "3": -20 },
            [WIRE_KEY.RIICHI_COLLECTED]: 2,
            [WIRE_KEY.CLOSED_TILES]: [0, 4, 8, 48, 52, 56, 60, 64, 68, 80, 84, 104, 105],
            [WIRE_KEY.MELDS]: [],
            [WIRE_KEY.WINNING_TILE]: 89,
            [WIRE_KEY.HONBA_BONUS]: 0,
            [WIRE_KEY.URA_DORA]: [65],
        },
    },
    {
        fixture: "ron_riichi_discard",
        key: "ron",
        label: "Ron",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 1,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [120],
            [WIRE_KEY.WINNER_SEAT]: 1,
            [WIRE_KEY.LOSER_SEAT]: 2,
            [WIRE_KEY.WINNING_TILE]: 49,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.HAN]: 7,
                [WIRE_KEY.FU]: 30,
                [WIRE_KEY.YAKU]: [
                    { [WIRE_KEY.YAKU_ID]: 3, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 8, [WIRE_KEY.HAN]: 2, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 12, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 27, [WIRE_KEY.HAN]: 2, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    {
                        [WIRE_KEY.YAKU_ID]: 121,
                        [WIRE_KEY.HAN]: 1,
                        [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                    },
                ],
                [WIRE_KEY.POINTS]: 120,
                [WIRE_KEY.HAND_LIMIT]: "haneman",
            },
            [WIRE_KEY.SCORES]: { "0": 250, "1": 240, "2": 250, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 130, "2": -120, "3": 0 },
            [WIRE_KEY.RIICHI_COLLECTED]: 1,
            [WIRE_KEY.CLOSED_TILES]: [0, 4, 8, 12, 16, 20, 24, 28, 32, 40, 44, 72, 73],
            [WIRE_KEY.MELDS]: [],
            [WIRE_KEY.HONBA_BONUS]: 0,
            [WIRE_KEY.URA_DORA]: [131],
        },
    },
    {
        fixture: "double_ron",
        key: "double_ron",
        label: "Double ron",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 2,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [116],
            [WIRE_KEY.LOSER_SEAT]: 0,
            [WIRE_KEY.WINNING_TILE]: 50,
            [WIRE_KEY.WINNERS]: [
                {
                    [WIRE_KEY.WINNER_SEAT]: 1,
                    [WIRE_KEY.HAND_RESULT]: {
                        [WIRE_KEY.HAN]: 7,
                        [WIRE_KEY.FU]: 30,
                        [WIRE_KEY.YAKU]: [
                            {
                                [WIRE_KEY.YAKU_ID]: 3,
                                [WIRE_KEY.HAN]: 1,
                                [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                            },
                            {
                                [WIRE_KEY.YAKU_ID]: 8,
                                [WIRE_KEY.HAN]: 2,
                                [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                            },
                            {
                                [WIRE_KEY.YAKU_ID]: 12,
                                [WIRE_KEY.HAN]: 1,
                                [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                            },
                            {
                                [WIRE_KEY.YAKU_ID]: 27,
                                [WIRE_KEY.HAN]: 2,
                                [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                            },
                            {
                                [WIRE_KEY.YAKU_ID]: 121,
                                [WIRE_KEY.HAN]: 1,
                                [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                            },
                        ],
                        [WIRE_KEY.POINTS]: 120,
                        [WIRE_KEY.HAND_LIMIT]: "haneman",
                    },
                    [WIRE_KEY.SCORE_CHANGES]: { "0": -120, "1": 140, "2": 0, "3": 0 },
                    [WIRE_KEY.RIICHI_COLLECTED]: 2,
                    [WIRE_KEY.CLOSED_TILES]: [0, 4, 8, 12, 16, 20, 24, 28, 32, 40, 44, 72, 73],
                    [WIRE_KEY.MELDS]: [],
                    [WIRE_KEY.HONBA_BONUS]: 0,
                    [WIRE_KEY.URA_DORA]: [130],
                },
                {
                    [WIRE_KEY.WINNER_SEAT]: 2,
                    [WIRE_KEY.HAND_RESULT]: {
                        [WIRE_KEY.HAN]: 4,
                        [WIRE_KEY.FU]: 30,
                        [WIRE_KEY.YAKU]: [
                            {
                                [WIRE_KEY.YAKU_ID]: 3,
                                [WIRE_KEY.HAN]: 1,
                                [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                            },
                            {
                                [WIRE_KEY.YAKU_ID]: 8,
                                [WIRE_KEY.HAN]: 2,
                                [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                            },
                            {
                                [WIRE_KEY.YAKU_ID]: 12,
                                [WIRE_KEY.HAN]: 1,
                                [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                            },
                        ],
                        [WIRE_KEY.POINTS]: 80,
                        [WIRE_KEY.HAND_LIMIT]: "mangan",
                    },
                    [WIRE_KEY.SCORE_CHANGES]: { "0": -80, "1": 0, "2": 80, "3": 0 },
                    [WIRE_KEY.RIICHI_COLLECTED]: 0,
                    [WIRE_KEY.CLOSED_TILES]: [5, 9, 13, 33, 34, 53, 57, 85, 89, 93, 94, 97, 101],
                    [WIRE_KEY.MELDS]: [],
                    [WIRE_KEY.HONBA_BONUS]: 0,
                    [WIRE_KEY.URA_DORA]: [130],
                },
            ],
            [WIRE_KEY.SCORES]: { "0": 250, "1": 240, "2": 240, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": -200, "1": 140, "2": 80, "3": 0 },
        },
    },
    {
        fixture: "eager_game",
        key: "dealer",
        label: "Dealer",
        names: ["Alice", "Charlie", "Bob", "Diana"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 0,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 2,
            [WIRE_KEY.DORA_INDICATORS]: [9],
            [WIRE_KEY.WINNER_SEAT]: 2,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.HAN]: 5,
                [WIRE_KEY.FU]: 25,
                [WIRE_KEY.YAKU]: [
                    { [WIRE_KEY.YAKU_ID]: 0, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 13, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 34, [WIRE_KEY.HAN]: 2, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    {
                        [WIRE_KEY.YAKU_ID]: 121,
                        [WIRE_KEY.HAN]: 1,
                        [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                    },
                ],
                [WIRE_KEY.POINTS]: 120,
                [WIRE_KEY.HAND_LIMIT]: "mangan",
            },
            [WIRE_KEY.SCORES]: { "0": 230, "1": 210, "2": 230, "3": 330 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": -40, "1": -40, "2": 120, "3": -40 },
            [WIRE_KEY.RIICHI_COLLECTED]: 0,
            [WIRE_KEY.CLOSED_TILES]: [11, 21, 55, 64, 77, 79, 85, 87, 88, 65, 89, 53, 10],
            [WIRE_KEY.MELDS]: [],
            [WIRE_KEY.WINNING_TILE]: 23,
            [WIRE_KEY.HONBA_BONUS]: 0,
        },
    },
    {
        fixture: "head_bump",
        key: "head_bump",
        label: "Head bump",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 1,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [107],
            [WIRE_KEY.WINNER_SEAT]: 1,
            [WIRE_KEY.LOSER_SEAT]: 0,
            [WIRE_KEY.WINNING_TILE]: 46,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.HAN]: 8,
                [WIRE_KEY.FU]: 40,
                [WIRE_KEY.YAKU]: [
                    { [WIRE_KEY.YAKU_ID]: 11, [WIRE_KEY.HAN]: 5, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 27, [WIRE_KEY.HAN]: 2, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    {
                        [WIRE_KEY.YAKU_ID]: 121,
                        [WIRE_KEY.HAN]: 1,
                        [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                    },
                ],
                [WIRE_KEY.POINTS]: 160,
                [WIRE_KEY.HAND_LIMIT]: "baiman",
            },
            [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": -160, "1": 160, "2": 0, "3": 0 },
            [WIRE_KEY.RIICHI_COLLECTED]: 0,
            [WIRE_KEY.CLOSED_TILES]: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 124, 125],
            [WIRE_KEY.MELDS]: [],
            [WIRE_KEY.HONBA_BONUS]: 0,
            [WIRE_KEY.HEAD_BUMPED_SEATS]: [2],
        },
    },
    {
        fixture: "kans",
        key: "sanbaiman",
        label: "Sanbaiman",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 0,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [102, 103, 104, 107],
            [WIRE_KEY.WINNER_SEAT]: 3,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.HAN]: 11,
                [WIRE_KEY.FU]: 60,
                [WIRE_KEY.YAKU]: [
                    { [WIRE_KEY.YAKU_ID]: 0, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 5, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    {
                        [WIRE_KEY.YAKU_ID]: 120,
                        [WIRE_KEY.HAN]: 8,
                        [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                    },
                    {
                        [WIRE_KEY.YAKU_ID]: 121,
                        [WIRE_KEY.HAN]: 1,
                        [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                    },
                ],
                [WIRE_KEY.POINTS]: 240,
                [WIRE_KEY.HAND_LIMIT]: "sanbaiman",
            },
            [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": -120, "1": -60, "2": -60, "3": 240 },
            [WIRE_KEY.RIICHI_COLLECTED]: 0,
            [WIRE_KEY.CLOSED_TILES]: [4, 8, 12, 52, 56, 60, 92, 96, 100, 32],
            [WIRE_KEY.MELDS]: [27_627],
            [WIRE_KEY.WINNING_TILE]: 33,
            [WIRE_KEY.HONBA_BONUS]: 0,
        },
    },
    {
        fixture: "kazoe",
        key: "kazoe",
        label: "Kazoe",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 0,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [112],
            [WIRE_KEY.WINNER_SEAT]: 0,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.HAN]: 15,
                [WIRE_KEY.FU]: 20,
                [WIRE_KEY.YAKU]: [
                    { [WIRE_KEY.YAKU_ID]: 0, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 3, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 8, [WIRE_KEY.HAN]: 2, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 12, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 13, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 38, [WIRE_KEY.HAN]: 3, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 39, [WIRE_KEY.HAN]: 6, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                ],
                [WIRE_KEY.POINTS]: 480,
                [WIRE_KEY.HAND_LIMIT]: "kazoe_yakuman",
                [WIRE_KEY.YAKUMAN_COUNT]: 1,
            },
            [WIRE_KEY.SCORES]: { "0": 240, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": 490, "1": -160, "2": -160, "3": -160 },
            [WIRE_KEY.RIICHI_COLLECTED]: 1,
            [WIRE_KEY.CLOSED_TILES]: [40, 44, 45, 48, 49, 53, 54, 56, 57, 60, 61, 64, 65],
            [WIRE_KEY.MELDS]: [],
            [WIRE_KEY.WINNING_TILE]: 41,
            [WIRE_KEY.HONBA_BONUS]: 0,
            [WIRE_KEY.URA_DORA]: [131],
        },
    },
    {
        fixture: "chankan_added",
        key: "chankan",
        label: "Chankan",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 1,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [112],
            [WIRE_KEY.WINNER_SEAT]: 2,
            [WIRE_KEY.LOSER_SEAT]: 1,
            [WIRE_KEY.WINNING_TILE]: 59,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.HAN]: 6,
                [WIRE_KEY.FU]: 30,
                [WIRE_KEY.YAKU]: [
                    { [WIRE_KEY.YAKU_ID]: 4, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 12, [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.YAKU_ID]: 27, [WIRE_KEY.HAN]: 2, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    {
                        [WIRE_KEY.YAKU_ID]: 121,
                        [WIRE_KEY.HAN]: 2,
                        [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                    },
                ],
                [WIRE_KEY.POINTS]: 120,
                [WIRE_KEY.HAND_LIMIT]: "haneman",
            },
            [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": -120, "2": 120, "3": 0 },
            [WIRE_KEY.RIICHI_COLLECTED]: 0,
            [WIRE_KEY.CLOSED_TILES]: [0, 4, 8, 12, 16, 20, 24, 28, 32, 48, 52, 72, 73],
            [WIRE_KEY.MELDS]: [],
            [WIRE_KEY.HONBA_BONUS]: 0,
            [WIRE_KEY.ROBBED_KAN]: {
                [WIRE_KEY.SEAT]: 1,
                [WIRE_KEY.TILE_ID]: 59,
                [WIRE_KEY.KAN_TYPE]: "added",
            },
        },
    },
    {
        fixture: "chankan_closed_kokushi",
        key: "yakuman",
        label: "Yakuman",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 1,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [109],
            [WIRE_KEY.WINNER_SEAT]: 2,
            [WIRE_KEY.LOSER_SEAT]: 1,
            [WIRE_KEY.WINNING_TILE]: 35,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.HAN]: 13,
                [WIRE_KEY.FU]: 0,
                [WIRE_KEY.YAKU]: [
                    {
                        [WIRE_KEY.YAKU_ID]: 100,
                        [WIRE_KEY.HAN]: 13,
                        [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 1,
                    },
                ],
                [WIRE_KEY.POINTS]: 320,
                [WIRE_KEY.HAND_LIMIT]: "yakuman",
                [WIRE_KEY.YAKUMAN_COUNT]: 1,
            },
            [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": -320, "2": 320, "3": 0 },
            [WIRE_KEY.RIICHI_COLLECTED]: 0,
            [WIRE_KEY.CLOSED_TILES]: [0, 1, 36, 68, 72, 104, 108, 112, 116, 120, 124, 128, 132],
            [WIRE_KEY.MELDS]: [],
            [WIRE_KEY.HONBA_BONUS]: 0,
            [WIRE_KEY.ROBBED_KAN]: {
                [WIRE_KEY.SEAT]: 1,
                [WIRE_KEY.TILE_ID]: 35,
                [WIRE_KEY.KAN_TYPE]: "closed",
            },
        },
    },
    {
        fixture: "pao",
        key: "pao",
        label: "Pao",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 0,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [106],
            [WIRE_KEY.WINNER_SEAT]: 1,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.HAN]: 13,
                [WIRE_KEY.FU]: 40,
                [WIRE_KEY.YAKU]: [
                    {
                        [WIRE_KEY.YAKU_ID]: 103,
                        [WIRE_KEY.HAN]: 13,
                        [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 1,
                    },
                ],
                [WIRE_KEY.POINTS]: 320,
                [WIRE_KEY.HAND_LIMIT]: "yakuman",
                [WIRE_KEY.YAKUMAN_COUNT]: 1,
            },
            [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": -320, "1": 320, "2": 0, "3": 0 },
            [WIRE_KEY.RIICHI_COLLECTED]: 0,
            [WIRE_KEY.CLOSED_TILES]: [0, 4, 8, 12],
            [WIRE_KEY.MELDS]: [20_733, 20_869, 21_021],
            [WIRE_KEY.WINNING_TILE]: 13,
            [WIRE_KEY.HONBA_BONUS]: 0,
            [WIRE_KEY.PAO_SEAT]: 0,
            [WIRE_KEY.PAO_LIABILITY]: {
                [WIRE_KEY.YAKU]: [103],
                [WIRE_KEY.PAO_SHARE]: "all",
                [WIRE_KEY.PAYS_HONBA]: false,
            },
        },
    },
    {
        fixture: "exhaustive_tenpai",
        key: "exhaustive",
        label: "Exhaustive",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 3,
            [WIRE_KEY.RIICHI_STICKS]: 1,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [116],
            [WIRE_KEY.TENPAI_SEATS]: [1, 2],
            [WIRE_KEY.NOTEN_SEATS]: [0, 3],
            [WIRE_KEY.TENPAI_HANDS]: [
                {
                    [WIRE_KEY.SEAT]: 1,
                    [WIRE_KEY.CLOSED_TILES]: [37, 41, 45, 49, 53, 57, 61, 65, 69, 73, 74, 75, 135],
                    [WIRE_KEY.MELDS]: [],
                },
                {
                    [WIRE_KEY.SEAT]: 2,
                    [WIRE_KEY.CLOSED_TILES]: [6, 10, 14, 18, 22, 26, 82, 86, 90, 94, 98, 102, 131],
                    [WIRE_KEY.MELDS]: [],
                },
            ],
            [WIRE_KEY.SCORES]: { "0": 250, "1": 240, "2": 250, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": -15, "1": 15, "2": 15, "3": -15 },
        },
    },
    {
        fixture: "full_game",
        key: "all_noten",
        label: "All noten",
        names: ["Wanjirou", "Ojisan", "Ichihime", "Akagi"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 3,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 3,
            [WIRE_KEY.DORA_INDICATORS]: [32],
            [WIRE_KEY.TENPAI_SEATS]: [],
            [WIRE_KEY.NOTEN_SEATS]: [0, 1, 2, 3],
            [WIRE_KEY.TENPAI_HANDS]: [],
            [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
        },
    },
    {
        fixture: "nagashi",
        key: "nagashi",
        label: "Nagashi",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 5,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [120],
            [WIRE_KEY.QUALIFYING_SEATS]: [1],
            [WIRE_KEY.QUALIFYING_RIVERS]: [
                {
                    [WIRE_KEY.SEAT]: 1,
                    [WIRE_KEY.DISCARDS]: [
                        {
                            [WIRE_KEY.TILE_ID]: 0,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 1,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 2,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 3,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 32,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 33,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 34,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 35,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 36,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 37,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 38,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 39,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 68,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 69,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 70,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 71,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 72,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                        {
                            [WIRE_KEY.TILE_ID]: 73,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.RIICHI_DISCARD]: false,
                        },
                    ],
                },
            ],
            [WIRE_KEY.TENPAI_SEATS]: [3],
            [WIRE_KEY.NOTEN_SEATS]: [0, 1, 2],
            [WIRE_KEY.TENPAI_HANDS]: [
                {
                    [WIRE_KEY.SEAT]: 3,
                    [WIRE_KEY.CLOSED_TILES]: [7, 11, 15, 19, 23, 27, 79, 83, 87, 91, 95, 99, 127],
                    [WIRE_KEY.MELDS]: [],
                },
            ],
            [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": -40, "1": 80, "2": -20, "3": -20 },
        },
    },
    {
        fixture: "kyuushu",
        key: "kyuushu",
        label: "Kyuushu",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 4,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [110],
            [WIRE_KEY.ABORTIVE_REASON]: "nine_terminals",
            [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
            [WIRE_KEY.SEAT]: 1,
        },
    },
    {
        fixture: "four_riichi",
        key: "four_riichi",
        label: "4 riichi",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 4,
            [WIRE_KEY.RIICHI_STICKS]: 4,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [114],
            [WIRE_KEY.ABORTIVE_REASON]: "four_riichi",
            [WIRE_KEY.SCORES]: { "0": 240, "1": 240, "2": 240, "3": 240 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
        },
    },
    {
        fixture: "triple_ron",
        key: "triple_ron",
        label: "Triple ron",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 4,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [107],
            [WIRE_KEY.ABORTIVE_REASON]: "triple_ron",
            [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
            [WIRE_KEY.RON_CALLERS]: [1, 2, 3],
        },
    },
    {
        fixture: "four_winds_riichi",
        key: "four_winds",
        label: "4 winds",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 4,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [115],
            [WIRE_KEY.ABORTIVE_REASON]: "four_winds",
            [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
        },
    },
    {
        fixture: "four_kans",
        key: "four_kans",
        label: "4 kans",
        names: ["Diana", "Alice", "Charlie", "Bob"],
        riichiStickValue: 1000,
        roundEnd: {
            [WIRE_KEY.EVENT_TYPE]: 4,
            [WIRE_KEY.RESULT_TYPE]: 4,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.DORA_INDICATORS]: [116, 119, 120, 121, 124],
            [WIRE_KEY.ABORTIVE_REASON]: "four_kans",
            [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
        },
    },
] as const satisfies readonly ResultSource[];

export type ResultStory = (typeof RESULT_SOURCES)[number]["key"];

export const RESULT_STORIES: readonly ResultStory[] = RESULT_SOURCES.map((source) => source.key);

function resultSource(story: ResultStory): ResultSource {
    const source = RESULT_SOURCES.find((candidate) => candidate.key === story);
    if (source === undefined) {
        throw new Error(`No result story ${story}`);
    }
    return source;
}

export function resultStoryLabel(story: ResultStory): string {
    return resultSource(story).label;
}

export interface ResultStoryTable {
    /** The replay fixture the story's round end comes from. */
    readonly fixture: string;
    readonly result: RoundEndResult;
    readonly players: readonly PlayerState[];
}

export function resultStoryTable(story: ResultStory): ResultStoryTable {
    const source = resultSource(story);
    const event = parseRoundEnd(source.roundEnd);
    const players = source.names.map((name, seat) =>
        createInitialPlayerState({
            isAiPlayer: false,
            name,
            score: seatEntry(event.scores, seat),
            seat,
        }),
    );
    return {
        fixture: source.fixture,
        players,
        result: extractRoundEndResult(event, source),
    };
}
