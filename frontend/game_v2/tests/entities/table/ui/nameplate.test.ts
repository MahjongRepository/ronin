import { render } from "lit-html";
import { describe, expect, it, vi } from "vitest";

import { tableStateToDisplayState } from "@/entities/table/lib/board-mapper";
import {
    type BoardDisplayState,
    SEAT_POSITIONS,
    type SeatPosition,
} from "@/entities/table/model/board-types";
import {
    createInitialPlayerState,
    createInitialTableState,
} from "@/entities/table/model/initial-state";
import { type TableState } from "@/entities/table/model/types";
import { Nameplates } from "@/entities/table/ui/nameplate";
import { SEAT_CONTROL_REASON } from "@/shared/protocol";

const LONG_NAME = "Wolfeschlegelsteinhausenbergerdorff";

function nameplates(): BoardDisplayState["nameplates"] {
    const players = [
        createInitialPlayerState({ isAiPlayer: false, name: "Alice", score: 31_000, seat: 0 }),
        createInitialPlayerState({ isAiPlayer: true, name: "Bot", score: 25_000, seat: 1 }),
        createInitialPlayerState({ isAiPlayer: false, name: LONG_NAME, score: 18_000, seat: 2 }),
        {
            ...createInitialPlayerState({ isAiPlayer: false, name: "Dan", score: 26_000, seat: 3 }),
            aiStandIn: SEAT_CONTROL_REASON.LEFT,
        },
    ];
    const table: TableState = { ...createInitialTableState(), phase: "in_round", players };
    return tableStateToDisplayState(table, { bottomSeat: 0, reveal: "bottom" })!.nameplates;
}

function renderPlates(pinned: SeatPosition | null, onPin = vi.fn()): HTMLElement {
    const host = document.createElement("div");
    const plates = Nameplates(nameplates(), { kind: "pin", onPin, pinned });
    render(
        SEAT_POSITIONS.map((position) => plates[position]),
        host,
    );
    return host;
}

function plate(host: HTMLElement, position: SeatPosition): HTMLButtonElement {
    const found = host.querySelector(`.nameplate--${position}`);
    if (!(found instanceof HTMLButtonElement)) {
        throw new Error(`no ${position} nameplate button`);
    }
    return found;
}

describe("Nameplates", () => {
    it("moves the pin to another plate pressed, and unpins the pinned plate pressed again", () => {
        const onPin = vi.fn();
        const host = renderPlates("right", onPin);
        expect(plate(host, "right").getAttribute("aria-pressed")).toBe("true");
        expect(plate(host, "top").getAttribute("aria-pressed")).toBe("false");
        plate(host, "top").click();
        plate(host, "right").click();
        expect(onPin.mock.calls).toEqual([["top"], [null]]);
    });

    it("reads whose turn it is, why an AI player is marked, and each other plate's difference from the pinned one", () => {
        const host = renderPlates("right");
        expect(plate(host, "bottom").getAttribute("aria-label")).toBe(
            "Alice, East, dealer, to play, +6000 from Bot",
        );
        expect(plate(host, "right").getAttribute("aria-label")).toBe(
            "Bot, South, 25,000 points, An AI player plays this seat",
        );
        expect(plate(host, "left").getAttribute("aria-label")).toBe(
            "Dan, North, +1000 from Bot, Disconnected: an AI player plays this seat",
        );
        expect(plate(host, "right").querySelector(".nameplate__ai--ai")).not.toBeNull();
        expect(plate(host, "left").querySelector(".nameplate__ai--away")).not.toBeNull();
    });

    it("keeps a long name's end apart from its start, so a narrow plate gives up the start", () => {
        const top = plate(renderPlates(null), "top");
        expect(top.querySelector(".nameplate__name .player-name__tail")?.textContent).toBe("orff");
        expect(top.getAttribute("aria-label")).toContain(LONG_NAME);
    });
});
