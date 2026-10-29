import { render } from "lit-html";
import { describe, expect, it, vi } from "vitest";

import { tableStateToDisplayState } from "@/entities/table/lib/board-mapper";
import { type SeatPosition } from "@/entities/table/model/board-types";
import {
    createInitialPlayerState,
    createInitialTableState,
} from "@/entities/table/model/initial-state";
import { GameBoard } from "@/entities/table/ui/game-board";

function renderBoard(pinned: SeatPosition | null, onPin = vi.fn()): HTMLElement {
    const players = [0, 1, 2, 3].map((seat) =>
        createInitialPlayerState({ isAiPlayer: false, name: `P${seat}`, score: 25_000, seat }),
    );
    const table = { ...createInitialTableState(), players };
    const state = tableStateToDisplayState(table, { bottomSeat: 0, reveal: "bottom" });
    const host = document.createElement("div");
    render(GameBoard({ debug: false, scoreDiff: { onPin, pinned }, state }), host);
    return host;
}

function press(host: HTMLElement, selector: string, init: KeyboardEventInit | null = null): void {
    const target = host.querySelector(selector);
    if (target === null) {
        throw new Error(`nothing matches ${selector}`);
    }
    target.dispatchEvent(
        init === null
            ? new MouseEvent("click", { bubbles: true })
            : new KeyboardEvent("keydown", { bubbles: true, ...init }),
    );
}

describe("GameBoard nameplates", () => {
    it("marks the board with the pinned plate, whose own click goes to the plate alone", () => {
        const onPin = vi.fn();
        const host = renderBoard("left", onPin);
        expect(host.querySelector(".game-board")?.classList.contains("game-board--diff-left")).toBe(
            true,
        );
        press(host, ".nameplate--top");
        expect(onPin.mock.calls).toEqual([["top"]]);
    });

    it("unpins the pinned plate on a click elsewhere on the board or on Escape", () => {
        const onPin = vi.fn();
        const host = renderBoard("left", onPin);
        press(host, ".board-center");
        press(host, ".nameplate--top", { key: "Escape" });
        expect(onPin.mock.calls).toEqual([[null], [null]]);
    });

    it("asks nothing on a click elsewhere or Escape while no plate is pinned", () => {
        const onPin = vi.fn();
        const host = renderBoard(null, onPin);
        press(host, ".board-center");
        press(host, ".board-center", { key: "Escape" });
        expect(onPin).not.toHaveBeenCalled();
    });
});
