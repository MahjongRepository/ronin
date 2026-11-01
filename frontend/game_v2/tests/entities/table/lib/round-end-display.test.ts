import { assert, describe, expect, test } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import {
    type DrawPageDisplay,
    type ResultHandDisplay,
    type RoundEndDisplayState,
    type RoundEndResult,
    type TableState,
    type WinPageDisplay,
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

function displayAt(table: TableState, page = 0): RoundEndDisplayState {
    assert(table.roundEndResult !== null);
    const { players, roundEndResult } = table;
    return roundEndDisplay({ players, result: roundEndResult }, page);
}

function winPage(table: TableState, page = 0): WinPageDisplay {
    const { body } = displayAt(table, page);
    assert(body.kind === "win");
    return body;
}

function drawPage(table: TableState): DrawPageDisplay {
    const { body } = displayAt(table);
    assert(body.kind === "draw");
    return body;
}

function handFaces(hand: ResultHandDisplay): string[] {
    return hand.tiles.map((tile) => tile.face ?? "?");
}

describe("roundEndDisplay - a win", () => {
    test("a ron: who won from whom, the hand's value with its limit, the yaku with the dora last", () => {
        const page = winPage(lastRoundEndTable("ron_riichi_discard"));

        expect(page).toMatchObject({
            from: "from Charlie",
            hanFu: "7 han 30 fu",
            limit: "Haneman",
            points: 12_000,
            title: "Ron",
            winnerName: "Alice",
            winnerWind: "South",
        });
        expect(page.yaku.map((line) => [line.name, line.han, line.isDora])).toEqual([
            ["Ippatsu", 1, false],
            ["Double Riichi", 2, false],
            ["Pinfu", 1, false],
            ["Ittsu", 2, false],
            ["Red Five", 1, true],
        ]);
        expect(page.notes).toEqual(["Riichi ×1 +1,000"]);
    });

    test("a chankan: the ron reads as robbing the declarer's kan, not as taking a discard", () => {
        const page = winPage(lastRoundEndTable("chankan_added"));

        expect(page).toMatchObject({
            from: "robbing Alice's kan",
            title: "Ron",
            winnerName: "Charlie",
        });
        expect(page.yaku.map((line) => line.name)).toContain("Chankan");
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

    test("the scores: each seat's change and the score it leads to, by wind and name", () => {
        const { scores } = displayAt(lastRoundEndTable("riichi"));

        expect(scores.map((row) => [row.wind, row.name, row.delta, row.after, row.tag])).toEqual([
            ["East", "Diana", -4000, 21_000, null],
            ["South", "Alice", 10_000, 34_000, null],
            ["West", "Charlie", -2000, 23_000, null],
            ["North", "Bob", -2000, 22_000, null],
        ]);
    });

    test("a yakuman: names it without han or fu; pao names the liable seat and tags its score; melds laid out", () => {
        const table = lastRoundEndTable("pao");
        const page = winPage(table);

        expect(page.limit).toBe("Yakuman");
        expect(page.hanFu).toBeNull();
        expect(page.yaku.map((line) => [line.name, line.han, line.yakuman])).toEqual([
            ["Daisangen", null, null],
        ]);
        expect(page.notes).toContain("Pao: Diana is liable for Daisangen and pays all of it");
        expect(displayAt(table).scores.map((row) => [row.name, row.tag])).toEqual([
            ["Diana", "Pao"],
            ["Alice", null],
            ["Charlie", null],
            ["Bob", null],
        ]);
        expect(page.hand.melds).toHaveLength(3);
        expect(page.winningTileLabel).toBe("Tsumo");
    });

    test("pao words the server's liability: the yakuman it covers, its share and the honba, whatever the hand and loser", () => {
        const table = lastRoundEndTable("pao");
        const result = table.roundEndResult;
        assert(result !== null && result.winners[0] !== undefined);
        const ended: RoundEndResult = result;
        const [winner] = result.winners;
        function notesWhen(loserSeat: number | null, pao: PaoLiability): readonly string[] {
            const winners = [{ ...winner, pao }];
            return winPage({ ...table, roundEndResult: { ...ended, loserSeat, winners } }).notes;
        }
        const daisuushiiHalf = { paysHonba: true, seat: 0, share: PAO_SHARE.HALF, yakuIds: [111] };

        expect(notesWhen(null, daisuushiiHalf)).toContain(
            "Pao: Diana is liable for Dai Suushii and pays half of it and the honba",
        );
        expect(
            notesWhen(2, { ...daisuushiiHalf, paysHonba: false, share: PAO_SHARE.ALL }),
        ).toContain("Pao: Diana is liable for Dai Suushii and pays all of it");
        expect(notesWhen(0, daisuushiiHalf)).toContain(
            "Pao: Diana is liable and dealt in, so pays it all",
        );
    });

    test("a yakuman yaku worth more than one names the server's multiple in place of han", () => {
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
            ["Dai Suushii", null, "Double Yakuman"],
        ]);
    });

    test("a kazoe yakuman: keeps its han beside the limit", () => {
        const page = winPage(lastRoundEndTable("kazoe"));

        expect(page).toMatchObject({
            hanFu: "15 han 20 fu",
            limit: "Kazoe Yakuman",
            points: 48_000,
        });
    });

    test("head bump: tells the player whose call lost and who won it", () => {
        const page = winPage(lastRoundEndTable("head_bump"));

        expect(page.notes).toEqual(["Alice won over Charlie's ron (head bump)"]);
    });

    test("a double ron on honba: each winner's page notes its own honba bonus", () => {
        const table = roundEndTables("double_ron_on_honba").find(
            (candidate) => (candidate.roundEndResult?.winners.length ?? 0) > 1,
        );
        assert(table !== undefined);

        expect([winPage(table, 0).notes, winPage(table, 1).notes]).toEqual([
            ["Honba +600"],
            ["Honba +600"],
        ]);
    });
});

describe("roundEndDisplay - the server's facts, never the table's or arithmetic", () => {
    test("the honba note is the server's bonus, never the winner's gain less its hand and sticks", () => {
        const table = lastRoundEndTable("riichi");
        const result = table.roundEndResult;
        assert(result !== null && result.winners[0] !== undefined);
        const winners = [{ ...result.winners[0], honbaBonus: 600 }];

        expect(winPage({ ...table, roundEndResult: { ...result, winners } }).notes).toContain(
            "Honba +600",
        );
    });

    test("the dealer and dora are the result's, whatever the table holds", () => {
        const table = lastRoundEndTable("ron_riichi_discard");
        const result = table.roundEndResult;
        assert(result !== null);
        const stale: TableState = { ...table, dealerSeat: 2, doraIndicators: [] };
        const page = winPage(stale);

        expect(page.winnerWind).toBe("South");
        expect(page.doraIndicators).toHaveLength(result.doraIndicators.length);
        expect(page.doraIndicators.length).toBeGreaterThan(0);
    });
});

describe("roundEndDisplay - a double ron", () => {
    test("each page shows its winner, the scores settling one winner at a time", () => {
        const table = lastRoundEndTable("double_ron");
        const first = displayAt(table, 0);
        const second = displayAt(table, 1);

        expect([first.page, first.pageCount, second.page]).toEqual([0, 2, 1]);
        expect([winPage(table, 0).winnerName, winPage(table, 1).winnerName]).toEqual([
            "Alice",
            "Charlie",
        ]);
        expect(first.scores.map((row) => row.after)).toEqual([13_000, 38_000, 24_000, 25_000]);
        expect(second.scores.map((row) => row.after)).toEqual(
            table.players.map((player) => player.score),
        );
        expect(second.scores.map((row) => row.delta)).toEqual([-8000, 0, 8000, 0]);
    });

    test("a page out of range shows the nearest one, and says so", () => {
        const table = lastRoundEndTable("double_ron");

        expect([displayAt(table, 5).page, displayAt(table, -1).page]).toEqual([1, 0]);
        expect(winPage(table, 5).winnerName).toBe("Charlie");
    });
});

describe("roundEndDisplay - a draw", () => {
    test("an exhaustive draw: the tenpai hands as faces, each seat tagged tenpai or noten with its payment", () => {
        const table = lastRoundEndTable("exhaustive_tenpai");
        const display = displayAt(table);
        const page = drawPage(table);

        expect(page.title).toBe("Exhaustive draw");
        expect(page.subtitle).toBeNull();
        expect(page.rivers).toEqual([]);
        expect(page.tenpaiHands.map((hand) => [hand.name, handFaces(hand.hand).length])).toEqual([
            ["Alice", 13],
            ["Charlie", 13],
        ]);
        expect(display.scores.map((row) => [row.tag, row.delta])).toEqual([
            ["Noten", -1500],
            ["Tenpai", 1500],
            ["Tenpai", 1500],
            ["Noten", -1500],
        ]);
    });

    test("an exhaustive draw says when every seat or none was tenpai, so no one pays", () => {
        const noten = roundEndTables("full_game").find(
            (table) => table.roundEndResult?.draw?.tenpaiSeats.length === 0,
        );
        assert(noten !== undefined);
        const tenpai = lastRoundEndTable("exhaustive_tenpai");
        const result = tenpai.roundEndResult;
        assert(result !== null && result.draw !== null);
        const allTenpai: TableState = {
            ...tenpai,
            roundEndResult: {
                ...result,
                draw: { ...result.draw, notenSeats: [], tenpaiSeats: [0, 1, 2, 3] },
            },
        };

        expect([drawPage(noten).subtitle, drawPage(allTenpai).subtitle]).toEqual([
            "All noten: no payments",
            "All tenpai: no payments",
        ]);
    });

    test("a nagashi mangan shows its maker's river as the server names it, whatever the table's river", () => {
        const table = lastRoundEndTable("nagashi");
        const page = drawPage({
            ...table,
            players: table.players.map((player) => ({ ...player, discards: [] })),
        });

        expect(
            page.rivers.map((river) => ({
                name: river.name,
                tiles: river.tiles.map((tile) => tile.face),
            })),
        ).toEqual([
            {
                name: "Alice",
                tiles: [
                    ...Array.from({ length: 4 }, () => "1m"),
                    ...Array.from({ length: 4 }, () => "9m"),
                    ...Array.from({ length: 4 }, () => "1p"),
                    ...Array.from({ length: 4 }, () => "9p"),
                    "1s",
                    "1s",
                ],
            },
        ]);
    });

    test.each([
        ["nagashi", "Nagashi Mangan", "by Alice"],
        ["kyuushu", "Nine terminals", "declared by Alice"],
        ["triple_ron", "Triple ron", "ron called by Alice, Charlie, Bob"],
        ["four_kans", "Four kans", "Abortive draw"],
    ])("a %s draw is named with the seats it names", (name, title, subtitle) => {
        const table = lastRoundEndTable(name);

        expect(drawPage(table)).toMatchObject({ subtitle, title });
        expect(displayAt(table).pageCount).toBe(1);
    });
});
