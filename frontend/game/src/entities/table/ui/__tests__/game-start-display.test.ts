import { type TemplateResult, render } from "lit-html";
import { describe, expect, test } from "vitest";

import { createInitialPlayerState } from "@/entities/table/model/initial-state";
import { type PlayerState } from "@/entities/table/model/types";
import { GameStartDisplay } from "@/entities/table/ui/game-start-display";

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

describe("GameStartDisplay", () => {
    test("renders all 4 players", () => {
        const el = renderTo(GameStartDisplay(makePlayers(), 0));
        const rows = el.querySelectorAll(".game-start-result__row");
        expect(rows).toHaveLength(4);
    });

    test("renders Game Start title", () => {
        const el = renderTo(GameStartDisplay(makePlayers(), 0));
        const title = el.querySelector(".game-start-result__title");
        expect(title?.textContent).toBe("Game Start");
    });

    test("wind assignments are relative to dealer seat", () => {
        const el = renderTo(GameStartDisplay(makePlayers(), 0));
        const winds = el.querySelectorAll(".game-start-result__wind");
        expect(winds[0].textContent).toBe("East");
        expect(winds[1].textContent).toBe("South");
        expect(winds[2].textContent).toBe("West");
        expect(winds[3].textContent).toBe("North");
    });

    test("winds sorted East-first when dealer is not seat 0", () => {
        const el = renderTo(GameStartDisplay(makePlayers(), 2));
        const winds = el.querySelectorAll(".game-start-result__wind");
        expect(winds[0].textContent).toBe("East");
        expect(winds[1].textContent).toBe("South");
        expect(winds[2].textContent).toBe("West");
        expect(winds[3].textContent).toBe("North");
    });

    test("names follow dealer-relative order when dealer is not seat 0", () => {
        const el = renderTo(GameStartDisplay(makePlayers(), 2));
        const names = el.querySelectorAll(".game-start-result__name");
        // Dealer seat 2 → East=Bot-2, South=Bob, West=Alice, North=Bot-1
        expect(names[0].textContent).toBe("Bot-2");
        expect(names[1].textContent).toBe("Bob");
        expect(names[2].textContent).toBe("Alice");
        expect(names[3].textContent).toBe("Bot-1");
    });
});
