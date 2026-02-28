import { describe, expect, it } from "vitest";
import { ABORTIVE_DRAW_TYPE, EVENT_TYPE, ROUND_RESULT_TYPE } from "../constants";
import { parseRoundEnd } from "../schemas/round-results";

describe("parseRoundEnd", () => {
    describe("tsumo (rt=0)", () => {
        it("parses tsumo with all fields including score changes and yaku", () => {
            const wire = {
                ct: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
                hr: {
                    fu: 30,
                    han: 3,
                    yk: [
                        { han: 1, yi: 0 },
                        { han: 2, yi: 7 },
                    ],
                },
                ml: [],
                rc: 2,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 100, "1": -34, "2": -33, "3": -33 },
                scs: { "0": 350, "1": 200, "2": 200, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 52,
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

        it("decodes wire scores (250 -> 25000)", () => {
            const wire = {
                ct: [0],
                hr: { fu: 30, han: 1, yk: [{ han: 1, yi: 0 }] },
                ml: [],
                rc: 0,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 10, "1": -4, "2": -3, "3": -3 },
                scs: { "0": 260, "1": 246, "2": 247, "3": 247 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result.scores).toEqual({ "0": 26000, "1": 24600, "2": 24700, "3": 24700 });
            expect(result.scoreChanges).toEqual({ "0": 1000, "1": -400, "2": -300, "3": -300 });
        });

        it("parses hand result with yaku array", () => {
            const wire = {
                ct: [0, 4],
                hr: {
                    fu: 40,
                    han: 4,
                    yk: [
                        { han: 1, yi: 0 },
                        { han: 1, yi: 1 },
                        { han: 2, yi: 7 },
                    ],
                },
                ml: [],
                rc: 0,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 80 },
                scs: { "0": 330 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 8,
            };
            const result = parseRoundEnd(wire);
            if (result.resultType !== ROUND_RESULT_TYPE.TSUMO) {
                throw new Error("wrong type");
            }
            expect(result.handResult.han).toBe(4);
            expect(result.handResult.fu).toBe(40);
            expect(result.handResult.yaku).toEqual([
                { han: 1, yakuId: 0 },
                { han: 1, yakuId: 1 },
                { han: 2, yakuId: 7 },
            ]);
        });

        it("includes optional pao seat when present", () => {
            const wire = {
                ct: [0],
                hr: { fu: 30, han: 13, yk: [{ han: 13, yi: 40 }] },
                ml: [6100],
                ps: 2,
                rc: 0,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 320 },
                scs: { "0": 570 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("paoSeat", 2);
        });

        it("defaults pao seat to null when absent", () => {
            const wire = {
                ct: [0],
                hr: { fu: 30, han: 1, yk: [{ han: 1, yi: 0 }] },
                ml: [],
                rc: 0,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 10 },
                scs: { "0": 260 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("paoSeat", null);
        });

        it("includes ura dora indicators when present", () => {
            const wire = {
                ct: [0, 4],
                hr: { fu: 30, han: 2, yk: [{ han: 2, yi: 7 }] },
                ml: [],
                rc: 1,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 30 },
                scs: { "0": 280 },
                t: EVENT_TYPE.ROUND_END,
                ud: [56, 60],
                ws: 0,
                wt: 8,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("uraDoraIndicators", [56, 60]);
        });

        it("defaults ura dora indicators to null when absent", () => {
            const wire = {
                ct: [0],
                hr: { fu: 30, han: 1, yk: [{ han: 1, yi: 0 }] },
                ml: [],
                rc: 0,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 10 },
                scs: { "0": 260 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("uraDoraIndicators", null);
        });

        it("rejects missing required fields", () => {
            const wire = {
                rt: ROUND_RESULT_TYPE.TSUMO,
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
            };
            expect(() => parseRoundEnd(wire)).toThrow();
        });
    });

    describe("ron (rt=1)", () => {
        it("parses ron with winner, loser, and winning tile", () => {
            const wire = {
                ct: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44],
                hr: {
                    fu: 30,
                    han: 3,
                    yk: [
                        { han: 1, yi: 0 },
                        { han: 2, yi: 7 },
                    ],
                },
                ls: 1,
                ml: [],
                rc: 0,
                rt: ROUND_RESULT_TYPE.RON,
                sch: { "0": 40, "1": -40 },
                scs: { "0": 290, "1": 210 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 48,
            };
            const result = parseRoundEnd(wire);
            expect(result.type).toBe("round_end");
            expect(result.resultType).toBe(ROUND_RESULT_TYPE.RON);
            expect(result).toHaveProperty("winnerSeat", 0);
            expect(result).toHaveProperty("loserSeat", 1);
            expect(result).toHaveProperty("winningTile", 48);
            expect(result).toHaveProperty("riichiSticksCollected", 0);
            expect(result).toHaveProperty("closedTiles");
            expect(result).toHaveProperty("melds", []);
        });

        it("includes optional pao seat when present", () => {
            const wire = {
                ct: [0],
                hr: { fu: 30, han: 13, yk: [{ han: 13, yi: 40 }] },
                ls: 2,
                ml: [6100],
                ps: 3,
                rc: 0,
                rt: ROUND_RESULT_TYPE.RON,
                sch: { "0": 320, "2": -320 },
                scs: { "0": 570, "2": 180 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("paoSeat", 3);
        });

        it("defaults pao seat to null when absent", () => {
            const wire = {
                ct: [0],
                hr: { fu: 30, han: 1, yk: [{ han: 1, yi: 0 }] },
                ls: 1,
                ml: [],
                rc: 0,
                rt: ROUND_RESULT_TYPE.RON,
                sch: { "0": 10, "1": -10 },
                scs: { "0": 260, "1": 240 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("paoSeat", null);
        });

        it("includes ura dora indicators when present", () => {
            const wire = {
                ct: [0],
                hr: { fu: 30, han: 2, yk: [{ han: 2, yi: 7 }] },
                ls: 1,
                ml: [],
                rc: 1,
                rt: ROUND_RESULT_TYPE.RON,
                sch: { "0": 30, "1": -30 },
                scs: { "0": 280, "1": 220 },
                t: EVENT_TYPE.ROUND_END,
                ud: [56],
                ws: 0,
                wt: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("uraDoraIndicators", [56]);
        });
    });

    describe("double ron (rt=2)", () => {
        const doubleRonWire = {
            ls: 3,
            rt: ROUND_RESULT_TYPE.DOUBLE_RON,
            sch: { "0": 40, "1": 30, "3": -70 },
            scs: { "0": 290, "1": 280, "2": 250, "3": 180 },
            t: EVENT_TYPE.ROUND_END,
            wn: [
                {
                    ct: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44],
                    hr: {
                        fu: 30,
                        han: 3,
                        yk: [
                            { han: 1, yi: 0 },
                            { han: 2, yi: 7 },
                        ],
                    },
                    ml: [],
                    rc: 1,
                    ws: 0,
                },
                {
                    ct: [52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96],
                    hr: { fu: 30, han: 2, yk: [{ han: 2, yi: 7 }] },
                    ml: [],
                    rc: 0,
                    ws: 1,
                },
            ],
            wt: 48,
        };

        it("parses double ron with loser and winning tile", () => {
            const result = parseRoundEnd(doubleRonWire);
            expect(result.type).toBe("round_end");
            expect(result.resultType).toBe(ROUND_RESULT_TYPE.DOUBLE_RON);
            expect(result).toHaveProperty("loserSeat", 3);
            expect(result).toHaveProperty("winningTile", 48);
        });

        it("parses two winners with separate hand results", () => {
            const result = parseRoundEnd(doubleRonWire);
            if (result.resultType !== ROUND_RESULT_TYPE.DOUBLE_RON) {
                throw new Error("wrong type");
            }
            expect(result.winners).toHaveLength(2);
            expect(result.winners[0].winnerSeat).toBe(0);
            expect(result.winners[0].riichiSticksCollected).toBe(1);
            expect(result.winners[0].handResult.han).toBe(3);
            expect(result.winners[1].winnerSeat).toBe(1);
            expect(result.winners[1].handResult.han).toBe(2);
        });

        it("includes pao seat and ura dora on individual winners", () => {
            const wire = {
                ls: 2,
                rt: ROUND_RESULT_TYPE.DOUBLE_RON,
                sch: { "0": 160, "1": 160, "2": -320 },
                scs: { "0": 410, "1": 410, "2": -70 },
                t: EVENT_TYPE.ROUND_END,
                wn: [
                    {
                        ct: [0],
                        hr: { fu: 30, han: 13, yk: [{ han: 13, yi: 40 }] },
                        ml: [6100],
                        ps: 2,
                        rc: 0,
                        ud: [56],
                        ws: 0,
                    },
                    {
                        ct: [52],
                        hr: { fu: 30, han: 13, yk: [{ han: 13, yi: 41 }] },
                        ml: [],
                        rc: 0,
                        ws: 1,
                    },
                ],
                wt: 48,
            };
            const result = parseRoundEnd(wire);
            if (result.resultType !== ROUND_RESULT_TYPE.DOUBLE_RON) {
                throw new Error("wrong type");
            }
            expect(result.winners[0].paoSeat).toBe(2);
            expect(result.winners[0].uraDoraIndicators).toEqual([56]);
            expect(result.winners[1].paoSeat).toBeNull();
            expect(result.winners[1].uraDoraIndicators).toBeNull();
        });
    });

    describe("exhaustive draw (rt=3)", () => {
        it("parses exhaustive draw with tenpai and noten seats", () => {
            const wire = {
                ns: [2, 3],
                rt: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
                sch: { "0": 15, "1": 15, "2": -15, "3": -15 },
                scs: { "0": 265, "1": 265, "2": 235, "3": 235 },
                t: EVENT_TYPE.ROUND_END,
                th: [
                    { ct: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48], ml: [], s: 0 },
                    { ct: [52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96, 100], ml: [], s: 1 },
                ],
                ts: [0, 1],
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
                ns: [1, 2, 3],
                rt: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
                sch: { "0": 30, "1": -10, "2": -10, "3": -10 },
                scs: { "0": 280, "1": 240, "2": 240, "3": 240 },
                t: EVENT_TYPE.ROUND_END,
                th: [{ ct: [0, 4, 8, 12], ml: [5000, 5100, 5200], s: 0 }],
                ts: [0],
            };
            const result = parseRoundEnd(wire);
            if (result.resultType !== ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW) {
                throw new Error("wrong type");
            }
            expect(result.tenpaiHands[0].melds).toEqual([5000, 5100, 5200]);
        });

        it("decodes wire scores (265 -> 26500)", () => {
            const wire = {
                ns: [1],
                rt: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
                sch: { "0": 30, "1": -30 },
                scs: { "0": 280, "1": 220 },
                t: EVENT_TYPE.ROUND_END,
                th: [{ ct: [0], ml: [], s: 0 }],
                ts: [0],
            };
            const result = parseRoundEnd(wire);
            expect(result.scores).toEqual({ "0": 28000, "1": 22000 });
            expect(result.scoreChanges).toEqual({ "0": 3000, "1": -3000 });
        });
    });

    describe("abortive draw (rt=4)", () => {
        it("parses abortive draw with reason string", () => {
            const wire = {
                rn: ABORTIVE_DRAW_TYPE.FOUR_RIICHI,
                rt: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                sch: {},
                scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
            };
            const result = parseRoundEnd(wire);
            expect(result.type).toBe("round_end");
            expect(result.resultType).toBe(ROUND_RESULT_TYPE.ABORTIVE_DRAW);
            if (result.resultType !== ROUND_RESULT_TYPE.ABORTIVE_DRAW) {
                throw new Error("wrong type");
            }
            expect(result.reason).toBe("four_riichi");
            expect(result.scores).toEqual({ "0": 25000, "1": 25000, "2": 25000, "3": 25000 });
            expect(result.scoreChanges).toEqual({});
        });

        it("includes seat when present (nine terminals)", () => {
            const wire = {
                rn: ABORTIVE_DRAW_TYPE.NINE_TERMINALS,
                rt: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                s: 2,
                sch: {},
                scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
            };
            const result = parseRoundEnd(wire);
            if (result.resultType !== ROUND_RESULT_TYPE.ABORTIVE_DRAW) {
                throw new Error("wrong type");
            }
            expect(result.seat).toBe(2);
        });

        it("defaults seat to null when absent", () => {
            const wire = {
                rn: ABORTIVE_DRAW_TYPE.TRIPLE_RON,
                rt: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                sch: {},
                scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
            };
            const result = parseRoundEnd(wire);
            if (result.resultType !== ROUND_RESULT_TYPE.ABORTIVE_DRAW) {
                throw new Error("wrong type");
            }
            expect(result.seat).toBeNull();
        });
    });

    describe("nagashi mangan (rt=5)", () => {
        it("parses nagashi mangan with qualifying seats", () => {
            const wire = {
                ns: [2, 3],
                qs: [0],
                rt: ROUND_RESULT_TYPE.NAGASHI_MANGAN,
                sch: { "0": 120, "1": 0, "2": -40, "3": -80 },
                scs: { "0": 370, "1": 250, "2": 210, "3": 170 },
                t: EVENT_TYPE.ROUND_END,
                th: [
                    { ct: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48], ml: [], s: 0 },
                    { ct: [52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96, 100], ml: [], s: 1 },
                ],
                ts: [0, 1],
            };
            const result = parseRoundEnd(wire);
            expect(result.type).toBe("round_end");
            expect(result.resultType).toBe(ROUND_RESULT_TYPE.NAGASHI_MANGAN);
            if (result.resultType !== ROUND_RESULT_TYPE.NAGASHI_MANGAN) {
                throw new Error("wrong type");
            }
            expect(result.qualifyingSeats).toEqual([0]);
            expect(result.tenpaiSeats).toEqual([0, 1]);
            expect(result.notenSeats).toEqual([2, 3]);
            expect(result.tenpaiHands).toHaveLength(2);
        });
    });

    describe("unknown result type", () => {
        it("throws on unknown rt value", () => {
            const wire = {
                rt: 99,
                scs: { "0": 250 },
                t: EVENT_TYPE.ROUND_END,
            };
            expect(() => parseRoundEnd(wire)).toThrow("Unknown round result type: rt=99");
        });
    });
});
