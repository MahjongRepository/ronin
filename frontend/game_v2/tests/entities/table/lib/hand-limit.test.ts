import { assert, describe, expect, test } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import { type WinnerResult } from "@/entities/table";
import { handLimitName } from "@/entities/table/lib/hand-limit";
import { HAND_LIMIT } from "@/shared/protocol";

function fixtureWinners(name: string): readonly WinnerResult[] {
    return loadEngineReplay(name).tables.flatMap((table, index, tables) =>
        table.roundEndResult !== null && tables[index - 1]?.roundEndResult !== table.roundEndResult
            ? table.roundEndResult.winners
            : [],
    );
}

function lastWinner(name: string): WinnerResult {
    const winner = fixtureWinners(name).at(-1);
    assert(winner !== undefined, `${name} has no winner`);
    return winner;
}

describe("handLimitName", () => {
    test.each([
        ["riichi", "5 han 20 fu", "Mangan"],
        ["chankan_added", "6 han", "Haneman"],
        ["head_bump", "8 han", "Baiman"],
        ["kans", "11 han", "Sanbaiman"],
        ["pao", "daisangen", "Yakuman"],
        ["chankan_closed_kokushi", "kokushi", "Yakuman"],
        ["kazoe", "15 han of ordinary yaku, dealer", "Yakuman"],
    ])("%s (%s) is paid as %s", (name, _hand, limit) => {
        const winner = lastWinner(name);

        expect(handLimitName(winner.handResult)).toBe(limit);
    });

    test("names the server's limit, never one worked back from the points or han", () => {
        const hand = { fu: 30, han: 5, yaku: [{ han: 5, yakuId: 39, yakumanCount: 0 }] };

        expect([
            handLimitName({
                ...hand,
                limit: HAND_LIMIT.MANGAN,
                points: 12_000,
                yakumanCount: null,
            }),
            handLimitName({ ...hand, limit: HAND_LIMIT.NONE, points: 8000, yakumanCount: null }),
            handLimitName({
                ...hand,
                han: 13,
                limit: HAND_LIMIT.SANBAIMAN,
                points: 24_000,
                yakumanCount: null,
            }),
            handLimitName({
                ...hand,
                han: 26,
                limit: HAND_LIMIT.YAKUMAN,
                points: 32_000,
                yakumanCount: 2,
            }),
        ]).toEqual(["Mangan", null, "Sanbaiman", "Double Yakuman"]);
    });
});
