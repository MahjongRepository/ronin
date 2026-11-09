import { render } from "lit-html";
import { describe, expect, it } from "vitest";

import { ManualClock, steadyClockOn } from "#tests/fixtures/clock";
import { checkpointState, loadSeatScenario } from "#tests/fixtures/seat-transcripts";
import {
    type LiveClient,
    NO_PLAY_UI,
    PlayBoard,
    playDisplay,
    scenarioStateIndex,
    stepGameClient,
} from "@/entities/client";

const PAGE_CLOCK = steadyClockOn(new ManualClock());

const STARTED = checkpointState("own_turn_seat_1", "game started");
const { scenario } = loadSeatScenario("own_turn_seat_1");
const DEALT = stepGameClient(
    STARTED,
    scenario.steps[scenarioStateIndex(scenario, "game started")].event,
).state;

function renderBoard(state: LiveClient): HTMLElement {
    const host = document.createElement("div");
    render(
        PlayBoard({
            clock: PAGE_CLOCK,
            display: playDisplay(state, NO_PLAY_UI),
            onCommand: () => {},
            onLanguage: () => {},
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

    it("stays over the dealt board with each seat's score, its OK counting the start confirm down, then disabled while waiting for the others, gone by the first draw", () => {
        function countdown(now: number): string | undefined {
            return renderBoard({ ...DEALT, now }).querySelector(".seating__countdown")?.textContent;
        }
        const dealt = renderBoard(DEALT);
        const confirmed = stepGameClient(DEALT, {
            at: 1000,
            intent: { type: "confirm_opening" },
            kind: "intent",
        }).state;
        const waiting =
            renderBoard(confirmed).querySelector<HTMLButtonElement>(".seating__confirm");

        expect([DEALT.table.phase, dealt.querySelectorAll(".seating__score").length]).toEqual([
            "in_round",
            4,
        ]);
        expect(dealt.querySelector(".seating__confirm-label")?.textContent).toBe("OK");
        expect([countdown(0), countdown(2500)]).toEqual(["10s left", "8s left"]);
        expect([waiting?.textContent?.replace(/\s+/gu, " ").trim(), waiting?.disabled]).toEqual([
            "Waiting for others 9s left",
            true,
        ]);
        expect(
            renderBoard(checkpointState("own_turn_seat_1", "first draw")).querySelector(".seating"),
        ).toBeNull();
    });
});
