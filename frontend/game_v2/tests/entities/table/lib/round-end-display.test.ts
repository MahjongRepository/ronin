import { afterEach, assert, describe, expect, test } from "vitest";

import { makeRonRoundEnd, makeRonWin } from "#tests/fixtures/events";
import { loadEngineReplay } from "#tests/fixtures/replays";
import {
    type DrawPageDisplay,
    type ResultHandDisplay,
    type RoundEndDisplayState,
    type TableState,
    type WinPageDisplay,
    createInitialPlayerState,
    extractRoundEndResult,
    roundEndDisplay,
} from "@/entities/table";
import { type PaoLiability } from "@/shared/protocol";
import { PAO_SHARE } from "@/shared/protocol/constants";

function roundEndTables(name: string): TableState[] {
    return loadEngineReplay(name).tables.filter(
        (table, index, tables) =>
            table.phase === "round_ended" && tables[index - 1]?.phase !== "round_ended",
    );
}

function lastRoundEndTable(name: string): TableState {
    const table = roundEndTables(name).at(-1);
    assert(table !== undefined, `${name} has no round end`);
    return table;
}

function doubleRonOnHonba(): TableState {
    const table = roundEndTables("double_ron_on_honba").find(
        (candidate) => (candidate.roundEndResult?.winners.length ?? 0) > 1,
    );
    assert(table !== undefined);
    return table;
}

function displayAt(table: TableState, page = 0, bottomSeat = 0): RoundEndDisplayState {
    assert(table.roundEndResult !== null);
    return roundEndDisplay({ ...table, result: table.roundEndResult }, { bottomSeat, page });
}

function winPage(table: TableState, page = 0): WinPageDisplay {
    const display = displayAt(table, page);
    assert(display.body.kind === "win");
    const shown = display.body.pages[display.page];
    assert(shown !== undefined);
    return shown;
}

function drawPage(table: TableState): DrawPageDisplay {
    const { body } = displayAt(table);
    assert(body.kind === "draw");
    return body;
}

function withScoreChanges(table: TableState, scoreChanges: Record<string, number>): TableState {
    const result = table.roundEndResult;
    assert(result !== null);
    return { ...table, roundEndResult: { ...result, scoreChanges } };
}

function seatTags(table: TableState): (string | null)[] {
    return displayAt(table).seats.map((seat) => seat.tag);
}

function paoNotesWhen(loserSeat: number | null, pao: PaoLiability): readonly string[] {
    const table = lastRoundEndTable("pao");
    const result = table.roundEndResult;
    assert(result !== null && result.winners[0] !== undefined);
    const winners = [{ ...result.winners[0], pao }];
    return winPage({ ...table, roundEndResult: { ...result, loserSeat, winners } }).notes;
}

function headBumpNotes(headBumpedSeats: number[]): readonly string[] {
    const players = ["Diana", "Alice", "Charlie", "Bob"].map((name, seat) =>
        createInitialPlayerState({ isAiPlayer: false, name, score: 25_000, seat }),
    );
    const event = makeRonRoundEnd({
        headBumpedSeats,
        loserSeat: 0,
        scoreChanges: { "0": -3900, "1": 3900, "2": 0, "3": 0 },
        winners: [makeRonWin({ winnerSeat: 1 })],
    });
    const result = extractRoundEndResult(event, { players, riichiStickValue: 1000 });
    const table = {
        firstDealerSeat: 0,
        honbaSticks: 0,
        inStep: true,
        players,
        result,
        roundInWind: 1,
        roundWind: 0,
    };
    const { body } = roundEndDisplay(table, { bottomSeat: 0, page: 0 });
    assert(body.kind === "win" && body.pages[0] !== undefined);
    return body.pages[0].notes;
}

function handFaces(hand: ResultHandDisplay): string[] {
    return hand.tiles.map((tile) => tile.face ?? "?");
}

afterEach(() => {
    document.documentElement.lang = "";
});

describe("roundEndDisplay - a win", () => {
    test("a ron: who won from whom, the hand's value with its limit, the yaku with the dora last, the stick it took", () => {
        const page = winPage(lastRoundEndTable("ron_riichi_discard"));

        expect(page).toMatchObject({
            from: "from Charlie",
            hanFu: "7 han 30 fu",
            limit: "Haneman",
            points: 12_000,
            title: "Ron",
            winnerName: "Alice",
        });
        expect(page.yaku.map((line) => [line.name, line.han, line.isDora])).toEqual([
            ["Ippatsu", 1, false],
            ["Double Riichi", 2, false],
            ["Pinfu", 1, false],
            ["Ittsuu", 2, false],
            ["Aka Dora", 1, true],
        ]);
        expect(page.sticks).toEqual({ bonus: 1000, honba: 0, riichi: 1 });
        expect(page.notes).toEqual([]);
    });

    test("a chankan: the ron reads as robbing the declarer's kan, in a note where no chankan yaku says it", () => {
        const page = winPage(lastRoundEndTable("chankan_added"));
        const kokushi = winPage(lastRoundEndTable("chankan_closed_kokushi"));

        expect(page).toMatchObject({
            from: "robbing Alice's kan",
            title: "Ron",
            winnerName: "Charlie",
        });
        expect(
            [page.yaku, kokushi.yaku].map((yaku) => yaku.some((line) => line.name === "Chankan")),
        ).toEqual([true, false]);
        expect([page.notes, kokushi.notes]).toEqual([
            [],
            [expect.stringMatching(/^Robbed .+'s kan$/)],
        ]);
    });

    test("a ron: the closed hand sorted, the winning tile apart under its label, the dora and ura as faces", () => {
        const table = lastRoundEndTable("ron_riichi_discard");
        const winner = table.roundEndResult?.winners[0];
        assert(winner !== undefined);
        const page = winPage(table);

        expect(page.hand.tiles.map((tile) => tile.tileId)).toEqual(
            winner.closedTiles.toSorted((first, second) => first - second),
        );
        expect(page.winningTile).toMatchObject({ show: "face", tileId: winner.winningTile });
        expect(page.winningTileLabel).toBe("Ron");
        expect(page.doraIndicators).toHaveLength(table.doraIndicators.length);
        expect(page.uraIndicators).toHaveLength(winner.uraDoraIndicators.length);
    });

    test("the seats: each one's change, the score it leads to and its placement, placed as it sits from the bottom seat", () => {
        const table = lastRoundEndTable("riichi");
        const { round, seats } = displayAt(table);

        expect(round).toBe("East 1");
        expect(
            seats.map((seat) => [
                seat.position,
                seat.wind,
                seat.windName,
                seat.name,
                seat.role,
                seat.delta,
                seat.after,
                seat.rank,
                seat.tag,
            ]),
        ).toEqual([
            ["bottom", "E", "East", "Diana", "loss", -4000, 21_000, "4th", null],
            ["right", "S", "South", "Alice", "gain", 10_000, 34_000, "1st", null],
            ["top", "W", "West", "Charlie", "loss", -2000, 23_000, "2nd", null],
            ["left", "N", "North", "Bob", "loss", -2000, 22_000, "3rd", null],
        ]);
        expect(displayAt(table, 0, 2).seats.map((seat) => [seat.position, seat.name])).toEqual([
            ["bottom", "Charlie"],
            ["right", "Bob"],
            ["top", "Diana"],
            ["left", "Alice"],
        ]);
    });

    test("a yakuman: names it under its seal without han or fu; pao names the liable seat and tags it; melds laid out", () => {
        const table = lastRoundEndTable("pao");
        const page = winPage(table);

        expect(page.limit).toBe("Yakuman");
        expect(page.hanFu).toBeNull();
        expect(page.yaku.map((line) => [line.name, line.han, line.yakuman])).toEqual([
            ["Daisangen", null, { kanji: "大三元", multiple: null, seal: "役満" }],
        ]);
        expect(page.notes).toContain("Pao: Diana is liable for Daisangen and pays the whole hand");
        expect(displayAt(table).seats.map((seat) => [seat.name, seat.tag])).toEqual([
            ["Diana", "Pao"],
            ["Alice", null],
            ["Charlie", null],
            ["Bob", null],
        ]);
        expect(page.hand.melds).toHaveLength(3);
        expect(page.winningTileLabel).toBe("Tsumo");
    });

    test("pao words the server's liability: the yakuman it covers, its share and the honba, whatever the hand and loser", () => {
        const daisuushiiHalf = { paysHonba: true, seat: 0, share: PAO_SHARE.HALF, yakuIds: [111] };

        expect(paoNotesWhen(null, daisuushiiHalf)).toContain(
            "Pao: Diana is liable for Daisuushii and pays half the hand and the honba",
        );
        expect(
            paoNotesWhen(2, { ...daisuushiiHalf, paysHonba: false, share: PAO_SHARE.ALL }),
        ).toContain("Pao: Diana is liable for Daisuushii and pays the whole hand");
        expect(paoNotesWhen(0, daisuushiiHalf)).toContain(
            "Pao: Diana is liable and dealt in, so pays it all",
        );
        document.documentElement.lang = "ru";
        expect(paoNotesWhen(null, daisuushiiHalf)).toContain(
            "Пао: Diana несёт ответственность за Дайсуши и платит половину стоимости руки и хонбу",
        );
    });

    test("a yakuman yaku worth more than one names the server's multiple on its seal and in place of han", () => {
        const table = lastRoundEndTable("pao");
        const result = table.roundEndResult;
        assert(result !== null && result.winners[0] !== undefined);
        const [winner] = result.winners;
        const doubled = {
            ...winner,
            handResult: { ...winner.handResult, yaku: [{ han: 13, yakuId: 111, yakumanCount: 2 }] },
        };
        const page = winPage({ ...table, roundEndResult: { ...result, winners: [doubled] } });

        expect(page.yaku.map((line) => [line.name, line.han, line.yakuman])).toEqual([
            ["Daisuushii", null, { kanji: "大四喜", multiple: "Double Yakuman", seal: "二倍役満" }],
        ]);
    });

    test("a kazoe yakuman: keeps its han beside the limit", () => {
        const page = winPage(lastRoundEndTable("kazoe"));

        expect(page).toMatchObject({
            hanFu: "15 han 20 fu",
            limit: "Yakuman",
            points: 48_000,
        });
    });

    test("head bump: tells the player whose call lost and who won it", () => {
        expect(headBumpNotes([2])).toEqual(["Atamahane: Alice won; no ron for Charlie"]);
        document.documentElement.lang = "ru";
        expect(headBumpNotes([2, 3])).toEqual([
            "Атамаханэ: рон засчитан (Alice), не засчитан (Charlie и Bob)",
        ]);
    });

    test("a double ron on honba: only the winner the server paid the honba to shows the round's honba sticks", () => {
        const table = doubleRonOnHonba();

        expect(displayAt(table).round).toBe("East 2, 2 honba");
        expect([winPage(table, 0).sticks, winPage(table, 1).sticks]).toEqual([
            { bonus: 600, honba: 2, riichi: 0 },
            { bonus: 0, honba: 0, riichi: 0 },
        ]);
    });
});

describe("roundEndDisplay - the server's facts, never the table's or arithmetic", () => {
    test("the sticks' bonus is the server's honba and riichi bonus, never the winner's gain less its hand", () => {
        const table = lastRoundEndTable("riichi");
        const result = table.roundEndResult;
        assert(result !== null && result.winners[0] !== undefined);
        const winners = [{ ...result.winners[0], honbaBonus: 600 }];

        expect(
            winPage({ ...table, honbaSticks: 2, roundEndResult: { ...result, winners } }).sticks,
        ).toEqual({ bonus: 2600, honba: 2, riichi: 2 });
    });

    test("the dealer and dora are the result's, whatever the table holds", () => {
        const table = lastRoundEndTable("ron_riichi_discard");
        const result = table.roundEndResult;
        assert(result !== null);
        const stale: TableState = { ...table, dealerSeat: 2, doraIndicators: [] };
        const page = winPage(stale);

        expect(displayAt(stale).seats).toEqual(displayAt(table).seats);
        expect(page.doraIndicators).toHaveLength(result.doraIndicators.length);
        expect(page.doraIndicators.length).toBeGreaterThan(0);
    });

    test("tied scores place by seat distance from the game's first dealer, not the round's dealer", () => {
        const table = lastRoundEndTable("full_game");

        expect([table.firstDealerSeat, table.roundEndResult?.dealerSeat]).toEqual([3, 2]);
        expect(displayAt(table).seats.map((seat) => [seat.after, seat.rank])).toEqual([
            [25_000, "2nd"],
            [25_000, "3rd"],
            [25_000, "4th"],
            [25_000, "1st"],
        ]);
    });
});

describe("roundEndDisplay - a double ron", () => {
    test("each page shows its winner, the seats settling one winner at a time", () => {
        const table = lastRoundEndTable("double_ron");
        const first = displayAt(table, 0);
        const second = displayAt(table, 1);

        expect([first.page, first.pageCount, second.page]).toEqual([0, 2, 1]);
        expect(first.pageNames).toEqual(["Alice", "Charlie"]);
        expect([winPage(table, 0).winnerName, winPage(table, 1).winnerName]).toEqual([
            "Alice",
            "Charlie",
        ]);
        expect(first.seats.map((seat) => [seat.delta, seat.after])).toEqual([
            [-12_000, 13_000],
            [14_000, 38_000],
            [0, 24_000],
            [0, 25_000],
        ]);
        expect(second.seats.map((seat) => seat.after)).toEqual(
            table.players.map((player) => player.score),
        );
        expect(second.seats.map((seat) => [seat.delta, seat.role])).toEqual([
            [-7700, "loss"],
            [0, "none"],
            [7700, "gain"],
            [0, "none"],
        ]);
    });

    test("a page out of range shows the nearest one, and says so", () => {
        const table = lastRoundEndTable("double_ron");

        expect([displayAt(table, 5).page, displayAt(table, -1).page]).toEqual([1, 0]);
        expect(winPage(table, 5).winnerName).toBe("Charlie");
    });
});

describe("roundEndDisplay - a draw", () => {
    test("an exhaustive draw: the tenpai hands as faces; a seat is tagged tenpai or noten only where it moved no points", () => {
        const table = lastRoundEndTable("exhaustive_tenpai");
        const page = drawPage(table);

        expect(page.title).toBe("Exhaustive draw");
        expect(page.subtitle).toBeNull();
        expect(page.hands.map((hand) => [hand.name, handFaces(hand.hand).length])).toEqual([
            ["Alice", 13],
            ["Charlie", 13],
        ]);
        expect(displayAt(table).seats.map((seat) => [seat.delta, seat.tag])).toEqual([
            [-1500, null],
            [1500, null],
            [1500, null],
            [-1500, null],
        ]);
        expect(
            seatTags(withScoreChanges(table, { "0": 0, "1": 1500, "2": 1500, "3": -3000 })),
        ).toEqual(["Noten", null, null, null]);
        expect(seatTags(withScoreChanges(table, { "0": 0, "1": 0, "2": 0, "3": 0 }))).toEqual([
            "Noten",
            "Tenpai",
            "Tenpai",
            "Noten",
        ]);
    });

    test("an exhaustive draw says when every seat or none was tenpai, so no one pays, and tags no seat", () => {
        const noten = roundEndTables("full_game").find(
            (table) => table.roundEndResult?.draw?.tenpaiSeats.length === 0,
        );
        assert(noten !== undefined);
        const tenpai = lastRoundEndTable("exhaustive_tenpai");
        const result = tenpai.roundEndResult;
        assert(result !== null && result.draw !== null);
        const allTenpai = withScoreChanges(
            {
                ...tenpai,
                roundEndResult: {
                    ...result,
                    draw: { ...result.draw, notenSeats: [], tenpaiSeats: [0, 1, 2, 3] },
                },
            },
            { "0": 0, "1": 0, "2": 0, "3": 0 },
        );

        expect([drawPage(noten).subtitle, drawPage(allTenpai).subtitle]).toEqual([
            "All noten: no payments",
            "All tenpai: no payments",
        ]);
        expect([seatTags(noten), seatTags(allTenpai)]).toEqual([
            [null, null, null, null],
            [null, null, null, null],
        ]);
    });

    test("a nagashi mangan: a mangan's value, who made it and what they collected, with no tenpai tags", () => {
        const table = lastRoundEndTable("nagashi");
        const display = displayAt(table);

        expect(display.body).toEqual({
            kind: "nagashi",
            limit: "Mangan",
            makers: ["Alice"],
            points: 8000,
            title: "Nagashi Mangan",
        });
        expect(display.pageCount).toBe(1);
        expect(
            seatTags(withScoreChanges(table, { "0": 0, "1": 8000, "2": -4000, "3": -4000 })),
        ).toEqual([null, null, null, null]);
    });

    test("a nagashi mangan two seats made names both and no points, their changes being net of each other's mangan", () => {
        const table = withScoreChanges(lastRoundEndTable("nagashi"), {
            "0": -6000,
            "1": 6000,
            "2": 6000,
            "3": -6000,
        });
        const { draw } = table.roundEndResult ?? {};
        assert(draw !== null && draw !== undefined && table.roundEndResult !== null);
        const twoMakers = {
            ...table,
            roundEndResult: { ...table.roundEndResult, draw: { ...draw, nagashiSeats: [1, 2] } },
        };

        expect(displayAt(twoMakers).body).toMatchObject({
            makers: ["Alice", "Charlie"],
            points: null,
        });
    });

    test.each([
        ["kyuushu", "Kyuushu Kyuuhai", "declared by Alice"],
        ["triple_ron", "Triple ron", "ron called by Alice, Charlie, and Bob"],
        ["four_kans", "Four kans", "Abortive draw"],
    ])("a %s draw is named with the seats it names", (name, title, subtitle) => {
        const table = lastRoundEndTable(name);

        expect(drawPage(table)).toMatchObject({ subtitle, title });
        expect(displayAt(table).pageCount).toBe(1);
    });
});
