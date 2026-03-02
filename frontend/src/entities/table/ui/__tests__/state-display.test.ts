import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import {
    createInitialPlayerState,
    createInitialTableState,
} from "@/entities/table/model/initial-state";
import { type TableState } from "@/entities/table/model/types";
import { StateDisplay } from "@/entities/table/ui/state-display";

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
