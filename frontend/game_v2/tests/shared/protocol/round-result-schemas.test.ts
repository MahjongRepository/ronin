import { assert, describe, expect, it } from "vitest";

import { type RonRoundEnd, WIRE_KEY } from "@/shared/protocol";
import { ABORTIVE_DRAW_TYPE, EVENT_TYPE, ROUND_RESULT_TYPE } from "@/shared/protocol/constants";
import { parseRoundEnd } from "@/shared/protocol/schemas/round-results";

describe("parseRoundEnd", () => {
    describe("tsumo (RESULT_TYPE=0)", () => {
        it("parses tsumo with all fields including score changes and yaku", () => {
            const wire = {
                [WIRE_KEY.CLOSED_TILES]: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.HONBA_BONUS]: 0,
                [WIRE_KEY.HAND_RESULT]: {
                    [WIRE_KEY.FU]: 30,
                    [WIRE_KEY.HAN]: 3,
                    [WIRE_KEY.HAND_LIMIT]: "none",
                    [WIRE_KEY.POINTS]: 30,
                    [WIRE_KEY.YAKU]: [
                        {
                            [WIRE_KEY.HAN]: 1,
                            [WIRE_KEY.YAKU_ID]: 0,
                            [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                        },
                        {
                            [WIRE_KEY.HAN]: 2,
                            [WIRE_KEY.YAKU_ID]: 7,
                            [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                        },
                    ],
                },
                [WIRE_KEY.MELDS]: [],
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RIICHI_COLLECTED]: 2,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.TSUMO,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 100, "1": -34, "2": -33, "3": -33 },
                [WIRE_KEY.SCORES]: { "0": 350, "1": 200, "2": 200, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.WINNER_SEAT]: 0,
                [WIRE_KEY.WINNING_TILE]: 52,
            };
            const result = parseRoundEnd(wire);
            expect(result.type).toBe("round_end");
            expect(result.resultType).toBe(ROUND_RESULT_TYPE.TSUMO);
            expect(result).toHaveProperty("winnerSeat", 0);
            expect(result).toHaveProperty("winningTile", 52);
            expect(result).toHaveProperty("riichiSticksCollected", 2);
            expect(result).toHaveProperty(
                "closedTiles",
                [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
            );
            expect(result).toHaveProperty("melds", []);
        });

        it("reads the round's dealer and dora indicators, refusing a round end without them", () => {
            const wire = {
                [WIRE_KEY.CLOSED_TILES]: [0],
                [WIRE_KEY.DORA_INDICATORS]: [40, 44],
                [WIRE_KEY.DEALER]: 3,
                [WIRE_KEY.HONBA_BONUS]: 0,
                [WIRE_KEY.HAND_RESULT]: {
                    [WIRE_KEY.FU]: 30,
                    [WIRE_KEY.HAN]: 1,
                    [WIRE_KEY.HAND_LIMIT]: "none",
                    [WIRE_KEY.POINTS]: 10,
                    [WIRE_KEY.YAKU]: [
                        {
                            [WIRE_KEY.HAN]: 1,
                            [WIRE_KEY.YAKU_ID]: 0,
                            [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                        },
                    ],
                },
                [WIRE_KEY.MELDS]: [],
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RIICHI_COLLECTED]: 0,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.TSUMO,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 10, "1": -4, "2": -3, "3": -3 },
                [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.WINNER_SEAT]: 0,
                [WIRE_KEY.WINNING_TILE]: 0,
            };
            const result = parseRoundEnd(wire);

            expect([result.dealerSeat, result.doraIndicators]).toEqual([3, [40, 44]]);
            expect(() => parseRoundEnd({ ...wire, [WIRE_KEY.DEALER]: undefined })).toThrow();
            expect(() =>
                parseRoundEnd({ ...wire, [WIRE_KEY.DORA_INDICATORS]: undefined }),
            ).toThrow();
        });

        it("decodes wire scores (250 -> 25000)", () => {
            const wire = {
                [WIRE_KEY.CLOSED_TILES]: [0],
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.HONBA_BONUS]: 0,
                [WIRE_KEY.HAND_RESULT]: {
                    [WIRE_KEY.FU]: 30,
                    [WIRE_KEY.HAN]: 1,
                    [WIRE_KEY.HAND_LIMIT]: "none",
                    [WIRE_KEY.POINTS]: 10,
                    [WIRE_KEY.YAKU]: [
                        {
                            [WIRE_KEY.HAN]: 1,
                            [WIRE_KEY.YAKU_ID]: 0,
                            [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                        },
                    ],
                },
                [WIRE_KEY.MELDS]: [],
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RIICHI_COLLECTED]: 0,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.TSUMO,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 10, "1": -4, "2": -3, "3": -3 },
                [WIRE_KEY.SCORES]: { "0": 260, "1": 246, "2": 247, "3": 247 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.WINNER_SEAT]: 0,
                [WIRE_KEY.WINNING_TILE]: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result.scores).toEqual({ "0": 26_000, "1": 24_600, "2": 24_700, "3": 24_700 });
            expect(result.scoreChanges).toEqual({ "0": 1000, "1": -400, "2": -300, "3": -300 });
        });

        it("reads a yakuman limit with its count and each yaku's, refusing a yakuman limit without its count", () => {
            const yakuman = {
                [WIRE_KEY.FU]: 0,
                [WIRE_KEY.HAN]: 26,
                [WIRE_KEY.HAND_LIMIT]: "yakuman",
                [WIRE_KEY.POINTS]: 640,
                [WIRE_KEY.YAKUMAN_COUNT]: 2,
                [WIRE_KEY.YAKU]: [
                    {
                        [WIRE_KEY.HAN]: 26,
                        [WIRE_KEY.YAKU_ID]: 113,
                        [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 2,
                    },
                ],
            };
            const wire = {
                [WIRE_KEY.CLOSED_TILES]: [0],
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.HONBA_BONUS]: 0,
                [WIRE_KEY.HAND_RESULT]: yakuman,
                [WIRE_KEY.MELDS]: [],
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RIICHI_COLLECTED]: 0,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.TSUMO,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 640, "1": -320, "2": -160, "3": -160 },
                [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.WINNER_SEAT]: 0,
                [WIRE_KEY.WINNING_TILE]: 0,
            };
            const result = parseRoundEnd(wire);
            if (result.resultType !== ROUND_RESULT_TYPE.TSUMO) {
                throw new Error("wrong type");
            }

            expect([result.handResult.limit, result.handResult.yakumanCount]).toEqual([
                "yakuman",
                2,
            ]);
            expect(result.handResult.yaku).toEqual([{ han: 26, yakuId: 113, yakumanCount: 2 }]);
            expect(() =>
                parseRoundEnd({
                    ...wire,
                    [WIRE_KEY.HAND_RESULT]: { ...yakuman, [WIRE_KEY.YAKUMAN_COUNT]: undefined },
                }),
            ).toThrow("yakuman count");
            expect(() =>
                parseRoundEnd({
                    ...wire,
                    [WIRE_KEY.HAND_RESULT]: { ...yakuman, [WIRE_KEY.HAND_LIMIT]: "mangan" },
                }),
            ).toThrow("yakuman count");
        });

        it("parses hand result with yaku array", () => {
            const wire = {
                [WIRE_KEY.CLOSED_TILES]: [0, 4],
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.HONBA_BONUS]: 0,
                [WIRE_KEY.HAND_RESULT]: {
                    [WIRE_KEY.FU]: 40,
                    [WIRE_KEY.HAN]: 4,
                    [WIRE_KEY.HAND_LIMIT]: "none",
                    [WIRE_KEY.POINTS]: 40,
                    [WIRE_KEY.YAKU]: [
                        {
                            [WIRE_KEY.HAN]: 1,
                            [WIRE_KEY.YAKU_ID]: 0,
                            [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                        },
                        {
                            [WIRE_KEY.HAN]: 1,
                            [WIRE_KEY.YAKU_ID]: 1,
                            [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                        },
                        {
                            [WIRE_KEY.HAN]: 2,
                            [WIRE_KEY.YAKU_ID]: 7,
                            [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                        },
                    ],
                },
                [WIRE_KEY.MELDS]: [],
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RIICHI_COLLECTED]: 0,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.TSUMO,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 80, "1": 0, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 330, "1": 250, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.WINNER_SEAT]: 0,
                [WIRE_KEY.WINNING_TILE]: 8,
            };
            const result = parseRoundEnd(wire);
            if (result.resultType !== ROUND_RESULT_TYPE.TSUMO) {
                throw new Error("wrong type");
            }
            expect(result.handResult.han).toBe(4);
            expect(result.handResult.fu).toBe(40);
            expect(result.handResult.points).toBe(4000);
            expect([result.handResult.limit, result.handResult.yakumanCount]).toEqual([
                "none",
                null,
            ]);
            expect(result.handResult.yaku).toEqual([
                { han: 1, yakuId: 0, yakumanCount: 0 },
                { han: 1, yakuId: 1, yakumanCount: 0 },
                { han: 2, yakuId: 7, yakumanCount: 0 },
            ]);
        });

        it("reads the liable seat with what it pays and the honba bonus, refusing a seat without its liability", () => {
            const wire = {
                [WIRE_KEY.CLOSED_TILES]: [0],
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.HONBA_BONUS]: 3,
                [WIRE_KEY.HAND_RESULT]: {
                    [WIRE_KEY.FU]: 30,
                    [WIRE_KEY.HAN]: 13,
                    [WIRE_KEY.HAND_LIMIT]: "none",
                    [WIRE_KEY.POINTS]: 130,
                    [WIRE_KEY.YAKU]: [
                        {
                            [WIRE_KEY.HAN]: 13,
                            [WIRE_KEY.YAKU_ID]: 40,
                            [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                        },
                    ],
                },
                [WIRE_KEY.MELDS]: [6100],
                [WIRE_KEY.PAO_LIABILITY]: {
                    [WIRE_KEY.PAYS_HONBA]: true,
                    [WIRE_KEY.PAO_SHARE]: "all",
                    [WIRE_KEY.YAKU]: [103],
                },
                [WIRE_KEY.PAO_SEAT]: 2,
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RIICHI_COLLECTED]: 0,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.TSUMO,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 320, "1": 0, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 570, "1": 250, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.WINNER_SEAT]: 0,
                [WIRE_KEY.WINNING_TILE]: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("pao", {
                paysHonba: true,
                seat: 2,
                share: "all",
                yakuIds: [103],
            });
            expect(result).toHaveProperty("honbaBonus", 300);
            expect(() => parseRoundEnd({ ...wire, [WIRE_KEY.PAO_LIABILITY]: undefined })).toThrow(
                "liable seat",
            );
            expect(() => parseRoundEnd({ ...wire, [WIRE_KEY.PAO_SEAT]: undefined })).toThrow(
                "liable seat",
            );
            expect(() => parseRoundEnd({ ...wire, [WIRE_KEY.HONBA_BONUS]: undefined })).toThrow();
        });

        it("reads no pao without a liable seat", () => {
            const wire = {
                [WIRE_KEY.CLOSED_TILES]: [0],
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.HONBA_BONUS]: 0,
                [WIRE_KEY.HAND_RESULT]: {
                    [WIRE_KEY.FU]: 30,
                    [WIRE_KEY.HAN]: 1,
                    [WIRE_KEY.HAND_LIMIT]: "none",
                    [WIRE_KEY.POINTS]: 10,
                    [WIRE_KEY.YAKU]: [
                        {
                            [WIRE_KEY.HAN]: 1,
                            [WIRE_KEY.YAKU_ID]: 0,
                            [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                        },
                    ],
                },
                [WIRE_KEY.MELDS]: [],
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RIICHI_COLLECTED]: 0,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.TSUMO,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 10, "1": 0, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 260, "1": 250, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.WINNER_SEAT]: 0,
                [WIRE_KEY.WINNING_TILE]: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("pao", null);
        });

        it("includes ura dora indicators when present", () => {
            const wire = {
                [WIRE_KEY.CLOSED_TILES]: [0, 4],
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.HONBA_BONUS]: 0,
                [WIRE_KEY.HAND_RESULT]: {
                    [WIRE_KEY.FU]: 30,
                    [WIRE_KEY.HAN]: 2,
                    [WIRE_KEY.HAND_LIMIT]: "none",
                    [WIRE_KEY.POINTS]: 20,
                    [WIRE_KEY.YAKU]: [
                        {
                            [WIRE_KEY.HAN]: 2,
                            [WIRE_KEY.YAKU_ID]: 7,
                            [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                        },
                    ],
                },
                [WIRE_KEY.MELDS]: [],
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RIICHI_COLLECTED]: 1,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.TSUMO,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 30, "1": 0, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 280, "1": 250, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.URA_DORA]: [56, 60],
                [WIRE_KEY.WINNER_SEAT]: 0,
                [WIRE_KEY.WINNING_TILE]: 8,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("uraDoraIndicators", [56, 60]);
        });

        it("defaults ura dora indicators to null when absent", () => {
            const wire = {
                [WIRE_KEY.CLOSED_TILES]: [0],
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.HONBA_BONUS]: 0,
                [WIRE_KEY.HAND_RESULT]: {
                    [WIRE_KEY.FU]: 30,
                    [WIRE_KEY.HAN]: 1,
                    [WIRE_KEY.HAND_LIMIT]: "none",
                    [WIRE_KEY.POINTS]: 10,
                    [WIRE_KEY.YAKU]: [
                        {
                            [WIRE_KEY.HAN]: 1,
                            [WIRE_KEY.YAKU_ID]: 0,
                            [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0,
                        },
                    ],
                },
                [WIRE_KEY.MELDS]: [],
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RIICHI_COLLECTED]: 0,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.TSUMO,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 10, "1": 0, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 260, "1": 250, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.WINNER_SEAT]: 0,
                [WIRE_KEY.WINNING_TILE]: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("uraDoraIndicators", null);
        });

        it("rejects missing required fields", () => {
            const wire = {
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.TSUMO,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.WINNER_SEAT]: 0,
            };
            expect(() => parseRoundEnd(wire)).toThrow();
        });
    });

    it("decodes a winner's added kan with the tile its seat added from hand", () => {
        const addedKanOf1p = 22_457;
        const tsumo = {
            [WIRE_KEY.CLOSED_TILES]: [0],
            [WIRE_KEY.DORA_INDICATORS]: [40],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.HONBA_BONUS]: 0,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.FU]: 30,
                [WIRE_KEY.HAN]: 1,
                [WIRE_KEY.HAND_LIMIT]: "none",
                [WIRE_KEY.POINTS]: 10,
                [WIRE_KEY.YAKU]: [
                    { [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_ID]: 0, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                ],
            },
            [WIRE_KEY.MELDS]: [addedKanOf1p],
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.RIICHI_COLLECTED]: 0,
            [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.TSUMO,
            [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 10, "2": 0, "3": 0 },
            [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
            [WIRE_KEY.WINNER_SEAT]: 1,
            [WIRE_KEY.WINNING_TILE]: 0,
        };

        expect(parseRoundEnd(tsumo)).toMatchObject({
            melds: [{ addedTileId: 39, calledTileId: 38, meldType: "added_kan" }],
        });
    });

    it("refuses a meld its hand's seat did not call, a winner's or a tenpai hand's", () => {
        const seat0Meld = 6100;
        const tsumo = {
            [WIRE_KEY.CLOSED_TILES]: [0],
            [WIRE_KEY.DORA_INDICATORS]: [40],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.HONBA_BONUS]: 0,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.FU]: 30,
                [WIRE_KEY.HAN]: 1,
                [WIRE_KEY.HAND_LIMIT]: "none",
                [WIRE_KEY.POINTS]: 10,
                [WIRE_KEY.YAKU]: [
                    { [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_ID]: 0, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                ],
            },
            [WIRE_KEY.MELDS]: [seat0Meld],
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.RIICHI_COLLECTED]: 0,
            [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.TSUMO,
            [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 10, "2": 0, "3": 0 },
            [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
            [WIRE_KEY.WINNER_SEAT]: 1,
            [WIRE_KEY.WINNING_TILE]: 0,
        };
        const draw = {
            [WIRE_KEY.DORA_INDICATORS]: [40],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.NOTEN_SEATS]: [0, 2, 3],
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
            [WIRE_KEY.SCORE_CHANGES]: { "0": -10, "1": 30, "2": -10, "3": -10 },
            [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
            [WIRE_KEY.TENPAI_HANDS]: [
                {
                    [WIRE_KEY.CLOSED_TILES]: [52, 56, 60, 64, 68, 72, 76, 80, 84, 88],
                    [WIRE_KEY.MELDS]: [seat0Meld],
                    [WIRE_KEY.SEAT]: 1,
                },
            ],
            [WIRE_KEY.TENPAI_SEATS]: [1],
        };

        expect(() => parseRoundEnd(tsumo)).toThrow(
            "a winner's hand lists a meld another seat called",
        );
        expect(() => parseRoundEnd(draw)).toThrow("a shown hand lists a meld another seat called");
        expect(parseRoundEnd({ ...tsumo, [WIRE_KEY.WINNER_SEAT]: 0 }).type).toBe("round_end");
    });

    describe("ron (RESULT_TYPE=1)", () => {
        const firstWin = {
            [WIRE_KEY.CLOSED_TILES]: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44],
            [WIRE_KEY.HONBA_BONUS]: 0,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.FU]: 30,
                [WIRE_KEY.HAN]: 3,
                [WIRE_KEY.HAND_LIMIT]: "none",
                [WIRE_KEY.POINTS]: 30,
                [WIRE_KEY.YAKU]: [
                    { [WIRE_KEY.HAN]: 1, [WIRE_KEY.YAKU_ID]: 0, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                    { [WIRE_KEY.HAN]: 2, [WIRE_KEY.YAKU_ID]: 7, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                ],
            },
            [WIRE_KEY.MELDS]: [],
            [WIRE_KEY.RIICHI_COLLECTED]: 1,
            [WIRE_KEY.SCORE_CHANGES]: { "0": 40, "1": 0, "2": 0, "3": -40 },
            [WIRE_KEY.WINNER_SEAT]: 0,
        };
        const secondWin = {
            [WIRE_KEY.CLOSED_TILES]: [52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96],
            [WIRE_KEY.HONBA_BONUS]: 0,
            [WIRE_KEY.HAND_RESULT]: {
                [WIRE_KEY.FU]: 30,
                [WIRE_KEY.HAN]: 2,
                [WIRE_KEY.HAND_LIMIT]: "none",
                [WIRE_KEY.POINTS]: 20,
                [WIRE_KEY.YAKU]: [
                    { [WIRE_KEY.HAN]: 2, [WIRE_KEY.YAKU_ID]: 7, [WIRE_KEY.YAKU_YAKUMAN_COUNT]: 0 },
                ],
            },
            [WIRE_KEY.MELDS]: [],
            [WIRE_KEY.RIICHI_COLLECTED]: 0,
            [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 30, "2": 0, "3": -30 },
            [WIRE_KEY.WINNER_SEAT]: 1,
        };
        const ronWire = {
            [WIRE_KEY.DORA_INDICATORS]: [40],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.LOSER_SEAT]: 3,
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.RON,
            [WIRE_KEY.SCORE_CHANGES]: { "0": 40, "1": 0, "2": 0, "3": -40 },
            [WIRE_KEY.SCORES]: { "0": 290, "1": 250, "2": 250, "3": 210 },
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
            [WIRE_KEY.WINNERS]: [firstWin],
            [WIRE_KEY.WINNING_TILE]: 48,
        };

        function parseRon(wire: Record<string, unknown>): RonRoundEnd {
            const result = parseRoundEnd(wire);
            assert(result.resultType === ROUND_RESULT_TYPE.RON);
            return result;
        }

        it("parses a ron's loser, its won tile and its one win under the winners", () => {
            const result = parseRon(ronWire);

            expect([result.type, result.loserSeat, result.winningTile]).toEqual([
                "round_end",
                3,
                48,
            ]);
            expect(result.winners).toMatchObject([
                {
                    closedTiles: firstWin[WIRE_KEY.CLOSED_TILES],
                    melds: [],
                    riichiSticksCollected: 1,
                    scoreChanges: { "0": 4000, "1": 0, "2": 0, "3": -4000 },
                    winnerSeat: 0,
                },
            ]);
        });

        it("parses two winners of one discard, each with its own hand and payments", () => {
            const result = parseRon({
                ...ronWire,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 40, "1": 30, "2": 0, "3": -70 },
                [WIRE_KEY.WINNERS]: [firstWin, secondWin],
            });

            expect(
                result.winners.map((winner) => [
                    winner.winnerSeat,
                    winner.handResult.han,
                    winner.scoreChanges,
                ]),
            ).toEqual([
                [0, 3, { "0": 4000, "1": 0, "2": 0, "3": -4000 }],
                [1, 2, { "0": 0, "1": 3000, "2": 0, "3": -3000 }],
            ]);
            expect(result.scoreChanges).toEqual({ "0": 4000, "1": 3000, "2": 0, "3": -7000 });
        });

        it.each([
            ["no win", []],
            [
                "three wins, which abort the round instead",
                [firstWin, secondWin, { ...secondWin, [WIRE_KEY.WINNER_SEAT]: 2 }],
            ],
            ["one winner twice", [firstWin, firstWin]],
        ])("refuses a ron of %s", (_name, winners) => {
            expect(() => parseRoundEnd({ ...ronWire, [WIRE_KEY.WINNERS]: winners })).toThrow(
                "one or two distinct winners",
            );
        });

        it("reads the seats its win head-bumped, empty without them", () => {
            const bumped = parseRon({ ...ronWire, [WIRE_KEY.HEAD_BUMPED_SEATS]: [2] });

            expect(bumped.headBumpedSeats).toEqual([2]);
            expect(parseRon(ronWire).headBumpedSeats).toEqual([]);
        });

        it("reads each win's liable seat with its share and its ura dora, null without them", () => {
            const result = parseRon({
                ...ronWire,
                [WIRE_KEY.WINNERS]: [
                    {
                        ...firstWin,
                        [WIRE_KEY.HONBA_BONUS]: 3,
                        [WIRE_KEY.PAO_LIABILITY]: {
                            [WIRE_KEY.PAYS_HONBA]: true,
                            [WIRE_KEY.PAO_SHARE]: "half",
                            [WIRE_KEY.YAKU]: [103],
                        },
                        [WIRE_KEY.PAO_SEAT]: 2,
                        [WIRE_KEY.URA_DORA]: [56],
                    },
                    secondWin,
                ],
            });

            expect(
                result.winners.map((winner) => [
                    winner.pao,
                    winner.honbaBonus,
                    winner.uraDoraIndicators,
                ]),
            ).toEqual([
                [{ paysHonba: true, seat: 2, share: "half", yakuIds: [103] }, 300, [56]],
                [null, 0, null],
            ]);
        });
    });

    describe("exhaustive draw (RESULT_TYPE=3)", () => {
        it("parses exhaustive draw with tenpai and noten seats", () => {
            const wire = {
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.NOTEN_SEATS]: [2, 3],
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 15, "1": 15, "2": -15, "3": -15 },
                [WIRE_KEY.SCORES]: { "0": 265, "1": 265, "2": 235, "3": 235 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.TENPAI_HANDS]: [
                    {
                        [WIRE_KEY.CLOSED_TILES]: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
                        [WIRE_KEY.MELDS]: [],
                        [WIRE_KEY.SEAT]: 0,
                    },
                    {
                        [WIRE_KEY.CLOSED_TILES]: [
                            52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96, 100,
                        ],
                        [WIRE_KEY.MELDS]: [],
                        [WIRE_KEY.SEAT]: 1,
                    },
                ],
                [WIRE_KEY.TENPAI_SEATS]: [0, 1],
            };
            const result = parseRoundEnd(wire);
            expect(result.type).toBe("round_end");
            expect(result.resultType).toBe(ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW);
            if (result.resultType !== ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW) {
                throw new Error("wrong type");
            }
            expect(result.tenpaiSeats).toEqual([0, 1]);
            expect(result.notenSeats).toEqual([2, 3]);
            expect(result.tenpaiHands).toHaveLength(2);
            expect(result.tenpaiHands[0]).toEqual({
                closedTiles: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
                melds: [],
                seat: 0,
            });
        });

        it("parses tenpai hands with melds", () => {
            const wire = {
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.NOTEN_SEATS]: [1, 2, 3],
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 30, "1": -10, "2": -10, "3": -10 },
                [WIRE_KEY.SCORES]: { "0": 280, "1": 240, "2": 240, "3": 240 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.TENPAI_HANDS]: [
                    {
                        [WIRE_KEY.CLOSED_TILES]: [0, 4, 8, 12],
                        [WIRE_KEY.MELDS]: [5000, 5100, 5200],
                        [WIRE_KEY.SEAT]: 0,
                    },
                ],
                [WIRE_KEY.TENPAI_SEATS]: [0],
            };
            const result = parseRoundEnd(wire);
            if (result.resultType !== ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW) {
                throw new Error("wrong type");
            }
            expect(result.tenpaiHands[0].melds.map((meld) => meld.meldType)).toEqual([
                "chi",
                "chi",
                "chi",
            ]);
        });

        it("reads the wait id and timeout of the round advance it opens, null without one, and refuses half of them", () => {
            const wire = {
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.NOTEN_SEATS]: [1],
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 30, "1": -30, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 280, "1": 220, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.TENPAI_HANDS]: [
                    { [WIRE_KEY.CLOSED_TILES]: [0], [WIRE_KEY.MELDS]: [], [WIRE_KEY.SEAT]: 0 },
                ],
                [WIRE_KEY.TENPAI_SEATS]: [0],
            };
            expect(
                parseRoundEnd({
                    ...wire,
                    [WIRE_KEY.ROUND_ADVANCE_SECONDS]: 20,
                    [WIRE_KEY.WAIT_ID]: 6,
                }).roundAdvance,
            ).toEqual({
                seconds: 20,
                waitId: 6,
            });
            expect(parseRoundEnd(wire).roundAdvance).toBeNull();
            expect(() => parseRoundEnd({ ...wire, [WIRE_KEY.WAIT_ID]: 6 })).toThrow(
                "without its timeout",
            );
            expect(() => parseRoundEnd({ ...wire, [WIRE_KEY.ROUND_ADVANCE_SECONDS]: 20 })).toThrow(
                "without its timeout",
            );
        });

        it("decodes wire scores (265 -> 26500)", () => {
            const wire = {
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.NOTEN_SEATS]: [1],
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 30, "1": -30, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 280, "1": 220, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                [WIRE_KEY.TENPAI_HANDS]: [
                    { [WIRE_KEY.CLOSED_TILES]: [0], [WIRE_KEY.MELDS]: [], [WIRE_KEY.SEAT]: 0 },
                ],
                [WIRE_KEY.TENPAI_SEATS]: [0],
            };
            const result = parseRoundEnd(wire);
            expect(result.scores).toEqual({ "0": 28_000, "1": 22_000, "2": 25_000, "3": 25_000 });
            expect(result.scoreChanges).toEqual({ "0": 3000, "1": -3000, "2": 0, "3": 0 });
        });
    });

    describe("abortive draw (RESULT_TYPE=4)", () => {
        it("reads the riichi sticks the draw leaves on the table, and refuses a round end that names none", () => {
            const wire = {
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.RIICHI_STICKS]: 4,
                [WIRE_KEY.ABORTIVE_REASON]: ABORTIVE_DRAW_TYPE.FOUR_RIICHI,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 240, "1": 240, "2": 240, "3": 240 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
            };
            const { [WIRE_KEY.RIICHI_STICKS]: _left, ...unnamed } = wire;

            expect(parseRoundEnd(wire).riichiSticks).toBe(4);
            expect(() => parseRoundEnd(unnamed)).toThrow();
        });

        it("parses abortive draw with reason string", () => {
            const wire = {
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.ABORTIVE_REASON]: ABORTIVE_DRAW_TYPE.FOUR_RIICHI,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
            };
            const result = parseRoundEnd(wire);
            expect(result.type).toBe("round_end");
            expect(result.resultType).toBe(ROUND_RESULT_TYPE.ABORTIVE_DRAW);
            if (result.resultType !== ROUND_RESULT_TYPE.ABORTIVE_DRAW) {
                throw new Error("wrong type");
            }
            expect(result.reason).toBe("four_riichi");
            expect(result.scores).toEqual({ "0": 25_000, "1": 25_000, "2": 25_000, "3": 25_000 });
            expect(result.scoreChanges).toEqual({ "0": 0, "1": 0, "2": 0, "3": 0 });
        });

        it("includes seat when present (nine terminals)", () => {
            const wire = {
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.ABORTIVE_REASON]: ABORTIVE_DRAW_TYPE.NINE_TERMINALS,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                [WIRE_KEY.SEAT]: 2,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
            };
            const result = parseRoundEnd(wire);
            if (result.resultType !== ROUND_RESULT_TYPE.ABORTIVE_DRAW) {
                throw new Error("wrong type");
            }
            expect(result.seat).toBe(2);
        });

        it("defaults seat to null when absent", () => {
            const wire = {
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.ABORTIVE_REASON]: ABORTIVE_DRAW_TYPE.TRIPLE_RON,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
            };
            const result = parseRoundEnd(wire);
            if (result.resultType !== ROUND_RESULT_TYPE.ABORTIVE_DRAW) {
                throw new Error("wrong type");
            }
            expect(result.seat).toBeNull();
        });

        it("reads the hands an abort shows, none without them", () => {
            const wire = {
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.ABORTIVE_REASON]: ABORTIVE_DRAW_TYPE.NINE_TERMINALS,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                [WIRE_KEY.SEAT]: 2,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
            };
            const hand = [0, 32, 36, 68, 72, 104, 108, 112, 116, 120, 124, 128, 132, 1];
            const shown = parseRoundEnd({
                ...wire,
                [WIRE_KEY.SHOWN_HANDS]: [
                    { [WIRE_KEY.CLOSED_TILES]: hand, [WIRE_KEY.MELDS]: [], [WIRE_KEY.SEAT]: 2 },
                ],
            });
            const none = parseRoundEnd(wire);
            assert(shown.resultType === ROUND_RESULT_TYPE.ABORTIVE_DRAW);
            assert(none.resultType === ROUND_RESULT_TYPE.ABORTIVE_DRAW);

            expect(shown.shownHands).toEqual([{ closedTiles: hand, melds: [], seat: 2 }]);
            expect(none.shownHands).toEqual([]);
        });

        it("reads a triple ron's declarers", () => {
            const wire = {
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.RIICHI_STICKS]: 0,
                [WIRE_KEY.RON_CALLERS]: [0, 1, 2],
                [WIRE_KEY.ABORTIVE_REASON]: ABORTIVE_DRAW_TYPE.TRIPLE_RON,
                [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
            };
            const result = parseRoundEnd(wire);
            if (result.resultType !== ROUND_RESULT_TYPE.ABORTIVE_DRAW) {
                throw new Error("wrong type");
            }
            expect(result.ronSeats).toEqual([0, 1, 2]);
        });
    });

    describe("exhaustive draw with a nagashi mangan (RESULT_TYPE=3)", () => {
        const nagashiWire = {
            [WIRE_KEY.DORA_INDICATORS]: [40],
            [WIRE_KEY.DEALER]: 0,
            [WIRE_KEY.NOTEN_SEATS]: [2, 3],
            [WIRE_KEY.QUALIFYING_RIVERS]: [
                {
                    [WIRE_KEY.DISCARDS]: [
                        { [WIRE_KEY.TILE_ID]: 0 },
                        {
                            [WIRE_KEY.RIICHI_DISCARD]: true,
                            [WIRE_KEY.TSUMOGIRI]: true,
                            [WIRE_KEY.TILE_ID]: 132,
                        },
                    ],
                    [WIRE_KEY.SEAT]: 0,
                },
            ],
            [WIRE_KEY.QUALIFYING_SEATS]: [0],
            [WIRE_KEY.RIICHI_STICKS]: 0,
            [WIRE_KEY.RESULT_TYPE]: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
            [WIRE_KEY.SCORE_CHANGES]: { "0": 120, "1": 0, "2": -40, "3": -80 },
            [WIRE_KEY.SCORES]: { "0": 370, "1": 250, "2": 210, "3": 170 },
            [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
            [WIRE_KEY.TENPAI_HANDS]: [
                {
                    [WIRE_KEY.CLOSED_TILES]: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
                    [WIRE_KEY.MELDS]: [],
                    [WIRE_KEY.SEAT]: 0,
                },
            ],
            [WIRE_KEY.TENPAI_SEATS]: [0, 1],
        };

        it("parses its qualifying seats and their rivers beside the tenpai seats", () => {
            const result = parseRoundEnd(nagashiWire);
            assert(result.resultType === ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW);

            expect([result.qualifyingSeats, result.qualifyingRivers]).toEqual([
                [0],
                [
                    {
                        discards: [
                            { isRiichiDiscard: false, isTsumogiri: false, tileId: 0 },
                            { isRiichiDiscard: true, isTsumogiri: true, tileId: 132 },
                        ],
                        seat: 0,
                    },
                ],
            ]);
            expect([result.tenpaiSeats, result.notenSeats]).toEqual([
                [0, 1],
                [2, 3],
            ]);
        });

        it.each([
            ["a qualifying seat without its river", { [WIRE_KEY.QUALIFYING_RIVERS]: [] }],
            ["rivers without their seats", { [WIRE_KEY.QUALIFYING_SEATS]: undefined }],
            [
                "no qualifying seat",
                { [WIRE_KEY.QUALIFYING_RIVERS]: [], [WIRE_KEY.QUALIFYING_SEATS]: [] },
            ],
        ])("refuses a draw naming %s", (_name, change) => {
            const wire = Object.fromEntries(
                Object.entries({ ...nagashiWire, ...change }).filter(
                    ([, value]) => value !== undefined,
                ),
            );

            expect(() => parseRoundEnd(wire)).toThrow("river of each qualifying seat");
        });
    });

    describe("unknown result type", () => {
        it.each([2, 5, 99])(
            "throws on result type %i, the double ron and nagashi codes retired",
            (code) => {
                const wire = {
                    [WIRE_KEY.DORA_INDICATORS]: [40],
                    [WIRE_KEY.DEALER]: 0,
                    [WIRE_KEY.RESULT_TYPE]: code,
                    [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
                    [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.ROUND_END,
                };
                expect(() => parseRoundEnd(wire)).toThrow(
                    `Unknown round result type: RESULT_TYPE=${code}`,
                );
            },
        );
    });
});
