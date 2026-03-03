import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import {
    createInitialPlayerState,
    createInitialTableState,
} from "@/entities/table/model/initial-state";
import {
    type GameEndResult,
    type RoundEndResult,
    type TableState,
} from "@/entities/table/model/types";
import { StateDisplay } from "@/entities/table/ui/state-display";
import { ROUND_RESULT_TYPE } from "@/shared/protocol";

function renderTo(template: TemplateResult): HTMLElement {
    const el = document.createElement("div");
    render(template, el);
    return el;
}

function makeState(overrides: Partial<TableState> = {}): TableState {
    const base = createInitialTableState();
    base.players = [
        createInitialPlayerState({ isAiPlayer: false, name: "Alice", score: 25000, seat: 0 }),
        createInitialPlayerState({ isAiPlayer: true, name: "Bob", score: 25000, seat: 1 }),
        createInitialPlayerState({ isAiPlayer: false, name: "Carol", score: 25000, seat: 2 }),
        createInitialPlayerState({ isAiPlayer: true, name: "Dave", score: 25000, seat: 3 }),
    ];
    return { ...base, ...overrides };
}

describe("StateDisplay", () => {
    describe("layout and player panels", () => {
        test("renders 4 player panels", () => {
            const el = renderTo(StateDisplay(makeState()));
            const panels = el.querySelectorAll(".player-panel");
            expect(panels).toHaveLength(4);
        });

        test("renders table info bar", () => {
            const el = renderTo(StateDisplay(makeState()));
            expect(el.querySelector(".table-info")).not.toBeNull();
        });

        test("dealer badge appears on correct player", () => {
            const el = renderTo(StateDisplay(makeState({ dealerSeat: 2 })));
            const panels = el.querySelectorAll(".player-panel");
            // Seat 2 (Carol) should have dealer badge
            expect(panels[2]?.querySelector(".player-panel__badge--dealer")?.textContent).toBe(
                "Dealer",
            );
            // Other seats should not
            expect(panels[0]?.querySelector(".player-panel__badge--dealer")).toBeNull();
            expect(panels[1]?.querySelector(".player-panel__badge--dealer")).toBeNull();
            expect(panels[3]?.querySelector(".player-panel__badge--dealer")).toBeNull();
        });

        test("current-turn indicator matches currentPlayerSeat", () => {
            const el = renderTo(StateDisplay(makeState({ currentPlayerSeat: 1 })));
            const panels = el.querySelectorAll(".player-panel");
            // Seat 1 (Bob) should have current class
            expect(panels[1]?.classList.contains("player-panel--current")).toBe(true);
            // Others should not
            expect(panels[0]?.classList.contains("player-panel--current")).toBe(false);
            expect(panels[2]?.classList.contains("player-panel--current")).toBe(false);
            expect(panels[3]?.classList.contains("player-panel--current")).toBe(false);
        });

        test("dealer and current-turn can be on different players", () => {
            const el = renderTo(StateDisplay(makeState({ currentPlayerSeat: 3, dealerSeat: 0 })));
            const panels = el.querySelectorAll(".player-panel");
            // Seat 0 is dealer
            expect(panels[0]?.querySelector(".player-panel__badge--dealer")?.textContent).toBe(
                "Dealer",
            );
            expect(panels[0]?.classList.contains("player-panel--current")).toBe(false);
            // Seat 3 is current
            expect(panels[3]?.classList.contains("player-panel--current")).toBe(true);
            expect(panels[3]?.querySelector(".player-panel__badge--dealer")).toBeNull();
        });

        test("wraps players in state-display__players container", () => {
            const el = renderTo(StateDisplay(makeState()));
            const container = el.querySelector(".state-display__players");
            expect(container).not.toBeNull();
            expect(container?.querySelectorAll(".player-panel")).toHaveLength(4);
        });
    });

    describe("result panels", () => {
        test("renders round-end result panel when phase is round_ended with winners", () => {
            const roundEndResult: RoundEndResult = {
                resultType: ROUND_RESULT_TYPE.TSUMO,
                scoreChanges: { "0": 1000, "1": -500, "2": -300, "3": -200 },
                winners: [
                    {
                        closedTiles: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
                        handResult: { fu: 30, han: 1, yaku: [{ han: 1, yakuId: 0 }] },
                        melds: [],
                        seat: 0,
                        winningTile: 52,
                    },
                ],
            };
            const el = renderTo(StateDisplay(makeState({ phase: "round_ended", roundEndResult })));
            expect(el.querySelector(".round-end-result")).not.toBeNull();
        });

        test("renders round-end result panel for draws showing score changes", () => {
            const roundEndResult: RoundEndResult = {
                resultType: ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW,
                scoreChanges: { "0": 1000, "1": -1000, "2": 0, "3": 0 },
                winners: [],
            };
            const el = renderTo(StateDisplay(makeState({ phase: "round_ended", roundEndResult })));
            expect(el.querySelector(".round-end-result")).not.toBeNull();
            expect(el.querySelector(".round-end-result__scores")).not.toBeNull();
        });

        test("renders game-end result panel when phase is game_ended", () => {
            const gameEndResult: GameEndResult = {
                standings: [
                    { finalScore: 42.0, score: 35000, seat: 0 },
                    { finalScore: 12.0, score: 28000, seat: 1 },
                    { finalScore: -18.0, score: 22000, seat: 2 },
                    { finalScore: -36.0, score: 15000, seat: 3 },
                ],
                winnerSeat: 0,
            };
            const el = renderTo(StateDisplay(makeState({ gameEndResult, phase: "game_ended" })));
            expect(el.querySelector(".game-end-result")).not.toBeNull();
        });

        test("does not render round-end panel when roundEndResult is null", () => {
            const el = renderTo(
                StateDisplay(makeState({ phase: "round_ended", roundEndResult: null })),
            );
            expect(el.querySelector(".round-end-result")).toBeNull();
        });

        test("does not render result panels during normal play", () => {
            const el = renderTo(StateDisplay(makeState({ phase: "in_round" })));
            expect(el.querySelector(".round-end-result")).toBeNull();
            expect(el.querySelector(".game-end-result")).toBeNull();
        });
    });
});
