import { describe, expect, it } from "vitest";

import { loadEngineReplay } from "#tests/fixtures/replays";
import {
    OBSERVE_RESULT_HOLD_MS,
    autoplayDelayMs,
    autoplayStep,
    buildNavigationIndex,
} from "@/entities/replay";
import { observeHeldUntil } from "@/entities/replay/model/replay-autoplay";
import { HELD_PANEL_DELAY_MS } from "@/entities/table";

function loaded(name: string) {
    const replay = loadEngineReplay(name);
    return { ...replay, navigation: buildNavigationIndex(replay.events, replay.tables) };
}

describe("autoplayStep", () => {
    it("pauses on each page of a double ron's result and goes no further from the last", () => {
        const { navigation } = loaded("double_ron");

        expect([
            autoplayStep(navigation, { page: 0, stop: 9 }),
            autoplayStep(navigation, { page: 0, stop: 10 }),
            autoplayStep(navigation, { page: 1, stop: 10 }),
        ]).toEqual([
            { cursor: { page: 0, stop: 10 }, pause: true },
            { cursor: { page: 1, stop: 10 }, pause: true },
            null,
        ]);
    });

    it("plays through a round's moves without pausing", () => {
        const { navigation } = loaded("double_ron_on_honba");

        expect(autoplayStep(navigation, { page: 0, stop: 138 })).toEqual({
            cursor: { page: 0, stop: 139 },
            pause: false,
        });
    });
});

describe("autoplayDelayMs", () => {
    it("reads a deal longest and a draw shortest", () => {
        const replay = loaded("riichi");

        expect([
            autoplayDelayMs(replay, { page: 0, stop: 0 }),
            autoplayDelayMs(replay, { page: 0, stop: 1 }),
            autoplayDelayMs(replay, { page: 0, stop: 2 }),
        ]).toEqual([1600, 800, 400]);
    });
});

describe("observeHeldUntil", () => {
    it("holds a result's first page past its panel's delay, a later page only the hold unless the board opened on it, and no other stop", () => {
        const { navigation } = loaded("double_ron");
        const at = 1000;
        const revealed = at + HELD_PANEL_DELAY_MS + OBSERVE_RESULT_HOLD_MS;

        expect([
            observeHeldUntil(navigation, { page: 0, stop: 10 }, { at, opened: false }),
            observeHeldUntil(navigation, { page: 1, stop: 10 }, { at, opened: false }),
            observeHeldUntil(navigation, { page: 1, stop: 10 }, { at, opened: true }),
            observeHeldUntil(navigation, { page: 0, stop: 9 }, { at, opened: true }),
        ]).toEqual([revealed, at + OBSERVE_RESULT_HOLD_MS, revealed, null]);
    });
});
