import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import { createInitialPlayerState } from "@/entities/table/model/initial-state";
import {
    type PlayerState,
    type RoundEndResult,
    type WinnerResult,
} from "@/entities/table/model/types";
import { RoundEndDisplay } from "@/entities/table/ui/round-end-display";
import { ROUND_RESULT_TYPE } from "@/shared/protocol";

function renderTo(template: TemplateResult): HTMLElement {
    const el = document.createElement("div");
    render(template, el);
    return el;
}

function makePlayers(): PlayerState[] {
    return [
        createInitialPlayerState({ isAiPlayer: false, name: "Alice", score: 25000, seat: 0 }),
        createInitialPlayerState({ isAiPlayer: true, name: "Bot-1", score: 25000, seat: 1 }),
        createInitialPlayerState({ isAiPlayer: true, name: "Bot-2", score: 25000, seat: 2 }),
        createInitialPlayerState({ isAiPlayer: false, name: "Bob", score: 25000, seat: 3 }),
    ];
}

function makeWinner(overrides?: Partial<WinnerResult>): WinnerResult {
    return {
        closedTiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        handResult: {
            fu: 30,
            han: 4,
            yaku: [
                { han: 1, yakuId: 1 },
                { han: 1, yakuId: 12 },
                { han: 1, yakuId: 0 },
                { han: 1, yakuId: 120 },
            ],
        },
        melds: [],
        seat: 0,
        winningTile: 52,
        ...overrides,
    };
}

function makeTsumoResult(overrides?: Partial<RoundEndResult>): RoundEndResult {
    return {
        doraIndicators: [16],
        resultType: ROUND_RESULT_TYPE.TSUMO,
        scoreChanges: { "0": 10000, "1": -3000, "2": -3000, "3": -4000 },
        uraDoraIndicators: [],
        winners: [makeWinner()],
        ...overrides,
    };
}

describe("RoundEndDisplay", () => {
    describe("winner name and wind", () => {
        test("renders winner name with wind when dealer is seat 0", () => {
            const el = renderTo(RoundEndDisplay(makeTsumoResult(), makePlayers(), 0));
            const winnerName = el.querySelector(".round-end-result__winner-name");
            expect(winnerName?.textContent).toBe("Alice (East)");
        });

        test("falls back to seat label when player not found", () => {
            const result = makeTsumoResult({ winners: [makeWinner({ seat: 99 })] });
            const el = renderTo(RoundEndDisplay(result, makePlayers(), 0));
            const winnerName = el.querySelector(".round-end-result__winner-name");
            expect(winnerName?.textContent).toContain("Seat 99");
        });

        test("renders correct wind relative to dealer position", () => {
            const result = makeTsumoResult({ winners: [makeWinner({ seat: 0 })] });
            const el = renderTo(RoundEndDisplay(result, makePlayers(), 2));
            const winnerName = el.querySelector(".round-end-result__winner-name");
            expect(winnerName?.textContent).toBe("Alice (West)");
        });
    });

    describe("hand and melds", () => {
        test("renders melds decoded from IMME-encoded integers", () => {
            const ponImme = 16128; // pon of 1m, caller seat 0
            const result = makeTsumoResult({
                winners: [makeWinner({ melds: [ponImme] })],
            });
            const el = renderTo(RoundEndDisplay(result, makePlayers(), 0));
            const hand = el.querySelector(".round-end-result__hand");
            const meldElements = hand!.querySelectorAll(".meld");
            expect(meldElements).toHaveLength(1);
        });

        test("renders added_kan as open_kan (4 tiles with sideways)", () => {
            const addedKanImme = 21024; // added_kan of 1m, caller seat 0
            const result = makeTsumoResult({
                winners: [makeWinner({ melds: [addedKanImme] })],
            });
            const el = renderTo(RoundEndDisplay(result, makePlayers(), 0));
            const hand = el.querySelector(".round-end-result__hand");
            const meldTiles = hand!.querySelectorAll(".meld .tile");
            expect(meldTiles.length).toBe(4);
        });

        test("throws on invalid IMME-encoded melds", () => {
            const invalidImme = 999999; // out of IMME range
            const validPonImme = 16128; // valid pon of 1m
            const result = makeTsumoResult({
                winners: [makeWinner({ melds: [invalidImme, validPonImme] })],
            });
            expect(() => RoundEndDisplay(result, makePlayers(), 0)).toThrow(
                "IMME value must be 0-24423, got 999999",
            );
        });

        test("renders hand tiles and winning tile with gap", () => {
            const el = renderTo(RoundEndDisplay(makeTsumoResult(), makePlayers(), 0));
            const hand = el.querySelector(".round-end-result__hand");
            expect(hand).not.toBeNull();
            const drawnGap = hand!.querySelector(".hand-drawn-gap");
            expect(drawnGap).not.toBeNull();
        });
    });

    describe("yaku and totals", () => {
        test("renders correct number of yaku entries", () => {
            const result = makeTsumoResult();
            const el = renderTo(RoundEndDisplay(result, makePlayers(), 0));
            const yakuItems = el.querySelectorAll(".round-end-result__yaku-item");
            expect(yakuItems).toHaveLength(4);
        });

        test("renders yaku names and han values", () => {
            const result = makeTsumoResult({
                winners: [
                    makeWinner({
                        handResult: {
                            fu: 30,
                            han: 2,
                            yaku: [
                                { han: 1, yakuId: 1 },
                                { han: 1, yakuId: 13 },
                            ],
                        },
                    }),
                ],
            });
            const el = renderTo(RoundEndDisplay(result, makePlayers(), 0));
            const yakuItems = el.querySelectorAll(".round-end-result__yaku-item");
            expect(yakuItems[0].textContent).toContain("Riichi");
            expect(yakuItems[0].textContent).toContain("1 han");
            expect(yakuItems[1].textContent).toContain("Tanyao");
            expect(yakuItems[1].textContent).toContain("1 han");
        });

        test("renders han and fu totals", () => {
            const el = renderTo(RoundEndDisplay(makeTsumoResult(), makePlayers(), 0));
            const totals = el.querySelector(".round-end-result__totals");
            expect(totals?.textContent).toContain("4 han / 30 fu");
        });

        test("renders Yakuman for han >= 13", () => {
            const result = makeTsumoResult({
                winners: [
                    makeWinner({
                        handResult: {
                            fu: 0,
                            han: 13,
                            yaku: [{ han: 13, yakuId: 102 }],
                        },
                    }),
                ],
            });
            const el = renderTo(RoundEndDisplay(result, makePlayers(), 0));
            const totals = el.querySelector(".round-end-result__totals");
            expect(totals?.textContent).toContain("Yakuman");
        });

        test("renders Double Yakuman for han >= 26", () => {
            const result = makeTsumoResult({
                winners: [
                    makeWinner({
                        handResult: {
                            fu: 0,
                            han: 26,
                            yaku: [{ han: 26, yakuId: 113 }],
                        },
                    }),
                ],
            });
            const el = renderTo(RoundEndDisplay(result, makePlayers(), 0));
            const totals = el.querySelector(".round-end-result__totals");
            expect(totals?.textContent).toContain("Double Yakuman");
        });

        test("renders Triple Yakuman for han >= 39", () => {
            const result = makeTsumoResult({
                winners: [
                    makeWinner({
                        handResult: {
                            fu: 0,
                            han: 39,
                            yaku: [
                                { han: 26, yakuId: 115 },
                                { han: 13, yakuId: 110 },
                            ],
                        },
                    }),
                ],
            });
            const el = renderTo(RoundEndDisplay(result, makePlayers(), 0));
            const totals = el.querySelector(".round-end-result__totals");
            expect(totals?.textContent).toContain("Triple Yakuman");
        });

        test("double ron renders two winner sections", () => {
            const result: RoundEndResult = {
                doraIndicators: [],
                loserSeat: 1,
                resultType: ROUND_RESULT_TYPE.DOUBLE_RON,
                scoreChanges: { "0": 8000, "1": -16000, "2": 8000, "3": 0 },
                uraDoraIndicators: [],
                winners: [
                    makeWinner({ seat: 0 }),
                    makeWinner({
                        closedTiles: [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38],
                        handResult: {
                            fu: 30,
                            han: 3,
                            yaku: [
                                { han: 1, yakuId: 12 },
                                { han: 1, yakuId: 13 },
                                { han: 1, yakuId: 120 },
                            ],
                        },
                        seat: 2,
                    }),
                ],
            };
            const el = renderTo(RoundEndDisplay(result, makePlayers(), 0));
            const winnerSections = el.querySelectorAll(".round-end-result__winner");
            expect(winnerSections).toHaveLength(2);

            const winnerNames = el.querySelectorAll(".round-end-result__winner-name");
            expect(winnerNames[0].textContent).toBe("Alice (East)");
            expect(winnerNames[1].textContent).toBe("Bot-2 (West)");
        });
    });

    describe("score changes", () => {
        test("renders score change rows for all players", () => {
            const el = renderTo(RoundEndDisplay(makeTsumoResult(), makePlayers(), 0));
            const scoreRows = el.querySelectorAll(".round-end-result__score-row");
            expect(scoreRows).toHaveLength(4);

            const names = el.querySelectorAll(".round-end-result__score-name");
            expect(names[0].textContent).toBe("Alice");
            expect(names[1].textContent).toBe("Bot-1");
            expect(names[2].textContent).toBe("Bot-2");
            expect(names[3].textContent).toBe("Bob");
        });

        test("renders score deltas with correct signs", () => {
            const el = renderTo(RoundEndDisplay(makeTsumoResult(), makePlayers(), 0));
            const deltas = el.querySelectorAll(".round-end-result__score-delta");
            expect(deltas[0].textContent).toBe("+10,000");
            expect(deltas[1].textContent).toBe("\u22123,000");
            expect(deltas[2].textContent).toBe("\u22123,000");
            expect(deltas[3].textContent).toBe("\u22124,000");
        });

        test("renders zero delta for players with no score change", () => {
            const result = makeTsumoResult({
                scoreChanges: { "0": 8000, "1": -8000 },
            });
            const el = renderTo(RoundEndDisplay(result, makePlayers(), 0));
            const deltas = el.querySelectorAll(".round-end-result__score-delta");
            expect(deltas[2].textContent).toBe("0");
            expect(deltas[3].textContent).toBe("0");
        });
    });

    describe("dora indicators", () => {
        test("renders dora indicator tiles", () => {
            const result = makeTsumoResult({ doraIndicators: [16, 56] });
            const el = renderTo(RoundEndDisplay(result, makePlayers(), 0));
            const rows = el.querySelectorAll(".round-end-result__indicator-group");
            expect(rows).toHaveLength(1);
            expect(rows[0].querySelector(".round-end-result__indicator-label")?.textContent).toBe(
                "Dora",
            );
            expect(rows[0].querySelectorAll(".round-end-result__indicator-tile")).toHaveLength(2);
        });

        test("renders ura dora indicator tiles", () => {
            const result = makeTsumoResult({ uraDoraIndicators: [28] });
            const el = renderTo(RoundEndDisplay(result, makePlayers(), 0));
            const rows = el.querySelectorAll(".round-end-result__indicator-group");
            expect(rows).toHaveLength(2);
            expect(rows[1].querySelector(".round-end-result__indicator-label")?.textContent).toBe(
                "Ura",
            );
            expect(rows[1].querySelectorAll(".round-end-result__indicator-tile")).toHaveLength(1);
        });

        test("hides indicator section when no dora indicators", () => {
            const result = makeTsumoResult({ doraIndicators: [], uraDoraIndicators: [] });
            const el = renderTo(RoundEndDisplay(result, makePlayers(), 0));
            const indicators = el.querySelector(".round-end-result__indicators");
            expect(indicators).toBeNull();
        });
    });
});
