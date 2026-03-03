import { render } from "lit-html";
import { describe, expect, test, vi } from "vitest";

import { type TurnInfo } from "@/entities/table/model/navigation-index";
import { TurnSelector, findNearestTurn } from "@/entities/table/ui/turn-selector";

function makeTurn(overrides: Partial<TurnInfo> = {}): TurnInfo {
    return {
        actionStepIndex: 5,
        playerName: "Alice",
        turnNumber: 1,
        ...overrides,
    };
}

function renderSelector(
    overrides: {
        currentStep?: number;
        isOpen?: boolean;
        onSelect?: (stepIndex: number) => void;
        onToggle?: () => void;
        turns?: TurnInfo[];
    } = {},
): HTMLElement {
    const el = document.createElement("div");
    render(
        TurnSelector({
            currentStep: overrides.currentStep ?? 0,
            isOpen: overrides.isOpen ?? false,
            onSelect: overrides.onSelect ?? vi.fn(),
            onToggle: overrides.onToggle ?? vi.fn(),
            turns: overrides.turns ?? [],
        }),
        el,
    );
    return el;
}

describe("findNearestTurn", () => {
    test("returns undefined for empty turns", () => {
        expect(findNearestTurn([], 5)).toBeUndefined();
    });

    test("returns the last turn at or before currentStep", () => {
        const turns = [
            makeTurn({ actionStepIndex: 3, turnNumber: 1 }),
            makeTurn({ actionStepIndex: 7, turnNumber: 2 }),
            makeTurn({ actionStepIndex: 11, turnNumber: 3 }),
        ];
        expect(findNearestTurn(turns, 8)).toBe(turns[1]);
    });

    test("returns exact match when currentStep equals a turn step", () => {
        const turns = [
            makeTurn({ actionStepIndex: 3, turnNumber: 1 }),
            makeTurn({ actionStepIndex: 7, turnNumber: 2 }),
        ];
        expect(findNearestTurn(turns, 7)).toBe(turns[1]);
    });

    test("returns undefined when currentStep is before all turns", () => {
        const turns = [
            makeTurn({ actionStepIndex: 5, turnNumber: 1 }),
            makeTurn({ actionStepIndex: 9, turnNumber: 2 }),
        ];
        expect(findNearestTurn(turns, 2)).toBeUndefined();
    });
});

describe("TurnSelector", () => {
    describe("maps turns to correct dropdown items", () => {
        test("renders correct number of items when open", () => {
            const turns = [
                makeTurn({ actionStepIndex: 3, playerName: "Alice", turnNumber: 1 }),
                makeTurn({ actionStepIndex: 7, playerName: "Bob", turnNumber: 2 }),
                makeTurn({ actionStepIndex: 11, playerName: "Carol", turnNumber: 3 }),
            ];
            const el = renderSelector({ currentStep: 3, isOpen: true, turns });
            const items = el.querySelectorAll(".dropdown-select__item");
            expect(items).toHaveLength(3);
        });

        test("renders correct labels with turn number and player name", () => {
            const turns = [
                makeTurn({ actionStepIndex: 3, playerName: "Alice", turnNumber: 1 }),
                makeTurn({ actionStepIndex: 7, playerName: "Bot-1", turnNumber: 2 }),
            ];
            const el = renderSelector({ currentStep: 3, isOpen: true, turns });
            const items = el.querySelectorAll(".dropdown-select__item");
            expect(items[0]?.textContent?.trim()).toBe("Turn 1 \u2014 Alice");
            expect(items[1]?.textContent?.trim()).toBe("Turn 2 \u2014 Bot-1");
        });

        test("calls onSelect with correct step index when item is clicked", () => {
            const onSelect = vi.fn();
            const turns = [
                makeTurn({ actionStepIndex: 3, turnNumber: 1 }),
                makeTurn({ actionStepIndex: 7, turnNumber: 2 }),
            ];
            const el = renderSelector({ currentStep: 3, isOpen: true, onSelect, turns });
            const items = el.querySelectorAll<HTMLButtonElement>(".dropdown-select__item");
            items[1]?.click();
            expect(onSelect).toHaveBeenCalledWith(7);
        });
    });

    describe("nearest turn to current step is highlighted", () => {
        test("highlights the nearest turn at or before currentStep", () => {
            const turns = [
                makeTurn({ actionStepIndex: 3, turnNumber: 1 }),
                makeTurn({ actionStepIndex: 7, turnNumber: 2 }),
                makeTurn({ actionStepIndex: 11, turnNumber: 3 }),
            ];
            const el = renderSelector({ currentStep: 8, isOpen: true, turns });
            const items = el.querySelectorAll(".dropdown-select__item");
            expect(items[0]?.classList.contains("dropdown-select__item--current")).toBe(false);
            expect(items[1]?.classList.contains("dropdown-select__item--current")).toBe(true);
            expect(items[2]?.classList.contains("dropdown-select__item--current")).toBe(false);
        });

        test("highlights exact match turn", () => {
            const turns = [
                makeTurn({ actionStepIndex: 3, turnNumber: 1 }),
                makeTurn({ actionStepIndex: 7, turnNumber: 2 }),
            ];
            const el = renderSelector({ currentStep: 7, isOpen: true, turns });
            const items = el.querySelectorAll(".dropdown-select__item");
            expect(items[0]?.classList.contains("dropdown-select__item--current")).toBe(false);
            expect(items[1]?.classList.contains("dropdown-select__item--current")).toBe(true);
        });

        test("no turn highlighted when currentStep is before all turns", () => {
            const turns = [
                makeTurn({ actionStepIndex: 5, turnNumber: 1 }),
                makeTurn({ actionStepIndex: 9, turnNumber: 2 }),
            ];
            const el = renderSelector({ currentStep: 2, isOpen: true, turns });
            const items = el.querySelectorAll(".dropdown-select__item");
            expect(items[0]?.classList.contains("dropdown-select__item--current")).toBe(false);
            expect(items[1]?.classList.contains("dropdown-select__item--current")).toBe(false);
        });
    });

    describe("trigger label", () => {
        test("shows 'Turns' when no turns available", () => {
            const el = renderSelector({ currentStep: 0, turns: [] });
            const trigger = el.querySelector(".dropdown-select__trigger");
            expect(trigger?.textContent).toBe("Turns");
        });

        test("shows current turn number when a turn is nearest", () => {
            const turns = [
                makeTurn({ actionStepIndex: 3, turnNumber: 1 }),
                makeTurn({ actionStepIndex: 7, turnNumber: 2 }),
            ];
            const el = renderSelector({ currentStep: 8, turns });
            const trigger = el.querySelector(".dropdown-select__trigger");
            expect(trigger?.textContent).toBe("Turn 2");
        });

        test("shows 'Turns' when currentStep is before all turns", () => {
            const turns = [makeTurn({ actionStepIndex: 5, turnNumber: 1 })];
            const el = renderSelector({ currentStep: 2, turns });
            const trigger = el.querySelector(".dropdown-select__trigger");
            expect(trigger?.textContent).toBe("Turns");
        });
    });
});
