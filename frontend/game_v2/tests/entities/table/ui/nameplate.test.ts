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

function renderPlates(onView: ((seat: SeatPosition) => void) | null = null): HTMLElement {
    const host = document.createElement("div");
    const plates = Nameplates(nameplates(), onView);
    render(
        SEAT_POSITIONS.map((position) => plates[position]),
        host,
    );
    return host;
}

function plate(host: HTMLElement, position: SeatPosition): HTMLElement {
    const found = host.querySelector(`.nameplate--${position}`);
    if (!(found instanceof HTMLElement)) {
        throw new Error(`no ${position} nameplate`);
    }
    return found;
}

describe("Nameplates", () => {
    it("draws a live game's plates as no buttons, reading whose turn it is, each score and why an AI player is marked", () => {
        const host = renderPlates();
        expect(host.querySelector("button")).toBeNull();
        expect(plate(host, "bottom").getAttribute("aria-label")).toBe(
            "Alice, East, dealer, to play, 31,000 points",
        );
        expect(plate(host, "left").getAttribute("aria-label")).toBe(
            "Dan, North, 26,000 points, Disconnected: an AI player plays this seat",
        );
        expect(plate(host, "right").querySelector(".nameplate__ai--ai")).not.toBeNull();
        expect(plate(host, "left").querySelector(".nameplate__ai--away")).not.toBeNull();
    });

    it("views the table from a plate's seat where a press views from one", () => {
        const onView = vi.fn();
        const host = renderPlates(onView);
        plate(host, "top").click();
        expect(onView.mock.calls).toEqual([["top"]]);
    });

    it("keeps a long name's end apart from its start, so a narrow plate gives up the start", () => {
        const top = plate(renderPlates(), "top");
        expect(top.querySelector(".nameplate__name .player-name__tail")?.textContent).toBe("orff");
        expect(top.getAttribute("aria-label")).toContain(LONG_NAME);
    });
});
