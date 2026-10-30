import { describe, expect, test } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import {
    type NavigationIndex,
    buildNavigationIndex,
} from "@/entities/table/model/navigation-index";
import {
    firstCursor,
    lastCursor,
    nextCursor,
    nextRoundCursor,
    positionCursor,
    prevCursor,
    prevRoundCursor,
    roundPosition,
} from "@/entities/table/model/replay-cursor";

function navigationOf(name: string): NavigationIndex {
    const { events, tables } = loadEngineReplay(name);
    return buildNavigationIndex(events, tables);
}

describe("replay cursor", () => {
    test("pages through a double ron's winners before leaving its result, and back in at its last page", () => {
        const nav = navigationOf("double_ron");
        const result = nav.stops.length - 1;
        const before = { page: 0, stop: result - 1 };

        expect(nextCursor(nav, before)).toEqual({ page: 0, stop: result });
        expect(nextCursor(nav, { page: 0, stop: result })).toEqual({ page: 1, stop: result });
        expect(nextCursor(nav, { page: 1, stop: result })).toBeNull();
        expect(prevCursor(nav, { page: 1, stop: result })).toEqual({ page: 0, stop: result });
        expect(prevCursor(nav, { page: 0, stop: result })).toEqual(before);
        expect(lastCursor(nav)).toEqual({ page: 1, stop: result });
    });

    test("goes back past a stop into the previous result at its last page", () => {
        const nav = navigationOf("double_ron_on_honba");
        const doubleRon = nav.stops.findIndex((stop) => stop.pages === 2);

        expect(prevCursor(nav, { page: 0, stop: doubleRon + 1 })).toEqual({
            page: 1,
            stop: doubleRon,
        });
    });

    test("starts at the first deal and stops at both ends", () => {
        const nav = navigationOf("full_game");
        const first = firstCursor(nav);

        expect(first).toEqual({ page: 0, stop: 0 });
        expect(first && prevCursor(nav, first)).toBeNull();
        expect(lastCursor(nav)).toEqual({ page: 0, stop: nav.stops.length - 1 });
    });

    test("jumps back to the round's deal, from its deal to the previous round's, and on to the next round's", () => {
        const nav = navigationOf("full_game");
        const [, second, third] = nav.rounds;
        const midSecond = { page: 0, stop: second.firstStop + 3 };

        expect(prevRoundCursor(nav, midSecond)).toEqual({ page: 0, stop: second.firstStop });
        expect(prevRoundCursor(nav, { page: 0, stop: second.firstStop })).toEqual({
            page: 0,
            stop: 0,
        });
        expect(prevRoundCursor(nav, { page: 0, stop: 0 })).toBeNull();
        expect(nextRoundCursor(nav, midSecond)).toEqual({ page: 0, stop: third.firstStop });
        expect(nextRoundCursor(nav, { page: 0, stop: nav.stops.length - 1 })).toBeNull();
    });

    test("numbers stops within their round from 0 at the deal, the standings the last round's last step", () => {
        const nav = navigationOf("full_game");
        const lastRound = nav.rounds.length - 1;
        const standings = { page: 0, stop: nav.stops.length - 1 };

        expect(roundPosition(nav, { page: 0, stop: nav.rounds[1].firstStop + 4 })).toEqual({
            round: 1,
            step: 4,
        });
        expect(roundPosition(nav, standings)).toEqual({
            round: lastRound,
            step: nav.rounds[lastRound].stopCount - 1,
        });
        expect(positionCursor(nav, roundPosition(nav, standings))).toEqual(standings);
        expect(positionCursor(nav, { round: 1, step: nav.rounds[1].stopCount })).toBeNull();
        expect(positionCursor(nav, { round: nav.rounds.length, step: 0 })).toBeNull();
    });
});
