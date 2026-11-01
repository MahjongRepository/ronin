import { describe, expect, it } from "vitest";

import { ABORTIVE_DRAW_TYPE, EVENT_TYPE, ROUND_RESULT_TYPE } from "@/shared/protocol/constants";
import { parseRoundEnd } from "@/shared/protocol/schemas/round-results";

describe("parseRoundEnd", () => {
    describe("tsumo (rt=0)", () => {
        it("parses tsumo with all fields including score changes and yaku", () => {
            const wire = {
                ct: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
                di: [40],
                dl: 0,
                hb: 0,
                hr: {
                    fu: 30,
                    han: 3,
                    lm: "none",
                    pt: 30,
                    yk: [
                        { han: 1, yi: 0, ym: 0 },
                        { han: 2, yi: 7, ym: 0 },
                    ],
                },
                ml: [],
                r: 0,
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

        it("reads the round's dealer and dora indicators, refusing a round end without them", () => {
            const wire = {
                ct: [0],
                di: [40, 44],
                dl: 3,
                hb: 0,
                hr: { fu: 30, han: 1, lm: "none", pt: 10, yk: [{ han: 1, yi: 0, ym: 0 }] },
                ml: [],
                r: 0,
                rc: 0,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 10, "1": -4, "2": -3, "3": -3 },
                scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 0,
            };
            const result = parseRoundEnd(wire);

            expect([result.dealerSeat, result.doraIndicators]).toEqual([3, [40, 44]]);
            expect(() => parseRoundEnd({ ...wire, dl: undefined })).toThrow();
            expect(() => parseRoundEnd({ ...wire, di: undefined })).toThrow();
        });

        it("decodes wire scores (250 -> 25000)", () => {
            const wire = {
                ct: [0],
                di: [40],
                dl: 0,
                hb: 0,
                hr: { fu: 30, han: 1, lm: "none", pt: 10, yk: [{ han: 1, yi: 0, ym: 0 }] },
                ml: [],
                r: 0,
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

        it("reads a yakuman limit with its count and each yaku's, refusing a yakuman limit without its count", () => {
            const yakuman = {
                fu: 0,
                han: 26,
                lm: "yakuman",
                pt: 640,
                yc: 2,
                yk: [{ han: 26, yi: 113, ym: 2 }],
            };
            const wire = {
                ct: [0],
                di: [40],
                dl: 0,
                hb: 0,
                hr: yakuman,
                ml: [],
                r: 0,
                rc: 0,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 640, "1": -320, "2": -160, "3": -160 },
                scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 0,
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
            expect(() => parseRoundEnd({ ...wire, hr: { ...yakuman, yc: undefined } })).toThrow(
                "yakuman count",
            );
            expect(() => parseRoundEnd({ ...wire, hr: { ...yakuman, lm: "mangan" } })).toThrow(
                "yakuman count",
            );
        });

        it("parses hand result with yaku array", () => {
            const wire = {
                ct: [0, 4],
                di: [40],
                dl: 0,
                hb: 0,
                hr: {
                    fu: 40,
                    han: 4,
                    lm: "none",
                    pt: 40,
                    yk: [
                        { han: 1, yi: 0, ym: 0 },
                        { han: 1, yi: 1, ym: 0 },
                        { han: 2, yi: 7, ym: 0 },
                    ],
                },
                ml: [],
                r: 0,
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
                ct: [0],
                di: [40],
                dl: 0,
                hb: 3,
                hr: { fu: 30, han: 13, lm: "none", pt: 130, yk: [{ han: 13, yi: 40, ym: 0 }] },
                ml: [6100],
                pl: { hb: true, sh: "all", yk: [103] },
                ps: 2,
                r: 0,
                rc: 0,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 320, "1": 0, "2": 0, "3": 0 },
                scs: { "0": 570, "1": 250, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("pao", {
                paysHonba: true,
                seat: 2,
                share: "all",
                yakuIds: [103],
            });
            expect(result).toHaveProperty("honbaBonus", 300);
            expect(() => parseRoundEnd({ ...wire, pl: undefined })).toThrow("liable seat");
            expect(() => parseRoundEnd({ ...wire, ps: undefined })).toThrow("liable seat");
            expect(() => parseRoundEnd({ ...wire, hb: undefined })).toThrow();
        });

        it("reads no pao without a liable seat", () => {
            const wire = {
                ct: [0],
                di: [40],
                dl: 0,
                hb: 0,
                hr: { fu: 30, han: 1, lm: "none", pt: 10, yk: [{ han: 1, yi: 0, ym: 0 }] },
                ml: [],
                r: 0,
                rc: 0,
                rt: ROUND_RESULT_TYPE.TSUMO,
                sch: { "0": 10, "1": 0, "2": 0, "3": 0 },
                scs: { "0": 260, "1": 250, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("pao", null);
        });

        it("includes ura dora indicators when present", () => {
            const wire = {
                ct: [0, 4],
                di: [40],
                dl: 0,
                hb: 0,
                hr: { fu: 30, han: 2, lm: "none", pt: 20, yk: [{ han: 2, yi: 7, ym: 0 }] },
                ml: [],
                r: 0,
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
                di: [40],
                dl: 0,
                hb: 0,
                hr: { fu: 30, han: 1, lm: "none", pt: 10, yk: [{ han: 1, yi: 0, ym: 0 }] },
                ml: [],
                r: 0,
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
                di: [40],
                dl: 0,
                r: 0,
                rt: ROUND_RESULT_TYPE.TSUMO,
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
            };
            expect(() => parseRoundEnd(wire)).toThrow();
        });
    });

    it("decodes a winner's added kan with the tile its seat added from hand", () => {
        const addedKanOf1p = 22_457;
        const tsumo = {
            ct: [0],
            di: [40],
            dl: 0,
            hb: 0,
            hr: { fu: 30, han: 1, lm: "none", pt: 10, yk: [{ han: 1, yi: 0, ym: 0 }] },
            ml: [addedKanOf1p],
            r: 0,
            rc: 0,
            rt: ROUND_RESULT_TYPE.TSUMO,
            sch: { "0": 0, "1": 10, "2": 0, "3": 0 },
            scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
            t: EVENT_TYPE.ROUND_END,
            ws: 1,
            wt: 0,
        };

        expect(parseRoundEnd(tsumo)).toMatchObject({
            melds: [{ addedTileId: 39, calledTileId: 38, meldType: "added_kan" }],
        });
    });

    it("refuses a meld its hand's seat did not call, a winner's or a tenpai hand's", () => {
        const seat0Meld = 6100;
        const tsumo = {
            ct: [0],
            di: [40],
            dl: 0,
            hb: 0,
            hr: { fu: 30, han: 1, lm: "none", pt: 10, yk: [{ han: 1, yi: 0, ym: 0 }] },
            ml: [seat0Meld],
            r: 0,
            rc: 0,
            rt: ROUND_RESULT_TYPE.TSUMO,
            sch: { "0": 0, "1": 10, "2": 0, "3": 0 },
            scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
            t: EVENT_TYPE.ROUND_END,
            ws: 1,
            wt: 0,
        };
        const draw = {
            di: [40],
            dl: 0,
            ns: [0, 2, 3],
            r: 0,
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
                di: [40],
                dl: 0,
                hb: 0,
                hr: {
                    fu: 30,
                    han: 3,
                    lm: "none",
                    pt: 30,
                    yk: [
                        { han: 1, yi: 0, ym: 0 },
                        { han: 2, yi: 7, ym: 0 },
                    ],
                },
                ls: 1,
                ml: [],
                r: 0,
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

        it("reads the liable seat with its half share", () => {
            const wire = {
                ct: [0],
                di: [40],
                dl: 0,
                hb: 0,
                hr: { fu: 30, han: 13, lm: "none", pt: 130, yk: [{ han: 13, yi: 40, ym: 0 }] },
                ls: 2,
                ml: [6100],
                pl: { hb: false, sh: "half", yk: [111] },
                ps: 3,
                r: 0,
                rc: 0,
                rt: ROUND_RESULT_TYPE.RON,
                sch: { "0": 320, "1": 0, "2": -320, "3": 0 },
                scs: { "0": 570, "1": 250, "2": 180, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("pao", {
                paysHonba: false,
                seat: 3,
                share: "half",
                yakuIds: [111],
            });
        });

        it("reads no pao without a liable seat", () => {
            const wire = {
                ct: [0],
                di: [40],
                dl: 0,
                hb: 0,
                hr: { fu: 30, han: 1, lm: "none", pt: 10, yk: [{ han: 1, yi: 0, ym: 0 }] },
                ls: 1,
                ml: [],
                r: 0,
                rc: 0,
                rt: ROUND_RESULT_TYPE.RON,
                sch: { "0": 10, "1": -10, "2": 0, "3": 0 },
                scs: { "0": 260, "1": 240, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 0,
            };
            const result = parseRoundEnd(wire);
            expect(result).toHaveProperty("pao", null);
        });

        it("includes ura dora indicators when present", () => {
            const wire = {
                ct: [0],
                di: [40],
                dl: 0,
                hb: 0,
                hr: { fu: 30, han: 2, lm: "none", pt: 20, yk: [{ han: 2, yi: 7, ym: 0 }] },
                ls: 1,
                ml: [],
                r: 0,
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
                di: [40],
                dl: 0,
                hb: 0,
                hr: { fu: 30, han: 2, lm: "none", pt: 20, yk: [{ han: 1, yi: 3, ym: 0 }] },
                ls: 1,
                ml: [],
                r: 0,
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
            di: [40],
            dl: 0,
            ls: 3,
            r: 0,
            rt: ROUND_RESULT_TYPE.DOUBLE_RON,
            sch: { "0": 40, "1": 30, "2": 0, "3": -70 },
            scs: { "0": 290, "1": 280, "2": 250, "3": 180 },
            t: EVENT_TYPE.ROUND_END,
            wn: [
                {
                    ct: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44],
                    hb: 0,
                    hr: {
                        fu: 30,
                        han: 3,
                        lm: "none",
                        pt: 30,
                        yk: [
                            { han: 1, yi: 0, ym: 0 },
                            { han: 2, yi: 7, ym: 0 },
                        ],
                    },
                    ml: [],
                    rc: 1,
                    sch: { "0": 40, "1": 0, "2": 0, "3": -40 },
                    ws: 0,
                },
                {
                    ct: [52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96],
                    hb: 0,
                    hr: { fu: 30, han: 2, lm: "none", pt: 20, yk: [{ han: 2, yi: 7, ym: 0 }] },
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
                di: [40],
                dl: 0,
                ls: 2,
                r: 0,
                rt: ROUND_RESULT_TYPE.DOUBLE_RON,
                sch: { "0": 160, "1": 160, "2": -320, "3": 0 },
                scs: { "0": 410, "1": 410, "2": -70, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
                wn: [
                    {
                        ct: [0],
                        hb: 3,
                        hr: {
                            fu: 30,
                            han: 13,
                            lm: "none",
                            pt: 130,
                            yk: [{ han: 13, yi: 40, ym: 0 }],
                        },
                        ml: [6100],
                        pl: { hb: true, sh: "half", yk: [103] },
                        ps: 2,
                        rc: 0,
                        sch: { "0": 160, "1": 0, "2": -160, "3": 0 },
                        ud: [56],
                        ws: 0,
                    },
                    {
                        ct: [52],
                        hb: 0,
                        hr: {
                            fu: 30,
                            han: 13,
                            lm: "none",
                            pt: 130,
                            yk: [{ han: 13, yi: 41, ym: 0 }],
                        },
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
            expect([result.winners[0].pao?.seat, result.winners[0].honbaBonus]).toEqual([2, 300]);
            expect(result.winners[0].uraDoraIndicators).toEqual([56]);
            expect([result.winners[1].pao, result.winners[1].honbaBonus]).toEqual([null, 0]);
            expect(result.winners[1].uraDoraIndicators).toBeNull();
        });
    });

    describe("exhaustive draw (rt=3)", () => {
        it("parses exhaustive draw with tenpai and noten seats", () => {
            const wire = {
                di: [40],
                dl: 0,
                ns: [2, 3],
                r: 0,
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
                di: [40],
                dl: 0,
                ns: [1, 2, 3],
                r: 0,
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
            expect(result.tenpaiHands[0].melds.map((meld) => meld.meldType)).toEqual([
                "chi",
                "chi",
                "chi",
            ]);
        });

        it("reads the wait id and timeout of the round advance it opens, null without one, and refuses half of them", () => {
            const wire = {
                di: [40],
                dl: 0,
                ns: [1],
                r: 0,
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
                di: [40],
                dl: 0,
                ns: [1],
                r: 0,
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
        it("reads the riichi sticks the draw leaves on the table, and refuses a round end that names none", () => {
            const wire = {
                di: [40],
                dl: 0,
                r: 4,
                rn: ABORTIVE_DRAW_TYPE.FOUR_RIICHI,
                rt: ROUND_RESULT_TYPE.ABORTIVE_DRAW,
                sch: { "0": 0, "1": 0, "2": 0, "3": 0 },
                scs: { "0": 240, "1": 240, "2": 240, "3": 240 },
                t: EVENT_TYPE.ROUND_END,
            };
            const { r: _left, ...unnamed } = wire;

            expect(parseRoundEnd(wire).riichiSticks).toBe(4);
            expect(() => parseRoundEnd(unnamed)).toThrow();
        });

        it("parses abortive draw with reason string", () => {
            const wire = {
                di: [40],
                dl: 0,
                r: 0,
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
                di: [40],
                dl: 0,
                r: 0,
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
                di: [40],
                dl: 0,
                r: 0,
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
                di: [40],
                dl: 0,
                r: 0,
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
        it("parses nagashi mangan with its qualifying seats and their rivers", () => {
            const wire = {
                di: [40],
                dl: 0,
                ns: [2, 3],
                qr: [{ dsc: [{ ti: 0 }, { rd: true, tg: true, ti: 132 }], s: 0 }],
                qs: [0],
                r: 0,
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
            expect(result.tenpaiSeats).toEqual([0, 1]);
            expect(result.notenSeats).toEqual([2, 3]);
            expect(result.tenpaiHands).toHaveLength(2);
        });
    });

    it("refuses a nagashi mangan that names a qualifying seat without its river", () => {
        const wire = {
            di: [40],
            dl: 0,
            ns: [1, 2, 3],
            qr: [],
            qs: [0],
            r: 0,
            rt: ROUND_RESULT_TYPE.NAGASHI_MANGAN,
            sch: { "0": 120, "1": -40, "2": -40, "3": -40 },
            scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
            t: EVENT_TYPE.ROUND_END,
            th: [],
            ts: [],
        };

        expect(() => parseRoundEnd(wire)).toThrow("river of each qualifying seat");
    });

    describe("unknown result type", () => {
        it("throws on unknown rt value", () => {
            const wire = {
                di: [40],
                dl: 0,
                rt: 99,
                scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
                t: EVENT_TYPE.ROUND_END,
            };
            expect(() => parseRoundEnd(wire)).toThrow("Unknown round result type: rt=99");
        });
    });
});
