import { html, render } from "lit-html";
import { describe, expect, it, vi } from "vitest";

import { tableStateToDisplayState } from "@/entities/table/lib/board-mapper";
import { type BoardCallouts, type SeatPosition } from "@/entities/table/model/board-types";
import {
    createInitialPlayerState,
    createInitialTableState,
} from "@/entities/table/model/initial-state";
import { GameBoard } from "@/entities/table/ui/game-board";

function renderBoard(pinned: SeatPosition | null, onPin = vi.fn()): HTMLElement {
    const players = [0, 1, 2, 3].map((seat) => ({
        ...createInitialPlayerState({
            isAiPlayer: false,
            name: `P${seat}`,
            score: 25_000 + 1000 * seat,
            seat,
        }),
        isRiichi: seat === 3,
    }));
    const table = {
        ...createInitialTableState(),
        dealerSeat: 1,
        doraIndicators: [0],
        honbaSticks: 2,
        players,
        riichiSticks: 1,
    };
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

function texts(host: HTMLElement, selector: string): (string | undefined)[] {
    return [...host.querySelectorAll(selector)].map((element) => element.textContent?.trim());
}

describe("GameBoard centre and dora", () => {
    it("gives each seat its wind and score on its side of the centre, its differences beside, and its riichi stick", () => {
        const host = renderBoard(null);
        expect(texts(host, ".board-center__seat--dealer .board-center__wind")).toEqual(["E"]);
        expect(host.querySelector(".board-center__seat--dealer")).toBe(
            host.querySelector(".board-center__seat--right"),
        );
        expect(texts(host, ".board-center__wind")).toEqual(["N", "E", "S", "W"]);
        expect(texts(host, ".board-center__score")).toEqual(["25000", "26000", "27000", "28000"]);
        expect(texts(host, ".board-center__seat--left .board-center__diff--bottom")).toEqual([
            "+3000",
        ]);
        expect(
            host.querySelectorAll(".board-center__riichi:not(.board-center__riichi--none)"),
        ).toHaveLength(1);
        expect(
            host.querySelector(".board-center__seat--left .board-center__riichi--none"),
        ).toBeNull();
    });

    it("shows the dora indicators turned so far, a back in each of the five slots still to turn, and the sticks", () => {
        const host = renderBoard(null);
        const slots = [...host.querySelectorAll(".board-dora__tile .tile")];
        expect(slots.map((tile) => tile.classList.contains("tile-back"))).toEqual([
            false,
            true,
            true,
            true,
            true,
        ]);
        expect(texts(host, ".board-dora__label")).toEqual(["Honba", "Riichi"]);
        expect(texts(host, ".board-dora__count")).toEqual(["2", "1"]);
    });
});

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

describe("GameBoard callouts", () => {
    function renderCallouts(
        callouts: BoardCallouts,
        host: HTMLElement = document.createElement("div"),
    ): HTMLElement {
        render(
            GameBoard({
                callouts,
                debug: false,
                overlay: html`<p>Result</p>`,
                overlayIsResult: true,
                scoreDiff: { onPin: vi.fn(), pinned: null },
                state: null,
            }),
            host,
        );
        return host;
    }

    const RON: BoardCallouts = {
        items: [{ kind: "ron", label: "Ron", position: "right" }],
        key: "call-1",
    };
    const PON: BoardCallouts = {
        items: [{ kind: "pon", label: "Pon", position: "top" }],
        key: "call-2",
    };

    it("holds a result's panel back while a win's call shows, never for another call", () => {
        const held = ".board-overlay--after-call";

        expect(renderCallouts(RON).querySelector(held)).not.toBeNull();
        expect(renderCallouts(PON).querySelector(held)).toBeNull();
    });

    it("draws a new showing afresh, so its animation replays, and keeps the element through a redraw", () => {
        const host = renderCallouts(PON);
        const first = host.querySelector(".board-callout");
        renderCallouts(PON, host);
        const redrawn = host.querySelector(".board-callout");
        renderCallouts({ ...PON, key: "call-3" }, host);

        expect(first?.textContent?.trim()).toBe("Pon");
        expect(first?.classList.contains("board-callout--top")).toBe(true);
        expect(redrawn).toBe(first);
        expect(host.querySelector(".board-callout")).not.toBe(first);
    });
});
