import { describe, expect, it } from "vitest";

import { ABORTIVE_DRAW_TYPE, EVENT_TYPE, ROUND_RESULT_TYPE } from "@/shared/protocol/constants";
import { parseRoundEnd } from "@/shared/protocol/schemas/round-results";

describe("parseRoundEnd", () => {
    describe("tsumo (rt=0)", () => {
        it("parses tsumo with all fields including score changes and yaku", () => {
            const wire = {
                ct: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
                hr: {
                    fu: 30,
                    han: 3,
                    pt: 30,
                    yk: [
                        { han: 1, yi: 0, ym: false },
                        { han: 2, yi: 7, ym: false },
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
                hr: { fu: 30, han: 1, pt: 10, yk: [{ han: 1, yi: 0, ym: false }] },
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
            expect(result.scores).toEqual({ "0": 26_000, "1": 24_600, "2": 24_700, "3": 24_700 });
            expect(result.scoreChanges).toEqual({ "0": 1000, "1": -400, "2": -300, "3": -300 });
        });

        it("parses hand result with yaku array", () => {
            const wire = {
                ct: [0, 4],
                hr: {
                    fu: 40,
                    han: 4,
                    pt: 40,
                    yk: [
                        { han: 1, yi: 0, ym: false },
                        { han: 1, yi: 1, ym: false },
                        { han: 2, yi: 7, ym: false },
                    ],
                },
                ml: [],
                rc: 0,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 80, "1": 0, "2": 0, "3": 0 },
                scs: { "0": 330, "1": 250, "2": 250, "3": 250 },
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
            expect(result.handResult.points).toBe(4000);
            expect(result.handResult.yaku).toEqual([
                { han: 1, isYakuman: false, yakuId: 0 },
                { han: 1, isYakuman: false, yakuId: 1 },
                { han: 2, isYakuman: false, yakuId: 7 },
            ]);
        });

        it("includes optional pao seat when present", () => {
            const wire = {
                ct: [0],
                hr: { fu: 30, han: 13, pt: 130, yk: [{ han: 13, yi: 40, ym: false }] },
                ml: [6100],
                ps: 2,
                rc: 0,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 320, "1": 0, "2": 0, "3": 0 },
                scs: { "0": 570, "1": 250, "2": 250, "3": 250 },
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
                hr: { fu: 30, han: 1, pt: 10, yk: [{ han: 1, yi: 0, ym: false }] },
                ml: [],
                rc: 0,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 10, "1": 0, "2": 0, "3": 0 },
                scs: { "0": 260, "1": 250, "2": 250, "3": 250 },
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
                hr: { fu: 30, han: 2, pt: 20, yk: [{ han: 2, yi: 7, ym: false }] },
                ml: [],
                rc: 1,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 30, "1": 0, "2": 0, "3": 0 },
                scs: { "0": 280, "1": 250, "2": 250, "3": 250 },
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
                hr: { fu: 30, han: 1, pt: 10, yk: [{ han: 1, yi: 0, ym: false }] },
                ml: [],
                rc: 0,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 10, "1": 0, "2": 0, "3": 0 },
                scs: { "0": 260, "1": 250, "2": 250, "3": 250 },
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

    it("refuses a meld its hand's seat did not call, a winner's or a tenpai hand's", () => {
        const seat0Meld = 6100;
        const tsumo = {
            ct: [0],
            hr: { fu: 30, han: 1, pt: 10, yk: [{ han: 1, yi: 0, ym: false }] },
            ml: [seat0Meld],
            rc: 0,
            rt: ROUND_RESULT_TYPE.TSUMO,
            sch: { "0": 0, "1": 10, "2": 0, "3": 0 },
            scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
            t: EVENT_TYPE.ROUND_END,
            ws: 1,
            wt: 0,
        };
        const draw = {
            ns: [0, 2, 3],
            rt: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
            sch: { "0": -10, "1": 30, "2": -10, "3": -10 },
            scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
            t: EVENT_TYPE.ROUND_END,
            th: [{ ct: [52, 56, 60, 64, 68, 72, 76, 80, 84, 88], ml: [seat0Meld], s: 1 }],
            ts: [1],
        };

        expect(() => parseRoundEnd(tsumo)).toThrow(
            "a winner's hand lists a meld another seat called",
        );
        expect(() => parseRoundEnd(draw)).toThrow("a tenpai hand lists a meld another seat called");
        expect(parseRoundEnd({ ...tsumo, ws: 0 }).type).toBe("round_end");
    });

    describe("ron (rt=1)", () => {
        it("parses ron with winner, loser, and winning tile", () => {
            const wire = {
                ct: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44],
                hr: {
                    fu: 30,
                    han: 3,
                    pt: 30,
                    yk: [
                        { han: 1, yi: 0, ym: false },
                        { han: 2, yi: 7, ym: false },
                    ],
                },
                ls: 1,
                ml: [],
                rc: 0,
                rt: ROUND_RESULT_TYPE.RON,
                sch: { "0": 40, "1": -40, "2": 0, "3": 0 },
                scs: { "0": 290, "1": 210, "2": 250, "3": 250 },
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
                hr: { fu: 30, han: 13, pt: 130, yk: [{ han: 13, yi: 40, ym: false }] },
                ls: 2,
                ml: [6100],
                ps: 3,
                rc: 0,
                rt: ROUND_RESULT_TYPE.RON,
                sch: { "0": 320, "1": 0, "2": -320, "3": 0 },
                scs: { "0": 570, "1": 250, "2": 180, "3": 250 },
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
                hr: { fu: 30, han: 1, pt: 10, yk: [{ han: 1, yi: 0, ym: false }] },
                ls: 1,
                ml: [],
                rc: 0,
                rt: ROUND_RESULT_TYPE.RON,
                sch: { "0": 10, "1": -10, "2": 0, "3": 0 },
                scs: { "0": 260, "1": 240, "2": 250, "3": 250 },
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
                hr: { fu: 30, han: 2, pt: 20, yk: [{ han: 2, yi: 7, ym: false }] },
                ls: 1,
                ml: [],
                rc: 1,
                rt: ROUND_RESULT_TYPE.RON,
                sch: { "0": 30, "1": -30, "2": 0, "3": 0 },
                scs: { "0": 280, "1": 220, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
                ud: [56],
                ws: 0,
                wt: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("uraDoraIndicators", [56]);
        });

        it("reads the kan it robs and the seats its win head-bumped, empty without them", () => {
            const wire = {
                ct: [0],
                hr: { fu: 30, han: 2, pt: 20, yk: [{ han: 1, yi: 3, ym: false }] },
                ls: 1,
                ml: [],
                rc: 0,
                rt: ROUND_RESULT_TYPE.RON,
                sch: { "0": 20, "1": -20, "2": 0, "3": 0 },
                scs: { "0": 270, "1": 230, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 9,
            };
            const robbed = parseRoundEnd({ ...wire, hbs: [3], rk: { kty: "added", s: 1, ti: 9 } });
            expect(robbed).toMatchObject({
                headBumpedSeats: [3],
                robbedKan: { kanType: "added", seat: 1, tileId: 9 },
            });
            expect(parseRoundEnd(wire)).toMatchObject({ headBumpedSeats: [], robbedKan: null });
        });
    });

    describe("double ron (rt=2)", () => {
        const doubleRonWire = {
            ls: 3,
            rt: ROUND_RESULT_TYPE.DOUBLE_RON,
            sch: { "0": 40, "1": 30, "2": 0, "3": -70 },
            scs: { "0": 290, "1": 280, "2": 250, "3": 180 },
            t: EVENT_TYPE.ROUND_END,
            wn: [
                {
                    ct: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44],
                    hr: {
                        fu: 30,
                        han: 3,
                        pt: 30,
                        yk: [
                            { han: 1, yi: 0, ym: false },
                            { han: 2, yi: 7, ym: false },
                        ],
                    },
                    ml: [],
                    rc: 1,
                    sch: { "0": 40, "1": 0, "2": 0, "3": -40 },
                    ws: 0,
                },
                {
                    ct: [52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96],
                    hr: { fu: 30, han: 2, pt: 20, yk: [{ han: 2, yi: 7, ym: false }] },
                    ml: [],
                    rc: 0,
                    sch: { "0": 0, "1": 30, "2": 0, "3": -30 },
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
            expect(result.winners.map((winner) => winner.scoreChanges)).toEqual([
                { "0": 4000, "1": 0, "2": 0, "3": -4000 },
                { "0": 0, "1": 3000, "2": 0, "3": -3000 },
            ]);
        });

        it("takes three distinct winners, which a game allowing more rons on one discard sends, but no winner twice", () => {
            const [first, second] = doubleRonWire.wn;
            const third = { ...second, sch: { "0": 0, "1": 0, "2": 20, "3": -20 }, ws: 2 };

            const tripleWinners = parseRoundEnd({ ...doubleRonWire, wn: [first, second, third] });
            expect(
                tripleWinners.resultType === ROUND_RESULT_TYPE.DOUBLE_RON && tripleWinners.winners,
            ).toHaveLength(3);
            expect(() => parseRoundEnd({ ...doubleRonWire, wn: [first, first] })).toThrow(
                "at least two distinct winners",
            );
        });

        it("includes pao seat and ura dora on individual winners", () => {
            const wire = {
                ls: 2,
                rt: ROUND_RESULT_TYPE.DOUBLE_RON,
                sch: { "0": 160, "1": 160, "2": -320, "3": 0 },
                scs: { "0": 410, "1": 410, "2": -70, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
                wn: [
                    {
                        ct: [0],
                        hr: { fu: 30, han: 13, pt: 130, yk: [{ han: 13, yi: 40, ym: false }] },
                        ml: [6100],
                        ps: 2,
                        rc: 0,
                        sch: { "0": 160, "1": 0, "2": -160, "3": 0 },
                        ud: [56],
                        ws: 0,
                    },
                    {
                        ct: [52],
                        hr: { fu: 30, han: 13, pt: 130, yk: [{ han: 13, yi: 41, ym: false }] },
                        ml: [],
                        rc: 0,
                        sch: { "0": 0, "1": 160, "2": -160, "3": 0 },
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

        it("reads the wait id and timeout of the round advance it opens, null without one, and refuses half of them", () => {
            const wire = {
                ns: [1],
                rt: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
                sch: { "0": 30, "1": -30, "2": 0, "3": 0 },
                scs: { "0": 280, "1": 220, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
                th: [{ ct: [0], ml: [], s: 0 }],
                ts: [0],
            };
            expect(parseRoundEnd({ ...wire, at: 20, wi: 6 }).roundAdvance).toEqual({
                seconds: 20,
                waitId: 6,
            });
            expect(parseRoundEnd(wire).roundAdvance).toBeNull();
            expect(() => parseRoundEnd({ ...wire, wi: 6 })).toThrow("without its timeout");
            expect(() => parseRoundEnd({ ...wire, at: 20 })).toThrow("without its timeout");
        });

        it("decodes wire scores (265 -> 26500)", () => {
            const wire = {
                ns: [1],
                rt: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
                sch: { "0": 30, "1": -30, "2": 0, "3": 0 },
                scs: { "0": 280, "1": 220, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
                th: [{ ct: [0], ml: [], s: 0 }],
                ts: [0],
            };
            const result = parseRoundEnd(wire);
            expect(result.scores).toEqual({ "0": 28_000, "1": 22_000, "2": 25_000, "3": 25_000 });
            expect(result.scoreChanges).toEqual({ "0": 3000, "1": -3000, "2": 0, "3": 0 });
        });
    });

    describe("abortive draw (rt=4)", () => {
        it("parses abortive draw with reason string", () => {
            const wire = {
                rn: ABORTIVE_DRAW_TYPE.FOUR_RIICHI,
                rt: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                sch: { "0": 0, "1": 0, "2": 0, "3": 0 },
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
            expect(result.scores).toEqual({ "0": 25_000, "1": 25_000, "2": 25_000, "3": 25_000 });
            expect(result.scoreChanges).toEqual({ "0": 0, "1": 0, "2": 0, "3": 0 });
        });

        it("includes seat when present (nine terminals)", () => {
            const wire = {
                rn: ABORTIVE_DRAW_TYPE.NINE_TERMINALS,
                rt: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                s: 2,
                sch: { "0": 0, "1": 0, "2": 0, "3": 0 },
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
                sch: { "0": 0, "1": 0, "2": 0, "3": 0 },
                scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
            };
            const result = parseRoundEnd(wire);
            if (result.resultType !== ROUND_RESULT_TYPE.ABORTIVE_DRAW) {
                throw new Error("wrong type");
            }
            expect(result.seat).toBeNull();
        });

        it("reads a triple ron's declarers", () => {
            const wire = {
                rcl: [0, 1, 2],
                rn: ABORTIVE_DRAW_TYPE.TRIPLE_RON,
                rt: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                sch: { "0": 0, "1": 0, "2": 0, "3": 0 },
                scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
            };
            const result = parseRoundEnd(wire);
            if (result.resultType !== ROUND_RESULT_TYPE.ABORTIVE_DRAW) {
                throw new Error("wrong type");
            }
            expect(result.ronSeats).toEqual([0, 1, 2]);
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
                scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
            };
            expect(() => parseRoundEnd(wire)).toThrow("Unknown round result type: rt=99");
        });
    });
});
