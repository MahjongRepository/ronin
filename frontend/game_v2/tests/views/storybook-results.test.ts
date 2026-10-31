import { describe, expect, test } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import { type PlayerState, type RoundEndResult } from "@/entities/table";
import { RESULT_STORIES, resultStoryTable } from "@/views/storybook-results";

function nagashiRivers(players: readonly PlayerState[], result: RoundEndResult): number[][] {
    const seats = result.draw?.nagashiSeats ?? [];
    return players
        .filter((player) => seats.includes(player.seat))
        .map((player) => player.discards.map((discard) => discard.tileId));
}

describe("resultStoryTable", () => {
    test.each(RESULT_STORIES)(
        "the %s story reads as a round end of its fixture, with its round's dealer, names and the rivers it shows",
        (story) => {
            const { dealerSeat, fixture, players, result } = resultStoryTable(story);
            const matching = loadEngineReplay(fixture).tables.find(
                (candidate) => JSON.stringify(candidate.roundEndResult) === JSON.stringify(result),
            );

            expect(matching?.roundEndResult).toEqual(result);
            expect(matching?.dealerSeat).toBe(dealerSeat);
            expect(matching?.players.map((player) => player.name)).toEqual(
                players.map((player) => player.name),
            );
            expect(nagashiRivers(players, result)).toEqual(
                nagashiRivers(matching?.players ?? [], result),
            );
        },
    );
});
