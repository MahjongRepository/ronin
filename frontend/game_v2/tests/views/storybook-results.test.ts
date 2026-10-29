import { describe, expect, test } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import { RESULT_STORIES, resultStoryTable } from "@/views/storybook-results";

describe("resultStoryTable", () => {
    test.each(RESULT_STORIES)(
        "the %s story reads as a round end of its fixture, with its round's dealer and names",
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
        },
    );
});
