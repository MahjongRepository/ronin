import { describe, expect, test } from "vitest";

import { type EngineReplay, loadEngineReplay } from "#tests/fixtures/replays";
import { buildNavigationIndex, narrateStop } from "@/entities/replay";
import { type BoardPerspective } from "@/entities/table";
import { SEAT_CONTROL_REASON } from "@/shared/protocol";

const ALL: BoardPerspective = { bottomSeat: 0, reveal: "all" };

function narration(replay: EngineReplay, perspective = ALL): string[] {
    const { stops } = buildNavigationIndex(replay.events, replay.tables);
    return stops.map((stop) => narrateStop(replay, stop, perspective));
}

describe("narrateStop", () => {
    test("tells the deal with the seats an AI holds from the start", () => {
        expect(narration(loadEngineReplay("ai_dealer_absent"))[0]).toBe(
            "East 1: Tsumogiri 1 deals · AI plays for Alice, who is absent · AI plays for Bob, who is absent",
        );
    });

    test("tells a seat changing hands on the stop that first shows it", () => {
        const replay = loadEngineReplay("ai_replacements");
        const { stops } = buildNavigationIndex(replay.events, replay.tables);
        const lines = narration(replay);
        const noted = lines.findIndex((line) => line.includes("AI plays for Charlie"));
        function charlie(stop: number): unknown {
            return replay.tables[stops[stop].stateIndex].players[2].aiStandIn;
        }

        expect(lines[noted]).toBe("Charlie discards 4p · AI plays for Charlie, who left");
        expect([charlie(noted - 1), charlie(noted)]).toEqual([null, SEAT_CONTROL_REASON.LEFT]);
    });

    test("tells a robbed kan's declaration on its own stop, then the ron that robs it", () => {
        expect(narration(loadEngineReplay("chankan_added")).slice(-2)).toEqual([
            "Alice declares an added kan of 6p",
            "Ron by Charlie robbing Alice's kan: 12,000",
        ]);
    });

    test("tells a riichi on its discard's stop", () => {
        expect(narration(loadEngineReplay("riichi"))[11]).toBe(
            "Alice declares riichi, discarding Red dragon",
        );
    });

    test("names a drawn tile only where the perspective shows the drawer's hand", () => {
        const replay = loadEngineReplay("riichi");

        expect(narration(replay, { bottomSeat: 0, reveal: "bottom" })[2]).toBe("Alice draws");
        expect(narration(replay, { bottomSeat: 1, reveal: "bottom" })[2]).toBe("Alice draws 9m");
    });
});
