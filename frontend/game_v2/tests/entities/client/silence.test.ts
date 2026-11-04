import { describe, expect, it } from "vitest";

import { GAME_ID, HANDOFF, clientEvent } from "#tests/fixtures/scenario";
import { WIRE_GAME_JOINED, WIRE_GAME_STARTED } from "#tests/fixtures/wire";
import { serverSilenceLimitMs, startGameClient, stepGameClient } from "@/entities/client";
import { WIRE_KEY } from "@/shared/protocol";

const { message, opened } = clientEvent;

describe("serverSilenceLimitMs", () => {
    it("waits out a round advance over three winners' pages, the most rons one discard can make", () => {
        const timer = {
            [WIRE_KEY.BANK_SECONDS]: 20,
            [WIRE_KEY.GAME_START_PAUSE]: 3,
            [WIRE_KEY.MAX_BANK_SECONDS]: 20,
            [WIRE_KEY.ROUND_ADVANCE_TIMEOUT]: 40,
            [WIRE_KEY.BASE_TURN_SECONDS]: 5,
        };
        const started = [
            opened(0),
            message(0, WIRE_GAME_JOINED),
            message(10, {
                ...WIRE_GAME_STARTED,
                [WIRE_KEY.SEAT]: 0,
                [WIRE_KEY.TIMER_SETTINGS]: timer,
            }),
        ].reduce(
            (state, event) => stepGameClient(state, event).state,
            startGameClient(GAME_ID, HANDOFF, 0).state,
        );

        expect(serverSilenceLimitMs(started)).toBe(3 * 40_000 + 25_000);
    });
});
