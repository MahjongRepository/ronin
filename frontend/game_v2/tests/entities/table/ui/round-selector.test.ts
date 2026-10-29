import { render } from "lit-html";
import { describe, expect, test, vi } from "vitest";

import { type RoundInfo } from "@/entities/table/model/navigation-index";
import { RoundSelector, formatRoundLabel } from "@/entities/table/ui/round-selector";

function makeRound(overrides: Partial<RoundInfo> = {}): RoundInfo {
    return {
        actionStepIndex: 2,
        honba: 0,
        resultDescription: "",
        roundNumber: 1,
        wind: 0,
        ...overrides,
    };
}

function renderSelector(
    overrides: {
        currentRound?: RoundInfo | undefined;
        isOpen?: boolean;
        onSelect?: (stepIndex: number) => void;
        onToggle?: () => void;
        rounds?: RoundInfo[];
    } = {},
): HTMLElement {
    const el = document.createElement("div");
    render(
        RoundSelector({
            currentRound: overrides.currentRound ?? undefined,
            isOpen: overrides.isOpen ?? false,
            onSelect: overrides.onSelect ?? vi.fn(),
            onToggle: overrides.onToggle ?? vi.fn(),
            rounds: overrides.rounds ?? [],
        }),
        el,
    );
    return el;
}

describe("formatRoundLabel", () => {
    test("formats basic round without honba or result", () => {
        const round = makeRound({ roundNumber: 1, wind: 0 });
        expect(formatRoundLabel(round)).toBe("East 1");
    });

    test("formats round with honba", () => {
        const round = makeRound({ honba: 2, roundNumber: 3, wind: 1 });
        expect(formatRoundLabel(round)).toBe("South 3, 2 honba");
    });

    test("formats round with result description", () => {
        const round = makeRound({ resultDescription: "Tsumo by Alice", roundNumber: 1, wind: 0 });
        expect(formatRoundLabel(round)).toBe("East 1 \u2014 Tsumo by Alice");
    });

    test("formats round with honba and result description", () => {
        const round = makeRound({
            honba: 1,
            resultDescription: "Ron by Bob from Carol",
            roundNumber: 2,
            wind: 0,
        });
        expect(formatRoundLabel(round)).toBe("East 2, 1 honba \u2014 Ron by Bob from Carol");
    });
});

describe("RoundSelector", () => {
    describe("maps rounds to correct dropdown items", () => {
        test("renders correct number of items when open", () => {
            const rounds = [
                makeRound({ actionStepIndex: 2, roundNumber: 1, wind: 0 }),
                makeRound({ actionStepIndex: 15, roundNumber: 2, wind: 0 }),
            ];
            const el = renderSelector({ isOpen: true, rounds });
            const items = el.querySelectorAll(".dropdown-select__item");
            expect(items).toHaveLength(2);
        });

        test("renders correct labels for each round", () => {
            const rounds = [
                makeRound({
                    actionStepIndex: 2,
                    resultDescription: "Tsumo by Alice",
                    roundNumber: 1,
                    wind: 0,
                }),
                makeRound({
                    actionStepIndex: 15,
                    honba: 1,
                    resultDescription: "Exhaustive draw",
                    roundNumber: 2,
                    wind: 0,
                }),
            ];
            const el = renderSelector({ isOpen: true, rounds });
            const items = el.querySelectorAll(".dropdown-select__item");
            expect(items[0]?.textContent?.trim()).toBe("East 1 \u2014 Tsumo by Alice");
            expect(items[1]?.textContent?.trim()).toBe("East 2, 1 honba \u2014 Exhaustive draw");
        });

        test("highlights current round", () => {
            const round1 = makeRound({ actionStepIndex: 2, roundNumber: 1, wind: 0 });
            const round2 = makeRound({ actionStepIndex: 15, roundNumber: 2, wind: 0 });
            const el = renderSelector({
                currentRound: round2,
                isOpen: true,
                rounds: [round1, round2],
            });
            const items = el.querySelectorAll(".dropdown-select__item");
            expect(items[0]?.classList.contains("dropdown-select__item--current")).toBe(false);
            expect(items[1]?.classList.contains("dropdown-select__item--current")).toBe(true);
        });

        test("calls onSelect with correct step index when item is clicked", () => {
            const onSelect = vi.fn();
            const rounds = [
                makeRound({ actionStepIndex: 2, roundNumber: 1, wind: 0 }),
                makeRound({ actionStepIndex: 15, roundNumber: 2, wind: 0 }),
            ];
            const el = renderSelector({ isOpen: true, onSelect, rounds });
            const items = el.querySelectorAll<HTMLButtonElement>(".dropdown-select__item");
            items[1]?.click();
            expect(onSelect).toHaveBeenCalledWith(15);
        });
    });

    describe("trigger label", () => {
        test("shows 'Rounds' when no current round", () => {
            const el = renderSelector({ currentRound: undefined });
            const trigger = el.querySelector(".dropdown-select__trigger");
            expect(trigger?.textContent).toBe("Rounds");
        });

        test("shows current round name when round is active", () => {
            const currentRound = makeRound({ roundNumber: 2, wind: 0 });
            const el = renderSelector({ currentRound, rounds: [currentRound] });
            const trigger = el.querySelector(".dropdown-select__trigger");
            expect(trigger?.textContent).toBe("East 2");
        });

        test("shows South wind correctly", () => {
            const currentRound = makeRound({ roundNumber: 1, wind: 1 });
            const el = renderSelector({ currentRound, rounds: [currentRound] });
            const trigger = el.querySelector(".dropdown-select__trigger");
            expect(trigger?.textContent).toBe("South 1");
        });
    });
});
