import { describe, expect, test } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import { buildNavigationIndex } from "@/entities/replay";
import { roundResultSummary } from "@/entities/table";

function summaries(name: string): string[] {
    const { events, tables } = loadEngineReplay(name);
    return buildNavigationIndex(events, tables).rounds.map((round) =>
        roundResultSummary(round.result, round.endTable.players),
    );
}

describe("roundResultSummary", () => {
    test("gives each win its hand's value and honba bonus, and each draw the seats it names", () => {
        expect(summaries("double_ron_on_honba")).toEqual([
            "Exhaustive draw: tenpai Diana",
            "Ron by Charlie from Diana: 2,400 (+300 honba)",
            "Double ron from Bob: Alice 1,600 (+600 honba); Diana 1,600 (+600 honba)",
            "Tsumo by Charlie: 2,700",
        ]);
        expect(summaries("pao")).toEqual(["Tsumo by Alice: 32,000, pao Diana"]);
        expect(summaries("full_game")[0]).toBe("Exhaustive draw: all noten");
        expect(summaries("kyuushu")).toEqual(["Kyuushu Kyuuhai: Alice"]);
    });

    test("says a round the recording stops in has no result", () => {
        expect(summaries("truncated_mid_round")).toEqual(["No result recorded"]);
    });
});
