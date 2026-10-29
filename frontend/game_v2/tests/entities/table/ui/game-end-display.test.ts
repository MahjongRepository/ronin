import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import { createInitialPlayerState } from "@/entities/table/model/initial-state";
import { type GameEndResult, type PlayerState } from "@/entities/table/model/types";
import { GameEndDisplay } from "@/entities/table/ui/game-end-display";

function renderTo(template: TemplateResult): HTMLElement {
    const el = document.createElement("div");
    render(template, el);
    return el;
}

function makePlayers(): PlayerState[] {
    return [
        createInitialPlayerState({ isAiPlayer: false, name: "Alice", score: 35_000, seat: 0 }),
        createInitialPlayerState({ isAiPlayer: true, name: "Bot-1", score: 28_000, seat: 1 }),
        createInitialPlayerState({ isAiPlayer: true, name: "Bot-2", score: 22_000, seat: 2 }),
        createInitialPlayerState({ isAiPlayer: false, name: "Bob", score: 15_000, seat: 3 }),
    ];
}

function makeGameEndResult(overrides?: Partial<GameEndResult>): GameEndResult {
    return {
        leftoverRiichiBonus: 0,
        standings: [
            { finalScore: 42, score: 35_000, seat: 0 },
            { finalScore: 12, score: 28_000, seat: 1 },
            { finalScore: -18, score: 22_000, seat: 2 },
            { finalScore: -36, score: 15_000, seat: 3 },
        ],
        winnerSeat: 0,
        ...overrides,
    };
}

describe("GameEndDisplay", () => {
    test("renders all 4 players", () => {
        const el = renderTo(GameEndDisplay(makeGameEndResult(), makePlayers()));
        const rows = el.querySelectorAll(".game-end-result__row");
        expect(rows).toHaveLength(4);
    });

    test("standings names preserve input order (not re-sorted)", () => {
        const result = makeGameEndResult({
            standings: [
                { finalScore: 42, score: 35_000, seat: 2 },
                { finalScore: 12, score: 28_000, seat: 0 },
                { finalScore: -18, score: 22_000, seat: 3 },
                { finalScore: -36, score: 15_000, seat: 1 },
            ],
        });
        const el = renderTo(GameEndDisplay(result, makePlayers()));
        const names = el.querySelectorAll(".game-end-result__name");
        expect(names[0].textContent).toBe("Bot-2");
        expect(names[1].textContent).toBe("Alice");
        expect(names[2].textContent).toBe("Bob");
        expect(names[3].textContent).toBe("Bot-1");
    });

    test("standings ranks are derived from array index", () => {
        const result = makeGameEndResult({
            standings: [
                { finalScore: 42, score: 35_000, seat: 2 },
                { finalScore: 12, score: 28_000, seat: 0 },
                { finalScore: -18, score: 22_000, seat: 3 },
                { finalScore: -36, score: 15_000, seat: 1 },
            ],
        });
        const el = renderTo(GameEndDisplay(result, makePlayers()));
        const ranks = el.querySelectorAll(".game-end-result__rank");
        expect(ranks[0].textContent).toBe("1.");
        expect(ranks[1].textContent).toBe("2.");
        expect(ranks[2].textContent).toBe("3.");
        expect(ranks[3].textContent).toBe("4.");
    });

    test("final scores show correct sign and format", () => {
        const el = renderTo(GameEndDisplay(makeGameEndResult(), makePlayers()));
        const finalScores = el.querySelectorAll(".game-end-result__final-score");
        expect(finalScores[0].textContent).toBe("+42.0");
        expect(finalScores[1].textContent).toBe("+12.0");
        expect(finalScores[2].textContent).toBe("\u221218.0");
        expect(finalScores[3].textContent).toBe("\u221236.0");
    });

    test("zero final score has no sign prefix", () => {
        const result = makeGameEndResult({
            standings: [
                { finalScore: 0, score: 25_000, seat: 0 },
                { finalScore: 0, score: 25_000, seat: 1 },
                { finalScore: 0, score: 25_000, seat: 2 },
                { finalScore: 0, score: 25_000, seat: 3 },
            ],
        });
        const el = renderTo(GameEndDisplay(result, makePlayers()));
        const finalScores = el.querySelectorAll(".game-end-result__final-score");
        expect(finalScores[0].textContent).toBe("0.0");
    });

    test("player names are looked up from players array", () => {
        const el = renderTo(GameEndDisplay(makeGameEndResult(), makePlayers()));
        const names = el.querySelectorAll(".game-end-result__name");
        expect(names[0].textContent).toBe("Alice");
        expect(names[1].textContent).toBe("Bot-1");
        expect(names[2].textContent).toBe("Bot-2");
        expect(names[3].textContent).toBe("Bob");
    });

    test("falls back to seat label when player not found", () => {
        const result = makeGameEndResult({
            standings: [{ finalScore: 10, score: 25_000, seat: 99 }],
        });
        const el = renderTo(GameEndDisplay(result, makePlayers()));
        const names = el.querySelectorAll(".game-end-result__name");
        expect(names[0].textContent).toBe("Seat 99");
    });

    test("raw scores are plain numbers", () => {
        const el = renderTo(GameEndDisplay(makeGameEndResult(), makePlayers()));
        const scores = el.querySelectorAll(".game-end-result__score");
        expect(scores[0].textContent).toBe("35000");
        expect(scores[3].textContent).toBe("15000");
    });

    test("names the leftover riichi sticks the winner's score holds, and nothing when none were left", () => {
        const withSticks = renderTo(
            GameEndDisplay(makeGameEndResult({ leftoverRiichiBonus: 2000 }), makePlayers()),
        );
        const without = renderTo(GameEndDisplay(makeGameEndResult(), makePlayers()));

        expect(withSticks.querySelector(".game-end-result__leftover")?.textContent?.trim()).toBe(
            "Leftover riichi sticks: +2,000 to Alice",
        );
        expect(without.querySelector(".game-end-result__leftover")).toBeNull();
    });

    test("renders Final Standings title", () => {
        const el = renderTo(GameEndDisplay(makeGameEndResult(), makePlayers()));
        const title = el.querySelector(".game-end-result__title");
        expect(title?.textContent).toBe("Final Standings");
    });
});
