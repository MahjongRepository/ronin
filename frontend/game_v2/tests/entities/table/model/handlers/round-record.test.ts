import { describe, expect, test } from "vitest";

import { checkpointState } from "#tests/fixtures/seat-transcripts";
import { standingsDisplay } from "@/entities/table/lib/standings-display";

describe("round history", () => {
    test("a reconnect's snapshot rebuilds the ledger the seat built from the round ends it saw", () => {
        const doubleRonSeen = checkpointState("double_ron_seat_1", "round end").table.roundHistory;
        const kyuushuSeen = checkpointState("game_end_reconnect_seat_1", "second deal").table
            .roundHistory;

        expect(checkpointState("double_ron_seat_1", "reconnected").table.roundHistory).toEqual(
            doubleRonSeen,
        );
        expect(
            doubleRonSeen.map((record) => [record.outcome, record.winnerSeats, record.loserSeat]),
        ).toEqual([["ron", [1, 3], 0]]);
        expect(
            checkpointState("game_end_reconnect_seat_1", "reconnected").table.roundHistory,
        ).toEqual(kyuushuSeen);
        expect(kyuushuSeen.map((record) => record.outcome)).toEqual(["nine_terminals"]);
    });

    test("keeps the rounds before a reconnect and every round after it through the game's end", () => {
        const display = standingsDisplay(
            checkpointState("game_end_reconnect_seat_1", "game end").table,
            1,
        );

        expect(display?.ledger.map((row) => [row.name, row.honba, row.outcome])).toEqual([
            ["East 1", 0, "Nine terminals"],
            ["East 1", 1, "Draw"],
            ["East 2", 2, "Draw"],
            ["East 3", 3, "Draw"],
            ["East 4", 4, "Draw"],
        ]);
        expect(display?.seats.find((seat) => seat.viewer)?.name).toBe("Alice");
    });
});
