import { afterEach, describe, expect, test } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import { type GameEndResult, type TableState } from "@/entities/table";
import { type GameEndDisplayState, gameEndDisplay } from "@/entities/table/lib/game-end-display";
import { GAME_END_CAUSE } from "@/shared/protocol";

function endTable(name: string): TableState {
    const table = loadEngineReplay(name).tables.at(-1);
    if (table === undefined) {
        throw new Error(`${name} holds no table`);
    }
    return table;
}

function endOf(table: TableState): GameEndResult {
    const end = table.gameEndResult;
    if (end === null) {
        throw new Error("the table holds no game end");
    }
    return end;
}

function shownEnd(table: TableState, viewerSeat: number | null = null): GameEndDisplayState {
    const display = gameEndDisplay(table, viewerSeat);
    if (display === null) {
        throw new Error("the table shows no game end");
    }
    return display;
}

describe("gameEndDisplay", () => {
    afterEach(() => {
        document.documentElement.lang = "";
    });

    test("ranks the seats as the server placed them, with the score, the uma/oka result and the viewer", () => {
        const display = shownEnd(endTable("leftover_riichi"), 1);

        expect(
            display.seats.map((seat) => [seat.placement, seat.score, seat.result, seat.isViewer]),
        ).toEqual([
            ["1st", "28,000", "+37.0", false],
            ["2nd", "24,500", "+5.0", true],
            ["3rd", "23,500", "−16.0", false],
            ["4th", "23,500", "−26.0", false],
        ]);
        document.documentElement.lang = "ru";
        expect(shownEnd(endTable("leftover_riichi"), 1).seats.map((seat) => seat.result)).toEqual([
            "+37,0",
            "+5,0",
            "−16,0",
            "−26,0",
        ]);
        expect(display.leftover).toBe(
            `1 leftover riichi stick: +1,500 to ${display.seats[0].name}`,
        );
    });

    test("says the leftover sticks went to nobody when the game end pays no bonus for them", () => {
        const table = endTable("leftover_riichi");
        const unpaid = { ...table, gameEndResult: { ...endOf(table), leftoverRiichiBonus: 0 } };

        expect(shownEnd(unpaid).leftover).toBe("1 leftover riichi stick, awarded to nobody");
        document.documentElement.lang = "ru";
        expect(
            [1, 2, 5].map(
                (leftoverSticks) =>
                    shownEnd({
                        ...unpaid,
                        gameEndResult: { ...unpaid.gameEndResult, leftoverSticks },
                    }).leftover,
            ),
        ).toEqual([
            "1 оставшаяся ставка риичи никому не достаётся",
            "2 оставшиеся ставки риичи никому не достаются",
            "5 оставшихся ставок риичи никому не достаются",
        ]);
    });

    test("says the game completed by the cause the server's engine names, in its last round", () => {
        expect(shownEnd(endTable("leftover_riichi")).ending.text).toBe(
            "Completed by tobi in East 1",
        );
        expect(shownEnd(endTable("eager_game")).ending.text).toBe("Completed after South 4");
        expect(shownEnd(endTable("full_game")).ending.text).toBe(
            "Completed after West 4, the extension's last round",
        );
    });

    test("names no round once the table lost step with the server", () => {
        const table = endTable("full_game");
        const lost = {
            ...table,
            gameEndResult: { ...endOf(table), endCause: GAME_END_CAUSE.TARGET_REACHED },
            inStep: false,
        };

        expect(shownEnd(lost).ending.text).toBe("Completed: the extension's target score reached");
    });
});
