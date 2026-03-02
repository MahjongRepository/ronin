import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import {
    createInitialPlayerState,
    createInitialTableState,
} from "@/entities/table/model/initial-state";
import { type TableState } from "@/entities/table/model/types";
import { TableInfo } from "@/entities/table/ui/table-info";

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

describe("TableInfo", () => {
    test("displays round wind and number", () => {
        const el = renderTo(TableInfo(makeState({ roundNumber: 1, roundWind: 0 })));
        const round = el.querySelector(".table-info__round");
        expect(round?.textContent).toBe("East 1");
    });

    test("displays south wind", () => {
        const el = renderTo(TableInfo(makeState({ roundNumber: 3, roundWind: 1 })));
        const round = el.querySelector(".table-info__round");
        expect(round?.textContent).toBe("South 3");
    });

    test("displays dealer name from seat index", () => {
        const el = renderTo(TableInfo(makeState({ dealerSeat: 2 })));
        const dealer = el.querySelector(".table-info__dealer");
        expect(dealer?.textContent).toBe("Dealer: Carol");
    });

    test("renders dora indicator tiles", () => {
        // tileId 0 = 1m, tileId 36 = 1p
        const el = renderTo(TableInfo(makeState({ doraIndicators: [0, 36] })));
        const doraTiles = el.querySelectorAll(".table-info__dora-tile");
        expect(doraTiles).toHaveLength(2);
        const uses = el.querySelectorAll(".table-info__dora-tile use");
        expect(uses[0]?.getAttribute("href")).toBe("#tile-1m");
        expect(uses[1]?.getAttribute("href")).toBe("#tile-1p");
    });

    test("renders empty dora section when no indicators", () => {
        const el = renderTo(TableInfo(makeState({ doraIndicators: [] })));
        const doraTiles = el.querySelectorAll(".table-info__dora-tile");
        expect(doraTiles).toHaveLength(0);
    });

    test("displays honba and riichi stick counts", () => {
        const el = renderTo(TableInfo(makeState({ honbaSticks: 3, riichiSticks: 2 })));
        const sticks = el.querySelector(".table-info__sticks");
        expect(sticks?.textContent).toContain("Honba: 3");
        expect(sticks?.textContent).toContain("Riichi: 2");
    });
});
