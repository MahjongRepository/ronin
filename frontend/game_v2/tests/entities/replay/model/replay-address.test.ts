import { describe, expect, test } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import {
    type NavigationIndex,
    buildNavigationIndex,
} from "@/entities/replay/model/navigation-index";
import {
    parseReplayAddress,
    replayAddressSearch,
    resolveReplayAddress,
} from "@/entities/replay/model/replay-address";

const FIRST_DEAL = { page: 0, stop: 0 };
const DEFAULTS = { bottomSeat: 3, cursor: FIRST_DEAL, seatCount: 4 };

function navigationOf(name: string): NavigationIndex {
    const { events, tables } = loadEngineReplay(name);
    return buildNavigationIndex(events, tables);
}

describe("parseReplayAddress", () => {
    test("reads whole numbers and drops a missing, repeated, signed, decimal or empty value", () => {
        expect(parseReplayAddress("?seat=2&round=10&step=0")).toEqual({
            round: 10,
            seat: 2,
            step: 0,
        });
        expect(parseReplayAddress("?seat=1&seat=2&round=-1&step=1.5")).toEqual({
            round: null,
            seat: null,
            step: null,
        });
        expect(parseReplayAddress("?seat=&round=abc")).toEqual({
            round: null,
            seat: null,
            step: null,
        });
    });
});

describe("resolveReplayAddress", () => {
    const nav = navigationOf("full_game");

    test("opens the named seat, round and step", () => {
        expect(resolveReplayAddress(nav, { round: 2, seat: 1, step: 5 }, DEFAULTS)).toEqual({
            bottomSeat: 1,
            cursor: { page: 0, stop: nav.rounds[2].firstStop + 5 },
        });
    });

    test("falls back to the default seat for a seat the game does not seat", () => {
        expect(resolveReplayAddress(nav, { round: 0, seat: 4, step: 0 }, DEFAULTS).bottomSeat).toBe(
            3,
        );
    });

    test("opens the first deal for a missing or out-of-range round, its step ignored", () => {
        expect(
            resolveReplayAddress(nav, { round: null, seat: null, step: 7 }, DEFAULTS).cursor,
        ).toEqual(FIRST_DEAL);
        expect(
            resolveReplayAddress(nav, { round: 99, seat: null, step: 7 }, DEFAULTS).cursor,
        ).toEqual(FIRST_DEAL);
    });

    test("opens the round's deal for a missing or out-of-range step", () => {
        const deal = { page: 0, stop: nav.rounds[3].firstStop };
        const pastEnd = nav.rounds[3].stopCount;

        expect(
            resolveReplayAddress(nav, { round: 3, seat: 0, step: null }, DEFAULTS).cursor,
        ).toEqual(deal);
        expect(
            resolveReplayAddress(nav, { round: 3, seat: 0, step: pastEnd }, DEFAULTS).cursor,
        ).toEqual(deal);
    });
});

describe("replayAddressSearch", () => {
    test("names the seat, round and step from 0, keeping the page's other parameters and no repeat", () => {
        const nav = navigationOf("full_game");
        const view = { bottomSeat: 2, cursor: { page: 1, stop: nav.rounds[1].firstStop + 3 } };

        expect(replayAddressSearch("?step=9&step=8&debug", nav, view)).toBe(
            "?step=3&debug=&seat=2&round=1",
        );
    });

    test("reads back to the view it names", () => {
        const nav = navigationOf("full_game");
        const view = { bottomSeat: 0, cursor: { page: 0, stop: nav.stops.length - 1 } };

        const address = parseReplayAddress(replayAddressSearch("", nav, view));

        expect(resolveReplayAddress(nav, address, DEFAULTS)).toEqual(view);
    });
});
