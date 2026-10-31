import { assert, describe, expect, test } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import { type WinnerResult } from "@/entities/table";
import { handLimitName } from "@/entities/table/lib/hand-limit";

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
        ["ai_replacements", "kiriage 4 han 30 fu", "Mangan"],
        ["chankan_added", "6 han", "Haneman"],
        ["head_bump", "8 han", "Baiman"],
        ["kans", "11 han", "Sanbaiman"],
        ["pao", "daisangen", "Yakuman"],
        ["chankan_closed_kokushi", "kokushi", "Yakuman"],
        ["kazoe", "15 han of ordinary yaku, dealer", "Kazoe Yakuman"],
    ])("%s (%s) is paid as %s", (name, _hand, limit) => {
        const winner = lastWinner(name);

        expect(handLimitName(winner.handResult, winner.isDealer)).toBe(limit);
    });

    test("reads a dealer's limit at 6x its basic points and a hand below mangan as none", () => {
        const winners = fixtureWinners("eager_game");
        const dealerMangan = winners.find(
            (winner) => winner.isDealer && winner.handResult.han === 5,
        );
        const below = winners.find((winner) => winner.handResult.han === 1);
        assert(dealerMangan !== undefined && below !== undefined);

        expect(dealerMangan.handResult.points).toBe(12_000);
        expect(handLimitName(dealerMangan.handResult, true)).toBe("Mangan");
        expect(handLimitName(below.handResult, below.isDealer)).toBeNull();
    });

    test("names a limit from the payment, not the han: kazoe capped at sanbaiman, a double yakuman", () => {
        const kazoeCapped = {
            fu: 30,
            han: 13,
            points: 24_000,
            yaku: [{ han: 6, isYakuman: false, yakuId: 39 }],
        };
        const doubleYakuman = {
            fu: 0,
            han: 26,
            points: 64_000,
            yaku: [{ han: 26, isYakuman: true, yakuId: 113 }],
        };

        expect(handLimitName(kazoeCapped, false)).toBe("Sanbaiman");
        expect(handLimitName(doubleYakuman, false)).toBe("Double Yakuman");
    });

    test("tells a yakuman from a kazoe yakuman by the server's yakuman flag, whatever the yaku's id", () => {
        const yakuman = { fu: 0, han: 13, points: 32_000 };

        expect([
            handLimitName({ ...yakuman, yaku: [{ han: 13, isYakuman: true, yakuId: 150 }] }, false),
            handLimitName(
                { ...yakuman, yaku: [{ han: 13, isYakuman: false, yakuId: 103 }] },
                false,
            ),
        ]).toEqual(["Yakuman", "Kazoe Yakuman"]);
    });
});
