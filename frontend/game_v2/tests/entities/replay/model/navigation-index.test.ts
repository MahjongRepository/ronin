import { describe, expect, test } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import {
    type NavigationIndex,
    buildNavigationIndex,
} from "@/entities/replay/model/navigation-index";

function navigationOf(name: string): NavigationIndex {
    const { events, tables } = loadEngineReplay(name);
    return buildNavigationIndex(events, tables);
}

describe("buildNavigationIndex", () => {
    test("numbers each round within its wind from a first dealer off seat 0, a dealer's repeat keeping it", () => {
        const { rounds } = navigationOf("eager_game");

        expect(rounds.map((round) => [round.wind, round.roundInWind, round.honba])).toEqual([
            [0, 1, 0],
            [0, 2, 0],
            [0, 2, 1],
            [0, 3, 0],
            [0, 4, 1],
            [1, 1, 0],
            [1, 2, 0],
            [1, 3, 0],
            [1, 4, 0],
        ]);
    });

    test("opens on the first deal and gives every stop to one round, the standings to the last", () => {
        const { events } = loadEngineReplay("full_game");
        const { complete, rounds, stops } = navigationOf("full_game");

        expect(events[stops[0].moveEntry]?.type).toBe("round_started");
        expect(rounds.map((round) => round.firstStop)).toEqual(
            stops.flatMap((stop, index) =>
                events[stop.moveEntry]?.type === "round_started" ? [index] : [],
            ),
        );
        expect(rounds.reduce((sum, round) => sum + round.stopCount, 0)).toBe(stops.length);
        expect(events[stops[stops.length - 1].moveEntry]?.type).toBe("game_end");
        expect(stops.at(-1)?.round).toBe(rounds.length - 1);
        expect(complete).toBe(true);
    });

    test("gives a double ron's result stop a page per winner, every other stop one", () => {
        const { stops } = navigationOf("double_ron");

        expect(stops.at(-1)?.pages).toBe(2);
        expect(stops.slice(0, -1).every((stop) => stop.pages === 1)).toBe(true);
    });

    test("keeps each round's result, none for a round the recording stops in, and marks it incomplete", () => {
        const midRound = navigationOf("truncated_mid_round");
        const afterRound = navigationOf("truncated_after_round");

        expect([midRound.complete, midRound.rounds.map((round) => round.result)]).toEqual([
            false,
            [null],
        ]);
        expect(afterRound.complete).toBe(false);
        expect(afterRound.rounds.every((round) => round.result !== null)).toBe(true);
    });

    test("starts a seat's turn once, the draw after its kan staying in the turn the kan was made in", () => {
        const { events } = loadEngineReplay("kans");
        const { stops } = navigationOf("kans");
        const afterOwnKan = stops.filter((stop, index) => {
            const before = events[stops[index - 1]?.moveEntry];
            const move = events[stop.moveEntry];
            return (
                move.type === "draw" && before?.type === "meld" && before.callerSeat === move.seat
            );
        });

        expect(afterOwnKan.length).toBeGreaterThan(0);
        expect(afterOwnKan.map((stop) => stop.turnSeat)).toEqual(afterOwnKan.map(() => null));
    });
});
