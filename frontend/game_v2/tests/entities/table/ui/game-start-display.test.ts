import { render } from "lit-html";
import { describe, expect, it } from "vitest";

import { checkpointState } from "#tests/fixtures/seat-transcripts";
import { type LiveClient, NO_PLAY_UI, PlayBoard, playDisplay } from "@/entities/client";

const STARTED = checkpointState("own_turn_seat_1", "game started");

function renderBoard(state: LiveClient): HTMLElement {
    const host = document.createElement("div");
    render(
        PlayBoard({
            display: playDisplay(state, NO_PLAY_UI),
            onCommand: () => {},
        }),
        host,
    );
    return host;
}

function seatRows(host: HTMLElement): string[][] {
    return [...host.querySelectorAll(".seating__seat")].map((row) =>
        [".seating__wind", ".seating__name", ".seating__marks"].map(
            (part) => row.querySelector(part)?.textContent?.replace(/\s+/gu, " ").trim() ?? "",
        ),
    );
}

describe("GameStartDisplay", () => {
    it("seats the players from the game start in wind order, the dealer, AI players and the viewer marked", () => {
        const host = renderBoard(STARTED);
        const dealer = STARTED.table.firstDealerSeat;
        const names = STARTED.table.players.map((player) => player.name);

        expect(host.querySelector(".seating__title")?.textContent).toBe("Hanchan · East 1");
        expect(seatRows(host).map(([wind]) => wind)).toEqual(["E", "S", "W", "N"]);
        expect(seatRows(host)[0][1]).toBe(names[dealer]);
        expect(seatRows(host)[0][2]).toMatch(/^Dealer/u);
        expect(host.querySelector(".seating__seat--viewer .seating__name")?.textContent).toBe(
            "Alice",
        );
        expect(
            host.querySelectorAll(".seating__seat .seating__mark:not([class*='--'])"),
        ).toHaveLength(3);
    });

    it("seats the players from the first dealer's seat round when the dealer is not seat 0", () => {
        const host = renderBoard({ ...STARTED, table: { ...STARTED.table, firstDealerSeat: 2 } });
        const names = STARTED.table.players.map((player) => player.name);

        expect(seatRows(host).map(([wind, name]) => [wind, name])).toEqual([
            ["E", names[2]],
            ["S", names[3]],
            ["W", names[0]],
            ["N", names[1]],
        ]);
        expect(seatRows(host)[0][2]).toMatch(/^Dealer/u);
    });

    it("counts the server's start pause down to the first deal, then only says the game is starting", () => {
        function status(now: number): string | undefined {
            return renderBoard({ ...STARTED, now }).querySelector(".seating__status")?.textContent;
        }

        expect([status(0), status(2500), status(3000)]).toEqual([
            "Starting in 3",
            "Starting in 1",
            "Starting…",
        ]);
        expect(
            renderBoard(checkpointState("own_turn_seat_1", "first draw")).querySelector(".seating"),
        ).toBeNull();
    });
});
