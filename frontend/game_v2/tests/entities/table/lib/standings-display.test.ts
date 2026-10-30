import { describe, expect, test } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import { type GameEndResult, type RoundRecord, type TableState } from "@/entities/table";
import { type StandingsDisplay, standingsDisplay } from "@/entities/table/lib/standings-display";

const STARTING_SCORE = 25_000;

function endTable(name: string): TableState {
    const table = loadEngineReplay(name).tables.at(-1);
    if (table === undefined) {
        throw new Error(`${name} holds no table`);
    }
    return table;
}

/** A table whose recording stops at a round end, ended there with the scores it holds, its winner the leader. */
function endedAtLastRound(table: TableState): TableState {
    const ranked = table.players.toSorted((first, second) => second.score - first.score);
    return {
        ...table,
        gameEndResult: {
            leftoverRiichiBonus: 0,
            leftoverSticks: 0,
            numRounds: table.roundHistory.length,
            standings: ranked.map((player) => ({
                finalScore: 0,
                score: player.score,
                seat: player.seat,
            })),
            winnerSeat: ranked[0].seat,
        },
        phase: "game_ended",
    };
}

function endOf(table: TableState): GameEndResult {
    const end = table.gameEndResult;
    if (end === null) {
        throw new Error("the table holds no game end");
    }
    return end;
}

function shownStandings(table: TableState, viewerSeat: number | null): StandingsDisplay {
    const display = standingsDisplay(table, viewerSeat);
    if (display === null) {
        throw new Error("the table shows no standings");
    }
    return display;
}

/** The points a cell shows, read as the player reads them: "−1,500" is -1500, a tenpai label or a blank none. */
function pointsShown(text: string): number {
    const points = Number(text.replace("−", "-").replaceAll(",", ""));
    return Number.isNaN(points) ? 0 : points;
}

function cellTexts(table: TableState): string[][] {
    return (standingsDisplay(table, null)?.ledger ?? []).map((row) =>
        row.cells.map((cell) => cell.text),
    );
}

describe("standingsDisplay", () => {
    test("ranks the seats as the server placed them, with the uma/oka result, the viewer and the leftover sticks", () => {
        const display = standingsDisplay(endTable("leftover_riichi"), 1);

        expect(
            display?.seats.map((seat) => [
                seat.placement,
                seat.seat,
                seat.score,
                seat.result,
                seat.viewer,
            ]),
        ).toEqual([
            ["1st", 2, "27,500", "+37.0", false],
            ["2nd", 1, "24,500", "+5.0", true],
            ["3rd", 0, "23,500", "−16.0", false],
            ["4th", 3, "23,500", "−26.0", false],
        ]);
        expect(display?.leftover).toEqual({
            awarded: true,
            cells: ["+1,000", "", "", ""],
            sticks: 1,
        });
        const evenly = shownStandings(endedAtLastRound(endTable("leftover_riichi")), null);
        expect(evenly.seats.map((seat) => seat.result)).toEqual(["0.0", "0.0", "0.0", "0.0"]);
    });

    test("says the leftover sticks were not awarded when the game end pays no bonus for the sticks left", () => {
        const table = endTable("leftover_riichi");
        const end = endOf(table);
        const unpaid = { ...table, gameEndResult: { ...end, leftoverRiichiBonus: 0 } };

        expect(end.leftoverSticks).toBe(1);
        expect(shownStandings(unpaid, null).leftover).toEqual({
            awarded: false,
            cells: ["", "", "", ""],
            sticks: 1,
        });
    });

    test("nets each riichi deposit out of its round, so the rounds and the leftover sticks add up to each final score", () => {
        for (const name of ["leftover_riichi", "pao", "full_game"]) {
            const table = endTable(name);
            const end = endOf(table);
            const { ledger, leftover } = shownStandings(table, null);
            const totals = end.standings.map(
                (_standing, column) =>
                    STARTING_SCORE +
                    pointsShown(leftover?.cells[column] ?? "") +
                    ledger.reduce((sum, row) => sum + pointsShown(row.cells[column].text), 0),
            );

            expect(totals).toEqual(end.standings.map((standing) => standing.score));
        }
        const [riichiRound] = standingsDisplay(endTable("leftover_riichi"), null)?.ledger ?? [];
        expect(riichiRound.cells.map((cell) => [cell.text, cell.riichi])).toEqual([
            ["+1,500", false],
            ["−500", true],
            ["−1,500", false],
            ["−1,500", false],
        ]);
    });

    test("names each round and its outcome, marks who won from whom, and says tenpai on a draw that moved no points", () => {
        const display = standingsDisplay(endedAtLastRound(endTable("double_ron_on_honba")), null);
        const doubleRon = display?.ledger[2];

        expect(display?.ledger.map((row) => [row.name, row.honba, row.outcome])).toEqual([
            ["East 1", 0, "Draw"],
            ["East 2", 1, "Ron"],
            ["East 2", 2, "Double ron"],
            ["East 3", 0, "Tsumo"],
        ]);
        expect(doubleRon?.summary).toBe("Double ron by Alice and Diana from Bob");
        expect(
            display?.seats.map((seat, index) => [seat.name, doubleRon?.cells[index].mark]),
        ).toEqual([
            ["Charlie", null],
            ["Diana", "win"],
            ["Alice", "win"],
            ["Bob", "deal_in"],
        ]);
        expect(cellTexts(endTable("full_game"))[0]).toEqual(["Noten", "Noten", "Noten", "Noten"]);
    });

    test("marks the seat liable for a yakuman (pao) apart from the winner", () => {
        const table = endTable("pao");
        const display = shownStandings(table, null);

        expect(
            display.seats.map((seat, index) => [seat.seat, display.ledger[0].cells[index].mark]),
        ).toEqual([
            [1, "win"],
            [2, null],
            [3, null],
            [0, "pao"],
        ]);
    });

    test("keeps every tenpai on a draw that paid nothing, a riichi's deposit its only change", () => {
        const table = endTable("leftover_riichi");
        const allTenpai: RoundRecord = {
            dealerSeat: 0,
            honba: 0,
            loserSeat: null,
            outcome: "exhaustive",
            paoSeats: [],
            riichiSeats: [3],
            scoreChanges: { "0": 0, "1": 0, "2": 0, "3": 0 },
            tenpaiSeats: [0, 1, 2, 3],
            wind: 0,
            winnerSeats: [],
        };

        expect(cellTexts({ ...table, roundHistory: [allTenpai] })).toEqual([
            ["Tenpai", "Tenpai", "Tenpai", "−2,000"],
        ]);
    });
});
